import json
import base64
from datetime import date, datetime
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from webauthn import (
    generate_registration_options, verify_registration_response,
    generate_authentication_options, verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor, UserVerificationRequirement,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from workforce.models import StaffProfile
from .models import Attendance, WebAuthnCredential, WebAuthnChallenge
from .serializers import (
    AttendanceSerializer, SignInRequestSerializer,
    FieldClockInRequestSerializer, WebAuthnCredentialSerializer,
)
from .utils import check_geofence, determine_attendance_status, calculate_attendance_grade

RP_ID = "oticgs.com"
RP_NAME = "OTIC Workforce"
ORIGIN = "https://origin.oticgs.com"


def _get_staff(request):
    try:
        return StaffProfile.objects.select_related('organization').get(user=request.user)
    except StaffProfile.DoesNotExist:
        return None


# ============================================
# WEBAUTHN REGISTRATION
# ============================================

class WebAuthnRegisterBeginView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        staff = _get_staff(request)
        if not staff:
            return Response({'error': 'Staff profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        existing_creds = WebAuthnCredential.objects.filter(staff=staff)
        exclude_credentials = [
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in existing_creds
        ]

        options = generate_registration_options(
            rp_id=RP_ID,
            rp_name=RP_NAME,
            user_id=str(staff.id).encode(),
            user_name=request.user.username,
            user_display_name=str(staff),
            exclude_credentials=exclude_credentials,
        )

        WebAuthnChallenge.objects.create(
            staff=staff,
            challenge=bytes_to_base64url(options.challenge),
            purpose='register',
        )

        return Response(json.loads(options_to_json(options)))


class WebAuthnRegisterCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        staff = _get_staff(request)
        if not staff:
            return Response({'error': 'Staff profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        challenge_obj = WebAuthnChallenge.objects.filter(
            staff=staff, purpose='register', used=False
        ).order_by('-created_at').first()
        if not challenge_obj:
            return Response({'error': 'No pending registration challenge. Please restart registration.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            credential = verify_registration_response(
                credential=request.data.get('credential'),
                expected_challenge=base64url_to_bytes(challenge_obj.challenge),
                expected_origin=ORIGIN,
                expected_rp_id=RP_ID,
            )
        except Exception as e:
            return Response({'error': f'Registration verification failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        WebAuthnCredential.objects.create(
            staff=staff,
            credential_id=bytes_to_base64url(credential.credential_id),
            public_key=bytes_to_base64url(credential.credential_public_key),
            sign_count=credential.sign_count,
            device_label=request.data.get('device_label', ''),
        )
        challenge_obj.used = True
        challenge_obj.save(update_fields=['used'])

        return Response({'success': True, 'message': 'Biometric device registered successfully.'}, status=status.HTTP_201_CREATED)


class MyWebAuthnCredentialsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff = _get_staff(request)
        if not staff:
            return Response([])
        creds = WebAuthnCredential.objects.filter(staff=staff)
        return Response(WebAuthnCredentialSerializer(creds, many=True).data)

    def delete(self, request, credential_id):
        staff = _get_staff(request)
        WebAuthnCredential.objects.filter(staff=staff, id=credential_id).delete()
        return Response({'success': True})


# ============================================
# WEBAUTHN SIGN-IN CHALLENGE
# ============================================

class WebAuthnSignInBeginView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        staff = _get_staff(request)
        if not staff:
            return Response({'error': 'Staff profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        creds = WebAuthnCredential.objects.filter(staff=staff)
        if not creds.exists():
            return Response({'error': 'No biometric device registered. Please register one first.'}, status=status.HTTP_400_BAD_REQUEST)

        allow_credentials = [
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in creds
        ]

        options = generate_authentication_options(
            rp_id=RP_ID,
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.REQUIRED,
        )

        WebAuthnChallenge.objects.create(
            staff=staff,
            challenge=bytes_to_base64url(options.challenge),
            purpose='signin',
        )

        return Response(json.loads(options_to_json(options)))


# ============================================
# SIGN IN / SIGN OUT
# ============================================

class AttendanceSignInView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        staff = _get_staff(request)
        if not staff or not staff.organization:
            return Response({'error': 'Staff profile or organization not found.'}, status=status.HTTP_404_NOT_FOUND)

        org = staff.organization
        today = date.today()

        if Attendance.objects.filter(staff=staff, date=today).exists():
            return Response({'error': 'Already signed in today.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = SignInRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data

        # 1. Geofence check
        is_within, distance = check_geofence(data['latitude'], data['longitude'], org)

        if not is_within:
            return Response({
                'error': 'You are outside the office geofence. Use "Not at Work" clock-in if you are working remotely.',
                'distance_m': distance,
            }, status=status.HTTP_403_FORBIDDEN)

        # 2. Biometric check (soft fallback if unavailable/not provided)
        cred_id = data.get('webauthn_credential_id')
        biometric_verified = False
        sign_in_method = 'geofence'

        if cred_id:
            challenge_obj = WebAuthnChallenge.objects.filter(
                staff=staff, purpose='signin', used=False
            ).order_by('-created_at').first()
            if not challenge_obj:
                return Response({'error': 'No pending sign-in challenge. Please restart.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                stored_cred = WebAuthnCredential.objects.get(staff=staff, credential_id=cred_id)
            except WebAuthnCredential.DoesNotExist:
                return Response({'error': 'Unrecognized biometric credential.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                verify_authentication_response(
                    credential=request.data.get('webauthn_credential'),
                    expected_challenge=base64url_to_bytes(challenge_obj.challenge),
                    expected_origin=ORIGIN,
                    expected_rp_id=RP_ID,
                    credential_public_key=base64url_to_bytes(stored_cred.public_key),
                    credential_current_sign_count=stored_cred.sign_count,
                )
            except Exception as e:
                return Response({'error': f'Biometric verification failed: {str(e)}'}, status=status.HTTP_403_FORBIDDEN)

            challenge_obj.used = True
            challenge_obj.save(update_fields=['used'])
            biometric_verified = True
            sign_in_method = 'biometric'

        now = timezone.now()
        attendance_status = determine_attendance_status(now, org)
        grade = calculate_attendance_grade(now, org)

        attendance = Attendance.objects.create(
            staff=staff,
            date=today,
            sign_in_time=now,
            sign_in_lat=data['latitude'],
            sign_in_lng=data['longitude'],
            sign_in_method=sign_in_method,
            geofence_verified=True,
            biometric_verified=biometric_verified,
            attendance_type='office',
            approval_status='not_required',
            status=attendance_status,
            distance_from_office_m=distance,
            attendance_grade=grade,
        )

        return Response(AttendanceSerializer(attendance).data, status=status.HTTP_201_CREATED)


class AttendanceSignOutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        staff = _get_staff(request)
        if not staff or not staff.organization:
            return Response({'error': 'Staff profile or organization not found.'}, status=status.HTTP_404_NOT_FOUND)

        today = date.today()
        try:
            attendance = Attendance.objects.get(staff=staff, date=today)
        except Attendance.DoesNotExist:
            return Response({'error': 'No sign-in record found for today.'}, status=status.HTTP_404_NOT_FOUND)

        if attendance.sign_out_time:
            return Response({'error': 'Already signed out today.'}, status=status.HTTP_400_BAD_REQUEST)

        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')

        attendance.sign_out_time = timezone.now()
        if latitude is not None:
            attendance.sign_out_lat = latitude
        if longitude is not None:
            attendance.sign_out_lng = longitude
        attendance.save(update_fields=['sign_out_time', 'sign_out_lat', 'sign_out_lng'])

        return Response(AttendanceSerializer(attendance).data)


# ============================================
# FIELD CLOCK-IN ("Not at Work")
# ============================================

class FieldClockInView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        staff = _get_staff(request)
        if not staff or not staff.organization:
            return Response({'error': 'Staff profile or organization not found.'}, status=status.HTTP_404_NOT_FOUND)

        org = staff.organization
        today = date.today()

        if Attendance.objects.filter(staff=staff, date=today).exists():
            return Response({'error': 'Already clocked in today.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = FieldClockInRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data

        is_within, distance = check_geofence(data['latitude'], data['longitude'], org)
        reason = data.get('reason', '').strip()

        # Reason required only if they're > 15m away (per org policy — using geofence_radius_m as that threshold)
        if not is_within and not reason:
            return Response({
                'error': 'A reason is required when clocking in from outside the office.',
                'distance_m': distance,
            }, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        attendance_status = determine_attendance_status(now, org)
        grade = calculate_attendance_grade(now, org)

        attendance = Attendance.objects.create(
            staff=staff,
            date=today,
            sign_in_time=now,
            sign_in_lat=data['latitude'],
            sign_in_lng=data['longitude'],
            sign_in_method='manual',
            geofence_verified=is_within,
            biometric_verified=False,
            attendance_type='field',
            approval_status='pending',
            reason=reason,
            status=attendance_status,
            distance_from_office_m=distance,
            attendance_grade=grade,
        )

        return Response(AttendanceSerializer(attendance).data, status=status.HTTP_201_CREATED)


class AdminPendingFieldClockInsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        pending = Attendance.objects.filter(
            attendance_type='field', approval_status='pending'
        ).select_related('staff__user').order_by('-created_at')
        return Response(AttendanceSerializer(pending, many=True).data)


class AdminApproveFieldClockInView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, attendance_id):
        try:
            attendance = Attendance.objects.get(id=attendance_id, attendance_type='field', approval_status='pending')
        except Attendance.DoesNotExist:
            return Response({'error': 'Pending field clock-in not found.'}, status=status.HTTP_404_NOT_FOUND)

        action = request.data.get('action')
        if action == 'approve':
            attendance.approval_status = 'approved'
        elif action == 'reject':
            attendance.approval_status = 'rejected'
        else:
            return Response({'error': 'action must be "approve" or "reject".'}, status=status.HTTP_400_BAD_REQUEST)

        attendance.approved_by = request.user
        attendance.approved_at = timezone.now()
        attendance.save(update_fields=['approval_status', 'approved_by', 'approved_at'])

        return Response(AttendanceSerializer(attendance).data)


# ============================================
# STAFF-FACING VIEWS
# ============================================

class MyTodayAttendanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff = _get_staff(request)
        if not staff:
            return Response({'error': 'Staff profile not found.'}, status=status.HTTP_404_NOT_FOUND)
        attendance = Attendance.objects.filter(staff=staff, date=date.today()).first()
        if not attendance:
            return Response(None)
        return Response(AttendanceSerializer(attendance).data)


class MyAttendanceHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        staff = _get_staff(request)
        if not staff:
            return Response([])
        qs = Attendance.objects.filter(staff=staff).order_by('-date')[:60]
        return Response(AttendanceSerializer(qs, many=True).data)


# ============================================
# ADMIN DASHBOARD ANALYTICS
# ============================================

class AdminAttendanceSummaryView(APIView):
    """Today's summary cards: present, late, absent, attendance rate"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        staff = _get_staff(request)
        org = staff.organization if staff else None
        if not org:
            return Response({'error': 'Organization not found for this admin.'}, status=status.HTTP_404_NOT_FOUND)

        today = date.today()
        total_staff = StaffProfile.objects.filter(organization=org, is_active=True).count()

        today_records = Attendance.objects.filter(staff__organization=org, date=today)
        present_today = today_records.filter(status='present').count()
        late_today = today_records.filter(status='late').count()
        signed_in_today = today_records.count()
        signed_out_today = today_records.filter(sign_out_time__isnull=False).count()
        absent_today = max(0, total_staff - signed_in_today)

        attendance_rate = round((signed_in_today / total_staff * 100), 1) if total_staff > 0 else 0

        return Response({
            'total_staff': total_staff,
            'present_today': present_today,
            'late_today': late_today,
            'absent_today': absent_today,
            'signed_in_today': signed_in_today,
            'signed_out_today': signed_out_today,
            'attendance_rate': attendance_rate,
        })


class AdminAttendanceTrendView(APIView):
    """Line chart data: attendance rate over the last N days"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        staff = _get_staff(request)
        org = staff.organization if staff else None
        if not org:
            return Response({'error': 'Organization not found for this admin.'}, status=status.HTTP_404_NOT_FOUND)

        days = int(request.query_params.get('days', 14))
        total_staff = StaffProfile.objects.filter(organization=org, is_active=True).count()
        today = date.today()

        # Single query for the whole range — avoids N+1
        start_date = today - timezone.timedelta(days=days - 1)
        records = Attendance.objects.filter(
            staff__organization=org, date__range=[start_date, today]
        ).values('date', 'status')

        by_date = {}
        for r in records:
            d = r['date']
            by_date.setdefault(d, {'present': 0, 'late': 0, 'total': 0})
            by_date[d]['total'] += 1
            if r['status'] == 'present':
                by_date[d]['present'] += 1
            elif r['status'] == 'late':
                by_date[d]['late'] += 1

        trend = []
        for i in range(days):
            d = start_date + timezone.timedelta(days=i)
            day_data = by_date.get(d, {'present': 0, 'late': 0, 'total': 0})
            rate = round((day_data['total'] / total_staff * 100), 1) if total_staff > 0 else 0
            trend.append({
                'date': str(d),
                'day_name': d.strftime('%A'),
                'present': day_data['present'],
                'late': day_data['late'],
                'total_signed_in': day_data['total'],
                'attendance_rate': rate,
            })

        return Response(trend)


class AdminDepartmentBreakdownView(APIView):
    """Bar chart data: lateness/attendance by department"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        staff = _get_staff(request)
        org = staff.organization if staff else None
        if not org:
            return Response({'error': 'Organization not found for this admin.'}, status=status.HTTP_404_NOT_FOUND)

        days = int(request.query_params.get('days', 30))
        today = date.today()
        start_date = today - timezone.timedelta(days=days - 1)

        staff_qs = StaffProfile.objects.filter(organization=org, is_active=True).select_related('department_fk')
        records = Attendance.objects.filter(
            staff__organization=org, date__range=[start_date, today]
        ).values('staff_id', 'status')

        # Build per-staff counts in memory — single query above, no loop queries
        staff_stats = {}
        for r in records:
            sid = r['staff_id']
            staff_stats.setdefault(sid, {'present': 0, 'late': 0})
            if r['status'] == 'present':
                staff_stats[sid]['present'] += 1
            elif r['status'] == 'late':
                staff_stats[sid]['late'] += 1

        dept_stats = {}
        for s in staff_qs:
            dept_name = s.department_fk.name if s.department_fk else (s.department or 'General')
            dept_stats.setdefault(dept_name, {'present': 0, 'late': 0, 'staff_count': 0})
            dept_stats[dept_name]['staff_count'] += 1
            stat = staff_stats.get(s.id, {'present': 0, 'late': 0})
            dept_stats[dept_name]['present'] += stat['present']
            dept_stats[dept_name]['late'] += stat['late']

        result = [
            {
                'department': dept,
                'present_count': v['present'],
                'late_count': v['late'],
                'staff_count': v['staff_count'],
            }
            for dept, v in dept_stats.items()
        ]
        result.sort(key=lambda x: x['late_count'], reverse=True)
        return Response(result)


class AdminStaffMonthlyOverviewView(APIView):
    """
    Per-staff monthly overview table: days absent, days late, avg sign-in time, avg work duration.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        staff = _get_staff(request)
        org = staff.organization if staff else None
        if not org:
            return Response({'error': 'Organization not found for this admin.'}, status=status.HTTP_404_NOT_FOUND)

        today = date.today()
        month_start = today.replace(day=1)
        start_str = request.query_params.get('start_date', str(month_start))
        end_str = request.query_params.get('end_date', str(today))
        start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_str, '%Y-%m-%d').date()

        # Working days in range, based on org's working_days config
        working_days_set = set(org.working_days or [0, 1, 2, 3, 4])
        total_working_days = 0
        d = start_date
        while d <= end_date:
            if d.weekday() in working_days_set:
                total_working_days += 1
            d += timezone.timedelta(days=1)

        staff_qs = StaffProfile.objects.filter(organization=org, is_active=True).select_related('user', 'department_fk')

        # One query for all records in range across all staff
        records = list(Attendance.objects.filter(
            staff__organization=org, date__range=[start_date, end_date]
        ).values('staff_id', 'status', 'sign_in_time', 'sign_out_time', 'attendance_grade'))

        by_staff = {}
        for r in records:
            by_staff.setdefault(r['staff_id'], []).append(r)

        overview = []
        for s in staff_qs:
            s_records = by_staff.get(s.id, [])
            days_present = sum(1 for r in s_records if r['status'] in ('present', 'late'))
            days_late = sum(1 for r in s_records if r['status'] == 'late')
            days_absent = max(0, total_working_days - days_present)

            import pytz
            org_tz = pytz.timezone(org.timezone or 'UTC')

            sign_in_seconds = []
            work_durations_hours = []
            for r in s_records:
                if r['sign_in_time']:
                    local = r['sign_in_time'].astimezone(org_tz)
                    sign_in_seconds.append(local.hour * 3600 + local.minute * 60 + local.second)
                if r['sign_in_time'] and r['sign_out_time']:
                    delta = (r['sign_out_time'] - r['sign_in_time']).total_seconds() / 3600
                    work_durations_hours.append(delta)

            avg_sign_in = None
            if sign_in_seconds:
                avg_sec = sum(sign_in_seconds) / len(sign_in_seconds)
                avg_sign_in = f"{int(avg_sec // 3600):02d}:{int((avg_sec % 3600) // 60):02d}"

            avg_work_hours = round(sum(work_durations_hours) / len(work_durations_hours), 1) if work_durations_hours else None

            grades = [r['attendance_grade'] for r in s_records if r['attendance_grade'] is not None]
            avg_grade = round(sum(grades) / len(grades), 2) if grades else None

            overview.append({
                'staff_id': s.id,
                'staff_name': str(s),
                'department': s.department_fk.name if s.department_fk else (s.department or 'General'),
                'days_present': days_present,
                'days_absent': days_absent,
                'days_late': days_late,
                'average_sign_in_time': avg_sign_in,
                'average_work_hours': avg_work_hours,
                'average_attendance_grade': avg_grade,
            })

        overview.sort(key=lambda x: x['days_late'], reverse=True)
        return Response({
            'start_date': str(start_date),
            'end_date': str(end_date),
            'total_working_days': total_working_days,
            'staff': overview,
        })


class AdminAttendanceTableView(APIView):
    """Filterable full attendance table for admin"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        staff = _get_staff(request)
        org = staff.organization if staff else None
        if not org:
            return Response({'error': 'Organization not found for this admin.'}, status=status.HTTP_404_NOT_FOUND)

        qs = Attendance.objects.filter(staff__organization=org).select_related('staff__user', 'staff__department_fk')

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        department = request.query_params.get('department')
        staff_id = request.query_params.get('staff_id')

        if start_date:
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)
        if department:
            qs = qs.filter(staff__department_fk__name=department)
        if staff_id:
            qs = qs.filter(staff_id=staff_id)

        qs = qs.order_by('-date', 'staff__user__first_name')[:500]
        return Response(AttendanceSerializer(qs, many=True).data)


class AdminLiveTodayView(APIView):
    """'Who's in today' live list"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        staff = _get_staff(request)
        org = staff.organization if staff else None
        if not org:
            return Response({'error': 'Organization not found for this admin.'}, status=status.HTTP_404_NOT_FOUND)

        today_records = Attendance.objects.filter(
            staff__organization=org, date=date.today()
        ).select_related('staff__user', 'staff__department_fk').order_by('sign_in_time')

        return Response(AttendanceSerializer(today_records, many=True).data)
