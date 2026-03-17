from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.db.models import Sum, Count
from datetime import date, timedelta, datetime, time
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.http import HttpResponse
from django.conf import settings
from rest_framework.permissions import IsAdminUser
import random
import string
import csv
import json
import traceback

from .models import (
    App, Subscription, StaffProfile, WorkLog, DailyMetric, Leave
)
from .serializers import (
    AppSerializer, UserSerializer, SubscriptionSerializer, 
    SubscriptionCreateSerializer, LoginResponseSerializer,
    StaffProfileSerializer, WorkLogSerializer, DailyMetricSerializer,
    LeaveSerializer, StaffDashboardSerializer, StaffRankingSerializer,
    AdminSummarySerializer, WeeklyTrendSerializer
)

# ============================================
# EXISTING AUTH VIEWS
# ============================================

class RegisterView(APIView):
    """Register a new user"""
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
            return Response(
                {'error': 'Username already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if User.objects.filter(email=email).exists():
            return Response(
                {'error': 'Email already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )
        
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED
        )

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        # Accept either username or email
        username_or_email = request.data.get('username') or request.data.get('email')
        password = request.data.get('password')
        
        if not username_or_email or not password:
            return Response(
                {'error': 'Please provide username/email and password'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Try to find user by email first
        user = None
        if '@' in username_or_email:
            # It's an email
            try:
                user_obj = User.objects.get(email=username_or_email)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
        else:
            # It's a username
            user = authenticate(username=username_or_email, password=password)
        
        if user:
            login(request, user)
            return Response({
                'user': UserSerializer(user).data,
                'access': 'dummy-token-' + str(user.id),
            })
        
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )

class LogoutView(APIView):
    """Logout user"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        logout(request)
        return Response({'message': 'Logged out successfully'})

class CurrentUserView(APIView):
    """Get current logged in user"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        return Response(UserSerializer(request.user).data)

# ============================================
# EXISTING APP VIEWS
# ============================================

class AppListView(generics.ListAPIView):
    """List all available apps"""
    queryset = App.objects.all()
    serializer_class = AppSerializer
    permission_classes = [permissions.AllowAny]

class AppDetailView(generics.RetrieveAPIView):
    """Get details of a specific app"""
    queryset = App.objects.all()
    serializer_class = AppSerializer
    permission_classes = [permissions.AllowAny]

# ============================================
# EXISTING SUBSCRIPTION VIEWS
# ============================================

class UserSubscriptionView(APIView):
    """Get user's subscriptions or create new one"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        subscriptions = Subscription.objects.filter(user=request.user)
        serializer = SubscriptionSerializer(subscriptions, many=True)
        return Response(serializer.data)
    
    def post(self, request):
        serializer = SubscriptionCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            app = App.objects.get(id=serializer.validated_data['app_id'])
            plan = serializer.validated_data['plan']
            
            price_map = {
                'individual': app.individual_price,
                'team': app.team_price,
                'enterprise': app.enterprise_price
            }
            
            subscription = Subscription.objects.create(
                user=request.user,
                app=app,
                plan=plan,
                status='pending',
                amount_paid=price_map[plan]
            )
            
            return Response(
                SubscriptionSerializer(subscription).data,
                status=status.HTTP_201_CREATED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SubscriptionPaymentView(APIView):
    """Simulate payment confirmation"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, subscription_id):
        try:
            subscription = Subscription.objects.get(
                id=subscription_id,
                user=request.user,
                status='pending'
            )
            
            subscription.status = 'active'
            subscription.transaction_id = f"TXN_{subscription.id}_{timezone.now().timestamp()}"
            subscription.start_date = timezone.now()
            subscription.end_date = timezone.now() + timezone.timedelta(days=30)
            subscription.save()
            
            return Response(
                SubscriptionSerializer(subscription).data,
                status=status.HTTP_200_OK
            )
            
        except Subscription.DoesNotExist:
            return Response(
                {'error': 'Subscription not found'},
                status=status.HTTP_404_NOT_FOUND
            )

class CheckAppAccessView(APIView):
    """Check if user has access to an app"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, app_id):
        try:
            subscription = Subscription.objects.get(
                user=request.user,
                app_id=app_id,
                status='active'
            )
            
            return Response({
                'has_access': True,
                'subscription': SubscriptionSerializer(subscription).data
            })
            
        except Subscription.DoesNotExist:
            return Response({
                'has_access': False
            })

class UserSubscriptionsListView(APIView):
    """Get all subscriptions for the current user with app details"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        subscriptions = Subscription.objects.filter(user=request.user)
        serializer = SubscriptionSerializer(subscriptions, many=True)
        return Response(serializer.data)

# ============================================
# NEW WORK LOG SYSTEM VIEWS
# ============================================

# -------------------- STAFF PROFILE --------------------

class StaffProfileView(APIView):
    """Get or update current user's staff profile"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        profile, created = StaffProfile.objects.get_or_create(
            user=request.user,
            defaults={
                'expected_hours_per_day': 8.00,
                'is_active': True
            }
        )
        serializer = StaffProfileSerializer(profile)
        return Response(serializer.data)
    
    def patch(self, request):
        profile = StaffProfile.objects.get(user=request.user)
        serializer = StaffProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# -------------------- WORK LOGS --------------------

class WorkLogListCreateView(generics.ListCreateAPIView):
    serializer_class = WorkLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        date_param = self.request.query_params.get('date')
        if date_param:
            return WorkLog.objects.filter(
                staff__user=self.request.user,
                date=date_param
            ).order_by('-created_at')
        return WorkLog.objects.filter(
            staff__user=self.request.user
        ).order_by('-date', '-created_at')
    
    def perform_create(self, serializer):
        staff = StaffProfile.objects.get(user=self.request.user)
        serializer.save(staff=staff)

class WorkLogDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a work log"""
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
    """View all staff work logs (read-only for everyone)"""
    serializer_class = WorkLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        date_param = self.request.query_params.get('date')
        if date_param:
            return WorkLog.objects.filter(
                date=date_param
            ).select_related('staff__user').order_by('staff__user__username', '-created_at')
        
        return WorkLog.objects.filter(
            date=date.today()
        ).select_related('staff__user').order_by('staff__user__username', '-created_at')

class TodayWorkLogsView(APIView):
    """Get today's work logs grouped by staff"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        today = date.today()
        logs = WorkLog.objects.filter(date=today).select_related('staff__user')
        
        result = []
        for staff in StaffProfile.objects.filter(is_active=True):
            staff_logs = logs.filter(staff=staff)
            if staff_logs.exists():
                total_hours = sum(log.hours for log in staff_logs)
                result.append({
                    'staff_id': staff.id,
                    'staff_name': str(staff),
                    'logs': WorkLogSerializer(staff_logs, many=True).data,
                    'total_hours': float(total_hours)
                })
        
        return Response(result)

# -------------------- DASHBOARD --------------------

class StaffDashboardView(APIView):
    """Get dashboard metrics for current staff"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        days = int(request.query_params.get('days', 30))
        staff = StaffProfile.objects.get(user=request.user)
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        logs_in_range = WorkLog.objects.filter(
            staff=staff,
            date__range=[start_date, end_date]
        )
        
        total_days_worked = logs_in_range.values('date').distinct().count()
        total_hours_worked = sum(float(log.hours) for log in logs_in_range)
        
        working_days = 0
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                working_days += 1
            current += timedelta(days=1)
        
        expected_hours = working_days * float(staff.expected_hours_per_day)
        
        deficit = max(0, expected_hours - total_hours_worked)
        surplus = max(0, total_hours_worked - expected_hours)
        attendance_rate = (total_days_worked / working_days * 100) if working_days > 0 else 0
        avg_hours = total_hours_worked / working_days if working_days > 0 else 0
        
        recent_logs = WorkLog.objects.filter(staff=staff).order_by('-date', '-created_at')[:10]
        recent_logs_serialized = WorkLogSerializer(recent_logs, many=True).data
        
        data = {
            'total_days_worked': total_days_worked,
            'total_hours_worked': total_hours_worked,
            'expected_hours': expected_hours,
            'deficit': deficit,
            'surplus': surplus,
            'attendance_rate': round(attendance_rate, 1),
            'average_hours_per_day': round(avg_hours, 1),
            'recent_logs': recent_logs_serialized
        }
        
        return Response(data)
    
class StaffListView(generics.ListAPIView):
    """Get list of all staff (accessible to all authenticated users)"""
    serializer_class = StaffProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return StaffProfile.objects.filter(is_active=True).select_related('user')
    
# -------------------- LEAVE REQUESTS --------------------

class LeaveListCreateView(generics.ListCreateAPIView):
    serializer_class = LeaveSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Leave.objects.filter(staff__user=self.request.user).order_by('-created_at')
    
    def perform_create(self, serializer):
        staff = StaffProfile.objects.get(user=self.request.user)
        serializer.save(staff=staff, status='pending')

class LeaveDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a leave request"""
    serializer_class = LeaveSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Leave.objects.filter(staff__user=self.request.user)
    
    def perform_update(self, serializer):
        if serializer.instance.status != 'pending':
            raise PermissionError("Cannot update non-pending requests")
        serializer.save()

# -------------------- ADMIN ONLY VIEWS --------------------

class AdminStaffListView(generics.ListAPIView):
    """Admin: List all staff profiles"""
    serializer_class = StaffProfileSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        return StaffProfile.objects.all().select_related('user')

class AdminRankingView(APIView):
    """Admin: Staff rankings by hours"""
    permission_classes = [permissions.IsAdminUser]
    
    def get(self, request):
        period = request.query_params.get('period', 'week')
        
        today = date.today()
        if period == 'week':
            start_date = today - timedelta(days=7)
        elif period == 'month':
            start_date = today - timedelta(days=30)
        else:
            start_date = today - timedelta(days=7)
        
        rankings = []
        for staff in StaffProfile.objects.filter(is_active=True):
            logs = WorkLog.objects.filter(
                staff=staff,
                date__range=[start_date, today]
            )
            
            total_hours = sum(float(log.hours) for log in logs)
            total_days = logs.values('date').distinct().count()
            avg_hours = total_hours / total_days if total_days > 0 else 0
            
            rankings.append({
                'staff_id': staff.id,
                'staff_name': str(staff),
                'department': None,
                'total_hours': round(total_hours, 1),
                'total_days': total_days,
                'average_hours': round(avg_hours, 1)
            })
        
        rankings.sort(key=lambda x: x['total_hours'], reverse=True)
        
        return Response({
            'period': period,
            'start_date': start_date,
            'end_date': today,
            'rankings': rankings
        })

class AdminSummaryView(APIView):
    """Admin: Overall stats dashboard"""
    permission_classes = [permissions.IsAdminUser]
    
    def get(self, request):
        today_date = date.today()
        
        total_staff = StaffProfile.objects.filter(is_active=True).count()
        
        today_logs = WorkLog.objects.filter(date=today_date)
        active_today = today_logs.values('staff').distinct().count()
        total_hours_today = sum(float(log.hours) for log in today_logs)
        
        week_start = today_date - timedelta(days=7)
        week_logs = WorkLog.objects.filter(date__range=[week_start, today_date])
        total_hours_week = sum(float(log.hours) for log in week_logs)
        
        month_start = today_date - timedelta(days=30)
        month_logs = WorkLog.objects.filter(date__range=[month_start, today_date])
        total_hours_month = sum(float(log.hours) for log in month_logs)
        
        weekly_trend = []
        for i in range(7):
            day = today_date - timedelta(days=i)
            day_logs = WorkLog.objects.filter(date=day)
            day_hours = sum(float(log.hours) for log in day_logs)
            day_staff = day_logs.values('staff').distinct().count()
            
            weekly_trend.append({
                'date': day,
                'day_name': day.strftime('%A'),
                'total_hours': round(day_hours, 1),
                'staff_count': day_staff
            })
        
        data = {
            'total_staff': total_staff,
            'active_today': active_today,
            'present_today': active_today,
            'attendance_rate': round((active_today / total_staff * 100) if total_staff > 0 else 0, 1),
            'total_hours_today': round(total_hours_today, 1),
            'total_hours_week': round(total_hours_week, 1),
            'total_hours_month': round(total_hours_month, 1),
            'weekly_trend': weekly_trend
        }
        
        return Response(data)

class AdminWorkLogsView(generics.ListAPIView):
    """Admin: View all work logs with filters"""
    serializer_class = WorkLogSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        queryset = WorkLog.objects.all().select_related('staff__user')
        
        staff_id = self.request.query_params.get('staff')
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(date__range=[start_date, end_date])
        elif start_date:
            queryset = queryset.filter(date__gte=start_date)
        elif end_date:
            queryset = queryset.filter(date__lte=end_date)
        
        locked = self.request.query_params.get('locked')
        if locked is not None:
            queryset = queryset.filter(is_locked=locked.lower() == 'true')
        
        return queryset.order_by('-date', '-created_at')

class AdminLeaveRequestsView(generics.ListAPIView):
    """Admin: View and manage leave requests"""
    serializer_class = LeaveSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        queryset = Leave.objects.all().select_related('staff__user')
        
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset.order_by('-created_at')

from datetime import time, timedelta
from django.utils import timezone

class AdminApproveLeaveView(APIView):
    """Admin: Approve or reject leave requests"""
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request, leave_id):
        try:
            leave = Leave.objects.get(id=leave_id, status='pending')
            action = request.data.get('action')
            
            if action in ['approve', 'approved']:
                leave.status = 'approved'
                leave.approved_by = request.user
                leave.approved_at = timezone.now()
                
                self.create_leave_work_logs(leave)
                
            elif action in ['reject', 'rejected']:
                leave.status = 'rejected'
            else:
                return Response(
                    {'error': 'Invalid action. Use "approve" or "reject"'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            leave.save()
            return Response(LeaveSerializer(leave).data)
            
        except Leave.DoesNotExist:
            return Response(
                {'error': 'Leave request not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def create_leave_work_logs(self, leave):
        from .models import WorkLog
        
        current_date = leave.start_date
        end_date = leave.end_date
        
        expected_hours = float(leave.staff.expected_hours_per_day or 8.00)
        
        leave_descriptions = {
            'sick': '🏥 Sick Leave',
            'vacation': '🌴 Vacation Leave',
            'permission': '📋 Permission - Official',
            'other': '📝 Approved Leave',
        }
        
        description = leave_descriptions.get(leave.leave_type, '✅ Approved Leave')
        
        logs_created = 0
        while current_date <= end_date:
            existing_log = WorkLog.objects.filter(
                staff=leave.staff,
                date=current_date
            ).first()
            
            if not existing_log:
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
                logs_created += 1
            
            current_date += timedelta(days=1)
        
        print(f"✅ Created {logs_created} leave work logs for {leave.staff}")

class AdminSetupView(APIView):
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request):
        profile, _ = StaffProfile.objects.get_or_create(user=request.user)
        profile.company_name = request.data.get('company_name')
        profile.max_staff = request.data.get('max_staff', 10)
        profile.setup_complete = True
        profile.save()
        
        return Response({'status': 'success'})

class AdminCreateStaffView(APIView):
    """Admin: Create a new staff user and email credentials"""
    permission_classes = [IsAdminUser]
    
    def generate_secure_password(self):
        letters = ''.join(random.choices(string.ascii_uppercase, k=2))
        numbers = ''.join(random.choices(string.digits, k=3))
        return f"OTIC{letters}{numbers}"
    
    def generate_employee_id(self):
        return f"EMP{random.randint(1000, 9999)}"
    
    def send_welcome_email(self, user, password, role):
        subject = 'Welcome to OTIC Workforce - Your Account Details'
        
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #1e3a8a; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .credentials {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                .footer {{ font-size: 12px; color: #666; text-align: center; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to OTIC Workforce!</h1>
                </div>
                <div class="content">
                    <p>Hello <strong>{user.first_name} {user.last_name}</strong>,</p>
                    <p>Your account has been created successfully. You can now access the OTIC Workforce platform with the following credentials:</p>
                    
                    <div class="credentials">
                        <p><strong>Username:</strong> {user.username}</p>
                        <p><strong>Email:</strong> {user.email}</p>
                        <p><strong>Password:</strong> {password}</p>
                        <p><strong>Role:</strong> {role.title()}</p>
                    </div>
                    
                    <p>For security reasons, we recommend changing your password after your first login.</p>
                    
                    <p><strong>Login URL:</strong> <a href="http://localhost:5173">http://localhost:5173</a></p>
                </div>
                <div class="footer">
                    <p>&copy; 2026 OTIC Workforce. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        try:
            send_mail(
                subject,
                strip_tags(html_message),
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=html_message,
                fail_silently=False,
            )
            print(f"✅ Welcome email sent to {user.email}")
            return True
        except Exception as e:
            print(f"❌ Failed to send email: {str(e)}")
            traceback.print_exc()
            return False
    
    def post(self, request):
        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        email = request.data.get('email')
        department = request.data.get('department', 'General')
        role = request.data.get('role', 'staff')
        
        if not first_name or not last_name or not email:
            return Response(
                {'error': 'First name, last name, and email are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if User.objects.filter(email=email).exists():
            return Response(
                {'error': f'User with email {email} already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        username = email.split('@')[0]
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        password = self.generate_secure_password()
        
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_staff=(role == 'admin'),
                is_superuser=(role == 'admin')
            )
            
            staff_profile = StaffProfile.objects.create(
                user=user,
                department=department,
                expected_hours_per_day=9.00,
                is_active=True,
                employee_id=self.generate_employee_id()
            )
            
            self.send_welcome_email(user, password, role)
            
            return Response({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'department': staff_profile.department,
                'role': role,
                'password': password,
                'message': f'Staff {first_name} {last_name} created successfully! Login credentials sent to {email}'
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print(f"Error creating staff: {str(e)}")
            traceback.print_exc()
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class AdminExportView(APIView):
    """Admin: Export work logs as CSV"""
    permission_classes = [permissions.IsAdminUser]
    
    def get(self, request):
        try:
            staff_id = request.query_params.get('staff')
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            
            queryset = WorkLog.objects.all().select_related('staff__user')
            
            if staff_id and staff_id != 'all' and staff_id != 'undefined':
                queryset = queryset.filter(staff_id=staff_id)
            
            if start_date and start_date != 'undefined':
                queryset = queryset.filter(date__gte=start_date)
            
            if end_date and end_date != 'undefined':
                queryset = queryset.filter(date__lte=end_date)
            
            queryset = queryset.order_by('-date', 'staff__user__username')
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="worklogs_{timestamp}.csv"'
            
            writer = csv.writer(response)
            writer.writerow([
                'Staff Name',
                'Department',
                'Date',
                'Start Time',
                'End Time',
                'Description',
                'Hours',
                'Status',
                'Locked'
            ])
            
            for log in queryset:
                writer.writerow([
                    str(log.staff),
                    log.staff.department if hasattr(log.staff, 'department') else 'General',
                    log.date,
                    log.start_time.strftime('%H:%M') if log.start_time else '',
                    log.end_time.strftime('%H:%M') if log.end_time else '',
                    log.description,
                    float(log.hours),
                    log.status,
                    'Yes' if log.is_locked else 'No'
                ])
            
            return response
            
        except Exception as e:
            print(f"Export error: {str(e)}")
            traceback.print_exc()
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )