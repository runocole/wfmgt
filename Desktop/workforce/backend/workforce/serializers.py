from rest_framework import serializers
from django.contrib.auth.models import User
from .models import App, Subscription, UserProfile, StaffProfile, WorkLog, DailyMetric, Leave
import json

class AppSerializer(serializers.ModelSerializer):
    individual_features = serializers.SerializerMethodField()
    team_features = serializers.SerializerMethodField()
    enterprise_features = serializers.SerializerMethodField()
    
    class Meta:
        model = App
        fields = [
            'id', 'name', 'description', 'icon_name', 'is_popular', 
            'icon_color', 'icon_bg_color', 'order',
            'individual_price', 'team_price', 'enterprise_price',
            'individual_features', 'team_features', 'enterprise_features'
        ]
    
    def get_individual_features(self, obj):
        return json.loads(obj.individual_features) if obj.individual_features else []
    
    def get_team_features(self, obj):
        return json.loads(obj.team_features) if obj.team_features else []
    
    def get_enterprise_features(self, obj):
        return json.loads(obj.enterprise_features) if obj.enterprise_features else []

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['company', 'phone', 'avatar']

class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'profile']
        read_only_fields = ['id']

class SubscriptionSerializer(serializers.ModelSerializer):
    app_details = AppSerializer(source='app', read_only=True)
    
    class Meta:
        model = Subscription
        fields = [
            'id', 'app', 'app_details', 'plan', 'status', 
            'amount_paid', 'start_date', 'end_date'
        ]

class SubscriptionCreateSerializer(serializers.Serializer):
    """For creating a new subscription"""
    app_id = serializers.IntegerField()
    plan = serializers.ChoiceField(choices=['individual', 'team', 'enterprise'])
    
    def validate(self, data):
        # Check if user already has an active subscription for this app
        user = self.context['request'].user
        app_id = data['app_id']
        
        if Subscription.objects.filter(
            user=user, 
            app_id=app_id, 
            status__in=['active', 'pending']
        ).exists():
            raise serializers.ValidationError("You already have a subscription for this app")
        
        return data

class LoginResponseSerializer(serializers.Serializer):
    user = UserSerializer()
    access = serializers.CharField()
    refresh = serializers.CharField(required=False)

# ============================================
# WORK LOG SYSTEM SERIALIZERS
# ============================================

class StaffProfileSerializer(serializers.ModelSerializer):
    """Serializer for staff profile"""
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = StaffProfile
        fields = [
            'id', 'user', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'employee_id', 'hire_date', 'expected_hours_per_day', 
            'is_active', 'phone', 'receive_daily_reminder'
        ]
    
    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

class WorkLogSerializer(serializers.ModelSerializer):
    """Serializer for work log entries"""
    staff_name = serializers.SerializerMethodField()
    staff_username = serializers.CharField(source='staff.user.username', read_only=True)
    
    class Meta:
        model = WorkLog
        fields = [
            'id', 'staff', 'staff_name', 'staff_username', 'date',
            'project', 'task', 'description', 'hours', 'status',
            'is_locked', 'created_at', 'updated_at'
        ]
        read_only_fields = ['is_locked', 'created_at', 'updated_at']
    
    def get_staff_name(self, obj):
        return str(obj.staff)
    
    def validate(self, data):
        from datetime import datetime, time
        
        # Check if after 10pm for new entries
        if not self.instance and datetime.now().time() >= time(22, 0):
            raise serializers.ValidationError("Cannot create new entries after 10pm")
        
        # Check if editing locked entry
        if self.instance and self.instance.is_locked:
            raise serializers.ValidationError("Cannot edit locked entries")
        
        return data

class DailyMetricSerializer(serializers.ModelSerializer):
    """Serializer for daily metrics"""
    staff_name = serializers.SerializerMethodField()
    
    class Meta:
        model = DailyMetric
        fields = [
            'id', 'staff', 'staff_name', 'date',
            'total_hours', 'expected_hours', 'deficit', 'surplus',
            'is_complete'
        ]
    
    def get_staff_name(self, obj):
        return str(obj.staff)

class LeaveSerializer(serializers.ModelSerializer):
    """Serializer for leave requests"""
    staff_name = serializers.SerializerMethodField()
    duration_days = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Leave
        fields = [
            'id', 'staff', 'staff_name', 'leave_type',
            'start_date', 'end_date', 'duration_days', 'reason',
            'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['status', 'created_at', 'updated_at']
    
    def get_staff_name(self, obj):
        return str(obj.staff)
    
    def validate(self, data):
        # Ensure end_date is after start_date
        if data['end_date'] < data['start_date']:
            raise serializers.ValidationError("End date must be after start date")
        return data

# ============================================
# DASHBOARD AND ANALYTICS SERIALIZERS
# ============================================

class StaffDashboardSerializer(serializers.Serializer):
    """Staff dashboard metrics"""
    total_days_worked = serializers.IntegerField()
    total_hours_worked = serializers.FloatField()
    expected_hours = serializers.FloatField()
    deficit = serializers.FloatField()
    surplus = serializers.FloatField()
    attendance_rate = serializers.FloatField()
    average_hours_per_day = serializers.FloatField()
    recent_logs = WorkLogSerializer(many=True)

class StaffRankingSerializer(serializers.Serializer):
    """Staff ranking for admin"""
    staff_id = serializers.IntegerField()
    staff_name = serializers.CharField()
    department = serializers.CharField(allow_null=True)
    total_hours = serializers.FloatField()
    total_days = serializers.IntegerField()
    average_hours = serializers.FloatField()

class AdminSummarySerializer(serializers.Serializer):
    """Admin dashboard summary"""
    total_staff = serializers.IntegerField()
    active_today = serializers.IntegerField()
    present_today = serializers.IntegerField()
    attendance_rate = serializers.FloatField()
    total_hours_today = serializers.FloatField()
    total_hours_week = serializers.FloatField()
    total_hours_month = serializers.FloatField()
    
    class Meta:
        fields = '__all__'

class WeeklyTrendSerializer(serializers.Serializer):
    """Weekly trend data point"""
    date = serializers.DateField()
    day_name = serializers.CharField()
    total_hours = serializers.FloatField()
    staff_count = serializers.IntegerField()