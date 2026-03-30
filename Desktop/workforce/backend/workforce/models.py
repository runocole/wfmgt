from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import date, timedelta

class App(models.Model):
    """Model for the apps shown on the frontend"""
    name = models.CharField(max_length=100)
    description = models.TextField()
    icon_name = models.CharField(max_length=50, help_text="Lucide icon name")
    is_popular = models.BooleanField(default=False)
    icon_color = models.CharField(max_length=50, default="text-primary")
    icon_bg_color = models.CharField(max_length=50, default="bg-primary/10")
    order = models.IntegerField(default=0)
    
    # Pricing
    individual_price = models.DecimalField(max_digits=10, decimal_places=2, default=9.99)
    team_price = models.DecimalField(max_digits=10, decimal_places=2, default=29.99)
    enterprise_price = models.DecimalField(max_digits=10, decimal_places=2, default=99.99)
    
    # Features by tier (stored as JSON)
    individual_features = models.TextField(default='[]', help_text="JSON array of features")
    team_features = models.TextField(default='[]', help_text="JSON array of features")
    enterprise_features = models.TextField(default='[]', help_text="JSON array of features")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'name']
    
    def __str__(self):
        return self.name
    
    def get_individual_features(self):
        return json.loads(self.individual_features)
    
    def get_team_features(self):
        return json.loads(self.team_features)
    
    def get_enterprise_features(self):
        return json.loads(self.enterprise_features)

class Subscription(models.Model):
    """Model for user subscriptions"""
    PLAN_CHOICES = [
        ('individual', 'Individual'),
        ('team', 'Team'),
        ('enterprise', 'Enterprise'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    app = models.ForeignKey(App, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Payment tracking
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True)
    
    # Dates
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'app']
    
    def __str__(self):
        return f"{self.user.username} - {self.app.name} ({self.status})"
    
    def is_active(self):
        return self.status == 'active' and (self.end_date is None or self.end_date > timezone.now())

class UserProfile(models.Model):
    """Extended user profile"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    company = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.user.username



# ============================================
# WORK LOG SYSTEM MODELS
# ============================================

class StaffProfile(models.Model):
    """Extended profile for staff members"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    employee_id = models.CharField(max_length=50, unique=True, blank=True)
    hire_date = models.DateField(default=date.today)
    expected_hours_per_day = models.DecimalField(
        max_digits=4, 
        decimal_places=2, 
        default=8.00,
        validators=[MinValueValidator(0), MaxValueValidator(24)]
    )
    department = models.CharField(max_length=100, blank=True, default='General')  
    is_active = models.BooleanField(default=True)
    phone = models.CharField(max_length=20, blank=True)
    
    # Settings
    receive_daily_reminder = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['user__first_name', 'user__last_name']
    
    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username}"

class WorkLog(models.Model):
    """Main work log entries"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='work_logs')
    date = models.DateField(default=date.today)
    description = models.TextField()
    hours = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(0.25), MaxValueValidator(24)]
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_locked = models.BooleanField(default=False)  # Locked after 10pm
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_worklogs')
    
    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['staff', 'date']),
            models.Index(fields=['date']),
            models.Index(fields=['is_locked']),
        ]
    
    def __str__(self):
        return f"{self.staff} - {self.date} - {self.hours}hrs"

class DailyMetric(models.Model):
    """Auto-calculated daily metrics for each staff"""
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='daily_metrics')
    date = models.DateField()
    
    # Calculated fields
    total_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    expected_hours = models.DecimalField(max_digits=5, decimal_places=2, default=8.00)
    deficit = models.DecimalField(max_digits=6, decimal_places=2, default=0)  # Negative if less than expected
    surplus = models.DecimalField(max_digits=6, decimal_places=2, default=0)   # Positive if more than expected
    
    # Status
    is_complete = models.BooleanField(default=False)  # All logs locked for the day
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date', 'staff']
        unique_together = ['staff', 'date']  # One record per staff per day
    
    def __str__(self):
        return f"{self.staff} - {self.date} - {self.total_hours}hrs"

class Leave(models.Model):
    """Staff leave requests"""
    LEAVE_TYPES = [
        ('sick', 'Sick Leave'),
        ('vacation', 'Vacation'),
        ('permission', 'Permission'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='leaves')
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_leaves')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.staff} - {self.leave_type} - {self.start_date}"
    
    @property
    def duration_days(self):
        return (self.end_date - self.start_date).days + 1