from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.db.models import Sum, Count
from datetime import date, timedelta, datetime, time
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
import json

# ============================================
# EXISTING AUTH VIEWS (Keep all your existing ones)
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
    """Login user"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        
        user = authenticate(username=username, password=password)
        
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
# EXISTING APP VIEWS (Keep all your existing ones)
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
# EXISTING SUBSCRIPTION VIEWS (Keep all your existing ones)
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
    """List all work logs for current user or create new"""
    serializer_class = WorkLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Filter by date if provided
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
        # Filter by date if provided
        date_param = self.request.query_params.get('date')
        if date_param:
            return WorkLog.objects.filter(
                date=date_param
            ).select_related('staff__user').order_by('staff__user__username', '-created_at')
        
        # Default to today
        return WorkLog.objects.filter(
            date=date.today()
        ).select_related('staff__user').order_by('staff__user__username', '-created_at')

class TodayWorkLogsView(APIView):
    """Get today's work logs grouped by staff"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        today = date.today()
        logs = WorkLog.objects.filter(date=today).select_related('staff__user')
        
        # Group by staff
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
        
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # Get metrics in date range
        metrics = DailyMetric.objects.filter(
            staff=staff,
            date__range=[start_date, end_date]
        )
        
        total_days_worked = metrics.count()
        total_hours_worked = sum(float(m.total_hours) for m in metrics)
        expected_hours = days * float(staff.expected_hours_per_day)
        
        deficit = max(0, expected_hours - total_hours_worked)
        surplus = max(0, total_hours_worked - expected_hours)
        attendance_rate = (total_days_worked / days * 100) if days > 0 else 0
        avg_hours = total_hours_worked / days if days > 0 else 0
        
        # Get recent logs
        recent_logs = WorkLog.objects.filter(staff=staff).order_by('-date', '-created_at')[:10]
        
        data = {
            'total_days_worked': total_days_worked,
            'total_hours_worked': total_hours_worked,
            'expected_hours': expected_hours,
            'deficit': deficit,
            'surplus': surplus,
            'attendance_rate': round(attendance_rate, 1),
            'average_hours_per_day': round(avg_hours, 1),
            'recent_logs': WorkLogSerializer(recent_logs, many=True).data
        }
        
        serializer = StaffDashboardSerializer(data)
        return Response(serializer.data)

# -------------------- LEAVE REQUESTS --------------------

class LeaveListCreateView(generics.ListCreateAPIView):
    """List or create leave requests"""
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
        # Can only update pending requests
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
        period = request.query_params.get('period', 'week')  # week, month
        
        # Calculate date range
        today = date.today()
        if period == 'week':
            start_date = today - timedelta(days=7)
        elif period == 'month':
            start_date = today - timedelta(days=30)
        else:
            start_date = today - timedelta(days=7)
        
        # Get rankings
        rankings = []
        for staff in StaffProfile.objects.filter(is_active=True):
            # Get work logs in date range
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
                'department': None,  # You can add department later if needed
                'total_hours': round(total_hours, 1),
                'total_days': total_days,
                'average_hours': round(avg_hours, 1)
            })
        
        # Sort by hours (highest first)
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
        
        # Staff counts
        total_staff = StaffProfile.objects.filter(is_active=True).count()
        
        # Today's activity
        today_logs = WorkLog.objects.filter(date=today_date)
        active_today = today_logs.values('staff').distinct().count()
        
        total_hours_today = sum(float(log.hours) for log in today_logs)
        
        # This week
        week_start = today_date - timedelta(days=7)
        week_logs = WorkLog.objects.filter(date__range=[week_start, today_date])
        total_hours_week = sum(float(log.hours) for log in week_logs)
        
        # This month
        month_start = today_date - timedelta(days=30)
        month_logs = WorkLog.objects.filter(date__range=[month_start, today_date])
        total_hours_month = sum(float(log.hours) for log in month_logs)
        
        # Weekly trend
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
        
        # Filter by staff
        staff_id = self.request.query_params.get('staff')
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(date__range=[start_date, end_date])
        elif start_date:
            queryset = queryset.filter(date__gte=start_date)
        elif end_date:
            queryset = queryset.filter(date__lte=end_date)
        
        # Filter by locked status
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
        
        # Filter by status
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset.order_by('-created_at')

class AdminApproveLeaveView(APIView):
    """Admin: Approve or reject leave requests"""
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request, leave_id):
        try:
            leave = Leave.objects.get(id=leave_id, status='pending')
            action = request.data.get('action')  # 'approve' or 'reject'
            
            if action == 'approve':
                leave.status = 'approved'
                leave.approved_by = request.user
                leave.approved_at = timezone.now()
            elif action == 'reject':
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
class AdminSetupView(APIView):
    permission_classes = [permissions.IsAdminUser]
    
    def post(self, request):
        # Update user profile with company details
        profile, _ = StaffProfile.objects.get_or_create(user=request.user)
        profile.company_name = request.data.get('company_name')
        profile.max_staff = request.data.get('max_staff', 10)
        profile.setup_complete = True
        profile.save()
        
        return Response({'status': 'success'})