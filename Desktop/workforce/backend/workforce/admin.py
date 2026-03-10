from django.contrib import admin
from .models import (
    App, Subscription, UserProfile, 
    StaffProfile, WorkLog, DailyMetric, Leave
)

@admin.register(App)
class AppAdmin(admin.ModelAdmin):
    list_display = ['name', 'order', 'is_popular', 'individual_price', 'team_price', 'enterprise_price']
    list_editable = ['order', 'is_popular']
    search_fields = ['name', 'description']
    list_filter = ['is_popular']

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'app', 'plan', 'status', 'start_date', 'end_date']
    list_filter = ['status', 'plan']
    search_fields = ['user__username', 'app__name']

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'company', 'phone']
    search_fields = ['user__username', 'company']

# ============================================
# WORK LOG SYSTEM ADMIN (FIXED)
# ============================================

@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'employee_id', 'expected_hours_per_day', 'is_active']  
    list_filter = ['is_active']  
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'employee_id']

@admin.register(WorkLog)
class WorkLogAdmin(admin.ModelAdmin):
    list_display = ['staff', 'date', 'hours', 'status', 'is_locked'] 
    list_filter = ['status', 'is_locked', 'date'] 
    search_fields = ['staff__user__username', 'description']
    date_hierarchy = 'date'

@admin.register(DailyMetric)
class DailyMetricAdmin(admin.ModelAdmin):
    list_display = ['staff', 'date', 'total_hours', 'expected_hours', 'deficit', 'surplus']
    list_filter = ['date']
    search_fields = ['staff__user__username']
    date_hierarchy = 'date'

@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ['staff', 'leave_type', 'start_date', 'end_date', 'status']
    list_filter = ['leave_type', 'status']
    search_fields = ['staff__user__username', 'reason']
    date_hierarchy = 'start_date'