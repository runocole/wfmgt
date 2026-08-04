from datetime import date, timedelta, datetime, time
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.db.models import Sum, Count
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.http import HttpResponse
from django.conf import settings
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
import random
import string
import csv
import json
import traceback

from .models import (
    App, Subscription, UserProfile, StaffProfile, WorkLog,
    DailyMetric, Leave, Query, PublicHoliday, DeletedLog
)
from .serializers import (
    AppSerializer, UserSerializer, SubscriptionSerializer,
    SubscriptionCreateSerializer, LoginResponseSerializer,
    StaffProfileSerializer, WorkLogSerializer, DailyMetricSerializer,
    LeaveSerializer, StaffDashboardSerializer, StaffRankingSerializer,
    AdminSummarySerializer, WeeklyTrendSerializer
)

# ============================================
# AUTH VIEWS
# ============================================

class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username')
        email = request.data.get('email')
        password = request.data.get('password')

        if not username or not email or not password:
            return Response(
                {'error': 'Please provide username, email, and password'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username already exists'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email=email).exists():
            return Response({'error': 'Email already exists'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(username=username, email=email, password=password)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    # FIX: Returns a real JWT token instead of the dummy 'dummy-token-{id}'
    # that was causing all subsequent requests to return 401 Unauthorized,
    # which made the frontend crash with "A.find is not a function".
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username_or_email = request.data.get('username') or request.data.get('email')
        password = request.data.get('password')

        if not username_or_email or not password:
            return Response(
                {'error': 'Please provide username/email and password'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = None
        if '@' in username_or_email:
            try:
                user_obj = User.objects.get(email=username_or_email)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
        else:
            user = authenticate(username=username_or_email, password=password)

        if user:
            login(request, user)
            refresh = RefreshToken.for_user(user)
            return Response({
                'user': UserSerializer(user).data,
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            })

        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except Exception:
            pass
        logout(request)
        return Response({'message': 'Logged out successfully'})


class CurrentUserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        data = UserSerializer(request.user).data
        data['role'] = 'admin' if request.user.is_staff else 'staff'
        return Response(data)


# ============================================
# APP VIEWS
# ============================================

class AppListView(generics.ListAPIView):
    queryset = App.objects.all()
    serializer_class = AppSerializer
    permission_classes = [permissions.AllowAny]


class AppDetailView(generics.RetrieveAPIView):
    queryset = App.objects.all()
    serializer_class = AppSerializer
    permission_classes = [permissions.AllowAny]


# ============================================
# SUBSCRIPTION VIEWS
# ============================================

class UserSubscriptionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        subscriptions = Subscription.objects.filter(user=request.user)
        return Response(SubscriptionSerializer(subscriptions, many=True).data)

    def post(self, request):
        serializer = SubscriptionCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            app = App.objects.get(id=serializer.validated_data['app_id'])
            plan = serializer.validated_data['plan']
            price_map = {
                'individual': app.individual_price,
                'team': app.team_price,
                'enterprise': app.enterprise_price,
            }
            subscription = Subscription.objects.create(
                user=request.user, app=app, plan=plan,
                status='pending', amount_paid=price_map[plan]
            )
            return Response(SubscriptionSerializer(subscription).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SubscriptionPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, subscription_id):
        try:
            subscription = Subscription.objects.get(
                id=subscription_id, user=request.user, status='pending'
            )
            subscription.status = 'active'
            subscription.transaction_id = f"TXN_{subscription.id}_{timezone.now().timestamp()}"
            subscription.start_date = timezone.now()
            subscription.end_date = timezone.now() + timedelta(days=30)
            subscription.save()
            return Response(SubscriptionSerializer(subscription).data)
        except Subscription.DoesNotExist:
            return Response({'error': 'Subscription not found'}, status=status.HTTP_404_NOT_FOUND)


class CheckAppAccessView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, app_id):
        try:
            subscription = Subscription.objects.get(
                user=request.user, app_id=app_id, status='active'
            )
            return Response({'has_access': True, 'subscription': SubscriptionSerializer(subscription).data})
        except Subscription.DoesNotExist:
            return Response({'has_access': False})


class UserSubscriptionsListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        subscriptions = Subscription.objects.filter(user=request.user)
        return Response(SubscriptionSerializer(subscriptions, many=True).data)


# ============================================
# WORK LOG SYSTEM VIEWS
# ============================================

class StaffProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile, created = StaffProfile.objects.get_or_create(
            user=request.user,
            defaults={'expected_hours_per_day': 8.00, 'is_active': True}
        )
        return Response(StaffProfileSerializer(profile).data)

    def patch(self, request):
        profile = StaffProfile.objects.get(user=request.user)
        serializer = StaffProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class WorkLogListCreateView(generics.ListCreateAPIView):
    serializer_class = WorkLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        date_param = self.request.query_params.get('date')
        qs = WorkLog.objects.filter(staff__user=self.request.user)
        if date_param:
            qs = qs.filter(date=date_param)
        return qs.order_by('-date', '-created_at')

    def perform_create(self, serializer):
        staff = StaffProfile.objects.get(user=self.request.user)
        serializer.save(staff=staff)


class WorkLogDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = WorkLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return WorkLog.objects.filter(staff__user=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.is_locked:
            raise PermissionError("Cannot edit locked entries")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.is_locked:
            raise PermissionError("Cannot delete locked entries")
        instance.delete()


class TeamWorkLogsView(generics.ListAPIView):
    serializer_class = WorkLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        date_param = self.request.query_params.get('date', str(date.today()))
        return WorkLog.objects.filter(date=date_param).select_related('staff__user').order_by('staff__user__username', '-created_at')


class TodayWorkLogsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = date.today()
        logs = WorkLog.objects.filter(date=today).select_related('staff__user')
        result = []
        for staff in StaffProfile.objects.filter(is_active=True):
            staff_logs = logs.filter(staff=staff)
            if staff_logs.exists():
                total_hours = sum(float(log.hours) for log in staff_logs)
                result.append({
                    'staff_id': staff.id,
                    'staff_name': str(staff),
                    'logs': WorkLogSerializer(staff_logs, many=True).data,
                    'total_hours': round(total_hours, 2),
                })
        return Response(result)


class StaffDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        import calendar
        staff = StaffProfile.objects.get(user=request.user)
        today = date.today()
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        if start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                start_date = today.replace(day=1)
                end_date = today
        else:
            start_date = today.replace(day=1)
            end_date = today
        logs_in_range = WorkLog.objects.filter(staff=staff, date__range=[start_date, end_date])
        total_days_worked = logs_in_range.values('date').distinct().count()
        total_hours_worked = float(logs_in_range.aggregate(total=Sum("hours"))["total"] or 0)
        month_start = today.replace(day=1)
        month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        # Fast working days calc — no loops
        import calendar as cal_mod
        _, month_days = cal_mod.monthrange(today.year, today.month)
        first_weekday = month_start.weekday()  # 0=Mon
        working_days = sum(1 for d in range(month_days) if (first_weekday + d) % 7 < 5)
        expected_hours = working_days * float(staff.expected_hours_per_day)
        deficit = max(0, expected_hours - total_hours_worked)
        surplus = max(0, total_hours_worked - expected_hours)
        elapsed = (today - month_start).days + 1
        elapsed_working_days = sum(1 for d in range(elapsed) if (first_weekday + d) % 7 < 5)
        attendance_rate = (total_days_worked / elapsed_working_days * 100) if elapsed_working_days > 0 else 0
        avg_hours = total_hours_worked / total_days_worked if total_days_worked > 0 else 0
        # Fetch recent logs with only needed fields — no full serializer
        recent_logs_qs = WorkLog.objects.filter(staff=staff).order_by('-date', '-created_at').values(
            'id', 'date', 'start_time', 'end_time', 'description', 'hours', 'status', 'is_locked', 'created_at'
        )[:10]
        recent_logs_data = []
        for log in recent_logs_qs:
            recent_logs_data.append({
                'id': log['id'],
                'date': str(log['date']),
                'startTime': str(log['start_time'])[:5] if log['start_time'] else None,
                'endTime': str(log['end_time'])[:5] if log['end_time'] else None,
                'description': log['description'],
                'hours': float(log['hours']),
                'status': log['status'],
                'is_locked': log['is_locked'],
                'created_at': log['created_at'].isoformat() if log['created_at'] else None,
            })
        return Response({
            'total_days_worked': total_days_worked,
            'total_hours_worked': total_hours_worked,
            'expected_hours': expected_hours,
            'deficit': round(deficit, 1),
            'surplus': round(surplus, 1),
            'attendance_rate': round(attendance_rate, 1),
            'average_hours_per_day': round(avg_hours, 1),
            'recent_logs': recent_logs_data,
        })

class StaffListView(generics.ListAPIView):
    serializer_class = StaffProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return StaffProfile.objects.filter(is_active=True).select_related('user')


class LeaveListCreateView(generics.ListCreateAPIView):
    serializer_class = LeaveSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Leave.objects.filter(staff__user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        staff = StaffProfile.objects.get(user=self.request.user)
        serializer.save(staff=staff, status='pending')


class LeaveDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LeaveSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Leave.objects.filter(staff__user=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.status != 'pending':
            raise PermissionError("Cannot update non-pending requests")
        serializer.save()


# ============================================
# ADMIN VIEWS
# ============================================

class AdminStaffListView(generics.ListAPIView):
    serializer_class = StaffProfileSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return StaffProfile.objects.all().select_related('user')


class AdminRankingView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
        today = date.today()
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        if start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                start_date = today - timedelta(days=7)
                end_date = today
        else:
            start_date = today - timedelta(days=7)
            end_date = today

        holidays = set(PublicHoliday.objects.filter(
            date__range=[start_date, end_date]
        ).values_list('date', flat=True))
        working_days = 0
        current = start_date
        while current <= end_date:
            if current.weekday() < 5 and current not in holidays:
                working_days += 1
            current += timedelta(days=1)
        expected_hours = working_days * 8

        rankings = []
        for staff in StaffProfile.objects.filter(is_active=True).select_related('user'):
            logs = WorkLog.objects.filter(staff=staff, date__range=[start_date, end_date])
            total_hours = float(logs.aggregate(Sum('hours'))['hours__sum'] or 0)
            total_days = logs.values('date').distinct().count()
            absent_days = 0
            c = start_date
            while c <= end_date:
                if c.weekday() < 5 and c not in holidays:
                    if not logs.filter(date=c).exists():
                        if not Leave.objects.filter(staff=staff, status='approved', start_date__lte=c, end_date__gte=c).exists():
                            absent_days += 1
                c += timedelta(days=1)
            deficit = round(max(0, expected_hours - total_hours), 1)
            surplus = round(max(0, total_hours - expected_hours), 1)
            rankings.append({
                'staff_id': staff.user.id,
                'staff_name': str(staff),
                'department': staff.department or 'General',
                'total_hours': total_hours,
                'total_days': total_days,
                'days_absent': absent_days,
                'average_hours': round(total_hours / total_days, 2) if total_days > 0 else 0,
                'deficit': deficit,
                'surplus': surplus,
            })
        rankings.sort(key=lambda x: x['total_hours'], reverse=True)
        return Response({'start_date': str(start_date), 'end_date': str(end_date), 'rankings': rankings})

class AdminSummaryView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        today_date = date.today()
        total_staff = StaffProfile.objects.filter(is_active=True).count()

        today_logs = WorkLog.objects.filter(date=today_date)
        active_today = today_logs.values('staff').distinct().count()
        total_hours_today = sum(float(log.hours) for log in today_logs)

        week_logs = WorkLog.objects.filter(date__range=[today_date - timedelta(days=7), today_date])
        total_hours_week = sum(float(log.hours) for log in week_logs)

        month_logs = WorkLog.objects.filter(date__range=[today_date - timedelta(days=30), today_date])
        total_hours_month = sum(float(log.hours) for log in month_logs)

        weekly_trend = []
        for i in range(7):
            day = today_date - timedelta(days=i)
            day_logs = WorkLog.objects.filter(date=day)
            weekly_trend.append({
                'date': day,
                'day_name': day.strftime('%A'),
                'total_hours': round(sum(float(l.hours) for l in day_logs), 1),
                'staff_count': day_logs.values('staff').distinct().count(),
            })

        return Response({
            'total_staff': total_staff,
            'active_today': active_today,
            'present_today': active_today,
            'attendance_rate': round((active_today / total_staff * 100) if total_staff > 0 else 0, 1),
            'total_hours_today': round(total_hours_today, 1),
            'total_hours_week': round(total_hours_week, 1),
            'total_hours_month': round(total_hours_month, 1),
            'weekly_trend': weekly_trend,
        })


class AdminWorkLogsView(generics.ListAPIView):
    serializer_class = WorkLogSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        qs = WorkLog.objects.all().select_related('staff__user')
        staff_id = self.request.query_params.get('staff')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        locked = self.request.query_params.get('locked')

        if staff_id and staff_id not in ('all', 'undefined'):
            qs = qs.filter(staff_id=staff_id)
        if start_date and start_date != 'undefined':
            qs = qs.filter(date__gte=start_date)
        if end_date and end_date != 'undefined':
            qs = qs.filter(date__lte=end_date)
        if locked is not None:
            qs = qs.filter(is_locked=locked.lower() == 'true')
        return qs.order_by('-date', '-created_at')


class AdminLeaveRequestsView(generics.ListAPIView):
    serializer_class = LeaveSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        qs = Leave.objects.all().select_related('staff__user')
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.order_by('-created_at')


class AdminApproveLeaveView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, leave_id):
        try:
            leave = Leave.objects.get(id=leave_id, status='pending')
            action = request.data.get('action')

            if action in ['approve', 'approved']:
                leave.status = 'approved'
                leave.approved_by = request.user
                leave.approved_at = timezone.now()
                self._create_leave_work_logs(leave)
            elif action in ['reject', 'rejected']:
                leave.status = 'rejected'
            else:
                return Response({'error': 'Invalid action. Use "approve" or "reject"'}, status=status.HTTP_400_BAD_REQUEST)

            leave.save()
            return Response(LeaveSerializer(leave).data)
        except Leave.DoesNotExist:
            return Response({'error': 'Leave request not found'}, status=status.HTTP_404_NOT_FOUND)

    def _create_leave_work_logs(self, leave):
        current_date = leave.start_date
        descriptions = {
            'sick': 'Sick Leave',
            'vacation': 'Vacation Leave',
            'permission': 'Permission - Official',
            'other': 'Approved Leave',
            'work_related': 'Work-Related Absence',
        }
        description = descriptions.get(leave.leave_type, 'Approved Leave')
        expected_hours = float(leave.staff.expected_hours_per_day or 8.00)

        while current_date <= leave.end_date:
            if not WorkLog.objects.filter(staff=leave.staff, date=current_date).exists():
                WorkLog.objects.create(
                    staff=leave.staff,
                    date=current_date,
                    description=description,
                    hours=expected_hours,
                    status='completed',
                    is_locked=True,
                    start_time=time(8, 0),
                    end_time=time(17, 0),
                )
            current_date += timedelta(days=1)


class AdminSetupView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        profile, _ = StaffProfile.objects.get_or_create(user=request.user)
        profile.save()
        return Response({'status': 'success'})


class AdminCreateStaffView(APIView):
    permission_classes = [IsAdminUser]

    def _generate_password(self):
        letters = ''.join(random.choices(string.ascii_uppercase, k=2))
        numbers = ''.join(random.choices(string.digits, k=3))
        return f"OTIC{letters}{numbers}"

    def _send_welcome_email(self, user, password, role):
        subject = 'Welcome to OTIC Workforce - Your Account Details'
        html_message = f"""
        <html><body>
        <h2>Welcome to OTIC Workforce!</h2>
        <p>Hello <strong>{user.first_name} {user.last_name}</strong>,</p>
        <p>Your account has been created:</p>
        <ul>
            <li><strong>Username:</strong> {user.username}</li>
            <li><strong>Email:</strong> {user.email}</li>
            <li><strong>Password:</strong> {password}</li>
            <li><strong>Role:</strong> {role.title()}</li>
        </ul>
        <p>Login at: <a href="https://oticgs.com/workforce">https://oticgs.com/workforce</a></p>
        </body></html>
        """
        try:
            send_mail(subject, strip_tags(html_message), settings.DEFAULT_FROM_EMAIL,
                      [user.email], html_message=html_message, fail_silently=False)
            return True
        except Exception as e:
            print(f"Email failed: {e}")
            return False

    def post(self, request):
        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        email = request.data.get('email')
        department = request.data.get('department', 'General')
        role = request.data.get('role', 'staff')

        if not first_name or not last_name or not email:
            return Response({'error': 'First name, last name, and email are required'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email=email).exists():
            return Response({'error': f'User with email {email} already exists'}, status=status.HTTP_400_BAD_REQUEST)

        username = email.split('@')[0]
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        password = self._generate_password()

        try:
            user = User.objects.create_user(
                username=username, email=email, password=password,
                first_name=first_name, last_name=last_name,
                is_staff=(role == 'admin'), is_superuser=(role == 'admin')
            )
            staff_profile = StaffProfile.objects.create(
                user=user, department=department,
                expected_hours_per_day=8.00, is_active=True,
                employee_id=f"EMP{random.randint(1000, 9999)}"
            )
            self._send_welcome_email(user, password, role)
            return Response({
                'id': user.id, 'username': user.username, 'email': user.email,
                'first_name': user.first_name, 'last_name': user.last_name,
                'department': staff_profile.department, 'role': role, 'password': password,
                'message': f'Staff {first_name} {last_name} created successfully!'
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminExportView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        try:
            staff_id = request.query_params.get('staff')
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')

            qs = WorkLog.objects.all().select_related('staff__user')
            if staff_id and staff_id not in ('all', 'undefined'):
                qs = qs.filter(staff__user__id=staff_id)
            if start_date and start_date != 'undefined':
                qs = qs.filter(date__gte=start_date)
            if end_date and end_date != 'undefined':
                qs = qs.filter(date__lte=end_date)
            qs = qs.order_by('-date', 'staff__user__username')

            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="worklogs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
            writer = csv.writer(response)
            writer.writerow(['Staff Name', 'Department', 'Date', 'Start Time', 'End Time', 'Description', 'Hours', 'Status', 'Locked'])
            for log in qs:
                writer.writerow([
                    str(log.staff),
                    getattr(log.staff, 'department', 'General'),
                    log.date,
                    log.start_time.strftime('%H:%M') if log.start_time else '',
                    log.end_time.strftime('%H:%M') if log.end_time else '',
                    log.description, float(log.hours), log.status,
                    'Yes' if log.is_locked else 'No',
                ])
            return response
        except Exception as e:
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================
# ABSENCES
# ============================================

class AdminAbsencesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
        # Return approved sick/permission leaves only
        leaves = Leave.objects.filter(
            status='approved',
            leave_type__in=['sick', 'permission']
        ).select_related('staff')
        absences = []
        for leave in leaves:
            current = leave.start_date
            while current <= leave.end_date:
                absences.append({
                    'staff_id': leave.staff.id,
                    'staff_name': str(leave.staff),
                    'department': leave.staff.department,
                    'date': str(current),
                    'leave_type': leave.leave_type,
                    'reason': leave.reason or '',
                })
                current += timedelta(days=1)
        return Response(absences)


class MyAbsenceDatesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            staff = StaffProfile.objects.get(user=request.user)
        except StaffProfile.DoesNotExist:
            return Response([])
        # Return approved sick/permission leaves for this staff member
        leaves = Leave.objects.filter(
            staff=staff,
            status='approved',
            leave_type__in=['sick', 'permission']
        )
        absences = []
        for leave in leaves:
            current = leave.start_date
            while current <= leave.end_date:
                absences.append({
                    'date': str(current),
                    'leave_type': leave.leave_type,
                    'reason': leave.reason or '',
                })
                current += timedelta(days=1)
        return Response(absences)


# ============================================
# QUERIES
# ============================================

def _serialize_query(q):
    return {
        'id': q.id,
        'staff_id': q.staff_id,
        'staff_name': str(q.staff),
        'work_log_id': q.work_log_id,
        'admin_note': q.admin_note,
        'staff_response': q.staff_response,
        'status': q.status,
        'work_log_date_snapshot': str(q.work_log_date_snapshot) if q.work_log_date_snapshot else None,
        'work_log_start_time_snapshot': str(q.work_log_start_time_snapshot) if q.work_log_start_time_snapshot else None,
        'work_log_end_time_snapshot': str(q.work_log_end_time_snapshot) if q.work_log_end_time_snapshot else None,
        'work_log_description_snapshot': q.work_log_description_snapshot,
        'created_at': q.created_at.isoformat(),
        'responded_at': q.responded_at.isoformat() if q.responded_at else None,
        'resolved_at': q.resolved_at.isoformat() if q.resolved_at else None,
    }


def _serialize_queries(queries):
    return [_serialize_query(q) for q in queries]


class AdminQueryListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
        queries = Query.objects.all().select_related('staff__user', 'work_log').order_by('-created_at')
        status_filter = request.query_params.get('status')
        if status_filter:
            queries = queries.filter(status=status_filter)
        return Response(_serialize_queries(queries))


class AdminCreateQueryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
        staff_id = request.data.get('staff_id')
        work_log_id = request.data.get('work_log_id')
        admin_note = request.data.get('admin_note', '')
        work_log = None
        if work_log_id:
            try:
                work_log = WorkLog.objects.get(pk=work_log_id)
            except WorkLog.DoesNotExist:
                pass
        # Get staff from work_log if staff_id not provided
        if staff_id:
            try:
                staff = StaffProfile.objects.get(pk=staff_id)
            except StaffProfile.DoesNotExist:
                return Response({'error': 'Staff not found.'}, status=status.HTTP_404_NOT_FOUND)
        elif work_log:
            staff = work_log.staff
        else:
            return Response({'error': 'staff_id or work_log_id required.'}, status=status.HTTP_400_BAD_REQUEST)
        query = Query.objects.create(
            staff=staff, work_log=work_log, admin_note=admin_note,
            work_log_date_snapshot=work_log.date if work_log else None,
            work_log_start_time_snapshot=work_log.start_time if work_log else None,
            work_log_end_time_snapshot=work_log.end_time if work_log else None,
            work_log_description_snapshot=work_log.description if work_log else None,
        )
        return Response(_serialize_query(query), status=status.HTTP_201_CREATED)


class AdminResolveQueryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, query_id):
        if not request.user.is_staff:
            return Response({'error': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            query = Query.objects.get(pk=query_id)
        except Query.DoesNotExist:
            return Response({'error': 'Query not found.'}, status=status.HTTP_404_NOT_FOUND)
        action = request.data.get('action')
        if action == 'accept':
            query.status = 'accepted'
        elif action == 'reject':
            # Save to DeletedLog before deleting the work log entry
            if query.work_log:
                log = query.work_log
                DeletedLog.objects.create(
                    staff_name=str(log.staff),
                    staff_id=log.staff.id,
                    department=log.staff.department if hasattr(log.staff, 'department') else '',
                    date=log.date,
                    start_time=log.start_time,
                    end_time=log.end_time,
                    description=log.description,
                    hours=log.hours,
                    status=log.status,
                    deleted_by='query_reject',
                )
                log.delete()
                query.work_log = None
            query.status = 'rejected'
        else:
            return Response({'error': 'Action must be accept or reject.'}, status=status.HTTP_400_BAD_REQUEST)
        query.resolved_at = timezone.now()
        query.save()
        return Response(_serialize_query(query))


class StaffQueryListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            staff = StaffProfile.objects.get(user=request.user)
        except StaffProfile.DoesNotExist:
            return Response([])
        queries = Query.objects.filter(staff=staff).order_by('-created_at')
        return Response(_serialize_queries(queries))


class StaffRespondQueryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, query_id):
        try:
            staff = StaffProfile.objects.get(user=request.user)
            query = Query.objects.get(pk=query_id, staff=staff)
        except (StaffProfile.DoesNotExist, Query.DoesNotExist):
            return Response({'error': 'Query not found.'}, status=status.HTTP_404_NOT_FOUND)
        response_text = request.data.get('staff_response', '')
        if not response_text:
            return Response({'error': 'Response text is required.'}, status=status.HTTP_400_BAD_REQUEST)
        query.staff_response = response_text
        query.status = 'responded'
        query.responded_at = timezone.now()
        query.save()
        return Response(_serialize_query(query))


class DeletedLogsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
        logs = DeletedLog.objects.all().order_by('-deleted_at')[:200]
        return Response([{
            'id': l.id, 'staff_name': l.staff_name, 'staff_id': l.staff_id,
            'department': l.department, 'date': str(l.date),
            'start_time': str(l.start_time) if l.start_time else None,
            'end_time': str(l.end_time) if l.end_time else None,
            'description': l.description, 'hours': float(l.hours),
            'status': l.status, 'deleted_at': l.deleted_at.isoformat(),
            'deleted_by': l.deleted_by,
        } for l in logs])


# ============================================
# PUBLIC HOLIDAYS
# ============================================

class PublicHolidayListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        holidays = PublicHoliday.objects.all().order_by('date')
        return Response([{'id': h.id, 'date': str(h.date), 'name': h.name} for h in holidays])

    def post(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Admin access required.'}, status=status.HTTP_403_FORBIDDEN)
        holiday_date = request.data.get('date')
        name = request.data.get('name', '')
        if not holiday_date:
            return Response({'error': 'Date is required.'}, status=status.HTTP_400_BAD_REQUEST)
        h, created = PublicHoliday.objects.get_or_create(date=holiday_date, defaults={'name': name})
        return Response(
            {'id': h.id, 'date': str(h.date), 'name': h.name},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


import json
from django.http import JsonResponse

from django.views.decorators.csrf import csrf_exempt
@csrf_exempt
def bulk_delete_worklogs(request):
    """Bulk delete work log entries - JWT auth"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        from rest_framework_simplejwt.authentication import JWTAuthentication
        jwt_auth = JWTAuthentication()
        validated = jwt_auth.authenticate(request)
        if not validated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        user, _ = validated
        # Debug
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"BULK DELETE: user={user.username} is_staff={user.is_staff} is_superuser={user.is_superuser}")
        if not user.is_staff and not user.is_superuser:
            return JsonResponse({'error': f'Permission denied for {user.username} is_staff={user.is_staff}'}, status=403)
        data = json.loads(request.body)
        ids = data.get('ids', [])
        if not ids:
            return JsonResponse({'error': 'No IDs provided'}, status=400)
        from .models import DeletedLog
        logs_to_delete = WorkLog.objects.filter(id__in=ids).select_related('staff')
        for log in logs_to_delete:
            DeletedLog.objects.create(
                staff_name=str(log.staff),
                staff_id=log.staff.id,
                department=log.staff.department if hasattr(log.staff, 'department') else '',
                date=log.date,
                start_time=log.start_time,
                end_time=log.end_time,
                description=log.description,
                hours=log.hours,
                status=log.status,
                deleted_by=user.get_full_name() or user.username,
            )
        deleted_count = WorkLog.objects.filter(id__in=ids).delete()[0]
        return JsonResponse({'success': True, 'deleted': deleted_count})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ============================================
# KPI & AI ANALYSIS VIEWS
# ============================================

class DepartmentKPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        department = request.query_params.get('department')
        from .models import DepartmentKPI
        qs = DepartmentKPI.objects.all()
        if department:
            qs = qs.filter(department=department)
        return Response([{
            'id': k.id, 'department': k.department, 'metric_name': k.metric_name,
            'weight': k.weight, 'description': k.description, 'perspective': k.perspective,
        } for k in qs])

    def post(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
        from .models import DepartmentKPI
        data = request.data
        kpi = DepartmentKPI.objects.create(
            department=data.get('department'),
            metric_name=data.get('metric_name'),
            weight=data.get('weight', 20),
            description=data.get('description', ''),
            perspective=data.get('perspective', 'Internal Process'),
        )
        return Response({'id': kpi.id, 'metric_name': kpi.metric_name}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
        from .models import DepartmentKPI
        kpi_id = request.query_params.get('id')
        DepartmentKPI.objects.filter(id=kpi_id).delete()
        return Response({'success': True})


class GeneratePerformanceReportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

        from .models import DepartmentKPI, PerformanceReport
        import json
        from groq import Groq

        staff_user_id = request.data.get('staff_id')
        period_start = request.data.get('period_start')
        period_end = request.data.get('period_end')

        if not all([staff_user_id, period_start, period_end]):
            return Response({'error': 'staff_id, period_start, period_end required'}, status=400)

        try:
            staff = StaffProfile.objects.get(user__id=staff_user_id)
        except StaffProfile.DoesNotExist:
            return Response({'error': 'Staff not found'}, status=404)

        kpis = DepartmentKPI.objects.filter(department=staff.department)
        if not kpis.exists():
            return Response({'error': f'No KPIs found for {staff.department}. Add KPIs in Settings first.'}, status=400)

        # Strict date filtering — ONLY entries within the exact period
        start_d = datetime.strptime(period_start, '%Y-%m-%d').date()
        end_d = datetime.strptime(period_end, '%Y-%m-%d').date()

        logs = WorkLog.objects.filter(
            staff=staff,
            date__gte=start_d,
            date__lte=end_d,
        ).order_by('date', 'start_time')

        if not logs.exists():
            return Response({'error': f'No log entries found for this period ({period_start} to {period_end})'}, status=400)

        # Build detailed log text — keep individual entries, not compressed
        # Limit to 180 entries max to stay within token limits
        log_list = list(logs.values('date', 'start_time', 'end_time', 'description', 'hours'))
        if len(log_list) > 25:
            log_list = log_list[:25]

        log_lines = []
        for l in log_list:
            start_str = str(l['start_time'])[:5] if l['start_time'] else '??:??'
            end_str = str(l['end_time'])[:5] if l['end_time'] else '??:??'
            log_lines.append(f"{l['date']} {start_str}-{end_str}: {(l['description'] or '')[:45]}")

        total_hours = float(logs.aggregate(total=Sum('hours'))['total'] or 0)
        total_days = logs.values('date').distinct().count()

        month_days = (end_d - start_d).days + 1
        working_days = sum(1 for i in range(month_days) if (start_d + timedelta(days=i)).weekday() < 5)
        expected_hours = working_days * float(staff.expected_hours_per_day)
        surplus_deficit = f"Surplus {round(total_hours - expected_hours, 1)}h" if total_hours >= expected_hours else f"Deficit {round(expected_hours - total_hours, 1)}h"
        period_label = start_d.strftime('%B %Y')

        kpi_list = '\n'.join([f"- {k.metric_name} (Weight: {k.weight}%, Perspective: {k.perspective}): {k.description}" for k in kpis])
        log_text = '\n'.join(log_lines)

        prompt = f"""You are a strict HR performance analyst for OTIC Geosystems, a geospatial and survey technology company in Lagos, Nigeria.

CRITICAL: You are analyzing ONLY the period {period_start} to {period_end} ({period_label}). Do NOT reference any activities outside this date range.

STAFF: {str(staff)}
DEPARTMENT: {staff.department}
REPORTING PERIOD: {period_label} ({period_start} to {period_end})
TOTAL HOURS LOGGED: {total_hours}h
EXPECTED HOURS: {expected_hours}h ({working_days} working days x 8h)
DAYS WITH ENTRIES: {total_days}
STATUS: {surplus_deficit}

KPI FRAMEWORK FOR {staff.department.upper()}:
{kpi_list}

WORK LOG ENTRIES FOR {period_label.upper()} ONLY ({len(log_lines)} entries):
{log_text}

Generate a comprehensive JSON performance report. Return ONLY valid JSON — no markdown, no explanation, no preamble.

{{
  "staff_name": "{str(staff)}",
  "department": "{staff.department}",
  "period": "{period_label}",
  "period_start": "{period_start}",
  "period_end": "{period_end}",
  "total_hours": {total_hours},
  "expected_hours": {expected_hours},
  "days_worked": {total_days},
  "kpi_evaluations": [
    {{
      "metric_name": "exact name from KPI framework",
      "perspective": "exact perspective from KPI framework",
      "weight": 20,
      "activities_observed": "List specific entries with dates that relate to this KPI. Be exhaustive — cite every relevant log entry you found. Include dates.",
      "evaluation": "Outstanding|Exceeds Expectations|Meets Expectations|Below Expectations|Unsatisfactory",
      "analysis": "3-4 sentences. Cite specific work done with dates. Explain your score. Be detailed.",
      "score": 18
    }}
  ],
  "total_kpi_score": 90,
  "max_kpi_score": 100,
  "attendance_analysis": "Detailed paragraph on attendance patterns, consistency, early starts, late finishes, CDS days, any absences. Reference specific dates.",
  "performance_summary": "Write 4+ paragraphs. Cover ALL significant contributions found in the logs. Group by theme. Mention specific projects, technologies, problems solved, and dates. This should read like a thorough professional review that someone spent time on — not a summary.",
  "recommendations": [
    "A specific, actionable recommendation based on what you observed in the logs — could be growth area, skill to develop, or area to maintain",
    "Another specific recommendation",
    "A third specific recommendation"
  ],
  "overall_rating": "Exceptional|Very Good|Good|Fair|Poor",
  "overall_score": 90.0
}}

RULES:
1. ONLY analyze entries dated between {period_start} and {period_end}. Never mention work from other months.
2. Score each KPI out of its weight value (20% weight = score out of 20).
3. overall_score = (total_kpi_score / max_kpi_score) * 100
4. Recommendations must be about what the STAFF MEMBER should do — not management actions.
5. Be thorough. A human HR reviewer would miss things. You should not."""

        from decouple import config
        client = Groq(api_key=config('GROQ_API_KEY'))
        message = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            max_tokens=4096,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = message.choices[0].message.content.strip()
        if raw.startswith('```'):
            raw = '\n'.join(raw.split('\n')[1:])
        if raw.endswith('```'):
            raw = raw.rsplit('```', 1)[0]
        raw = raw.strip()
        # Remove invalid control characters that break JSON parsing
        import re
        raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', raw)

        report_data = json.loads(raw)

        report = PerformanceReport.objects.create(
            staff=staff,
            period_start=start_d,
            period_end=end_d,
            report_data=report_data,
            generated_by=request.user,
        )

        return Response({'report_id': report.id, 'report': report_data})


class GetPerformanceReportsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_staff:
            return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
        from .models import PerformanceReport
        staff_id = request.query_params.get('staff_id')
        qs = PerformanceReport.objects.all()
        if staff_id:
            qs = qs.filter(staff__user__id=staff_id)
        return Response([{
            'id': r.id,
            'staff_name': str(r.staff),
            'period_start': str(r.period_start),
            'period_end': str(r.period_end),
            'overall_rating': r.report_data.get('overall_rating', ''),
            'overall_score': r.report_data.get('overall_score', 0),
            'generated_at': r.generated_at.isoformat(),
            'report': r.report_data,
        } for r in qs])

