from django.contrib import admin
from .models import StaffProfile, WorkLog, Leave, Query, PublicHoliday, DeletedLog

@admin.register(Query)
class QueryAdmin(admin.ModelAdmin):
    list_display = ['id', 'staff', 'status', 'admin_note', 'created_at']
    list_filter = ['status']
    search_fields = ['staff__user__username', 'admin_note']

@admin.register(WorkLog)
class WorkLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'staff', 'date', 'start_time', 'end_time', 'hours', 'status']
    list_filter = ['status', 'date']

@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'department', 'is_active']

@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ['id', 'staff', 'leave_type', 'status', 'start_date', 'end_date']
    list_filter = ['status', 'leave_type']

@admin.register(PublicHoliday)
class PublicHolidayAdmin(admin.ModelAdmin):
    list_display = ['date', 'name']

@admin.register(DeletedLog)
class DeletedLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'staff_name', 'date', 'deleted_at', 'deleted_by']
