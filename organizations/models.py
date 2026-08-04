from django.db import models


class Organization(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    timezone = models.CharField(max_length=50, default='Africa/Lagos')

    # Work schedule config
    work_start_time = models.TimeField(default='08:00')
    work_end_time = models.TimeField(default='17:00')
    late_threshold_minutes = models.IntegerField(default=30)
    working_days = models.JSONField(default=list)  # e.g. [0,1,2,3,4] Mon-Fri

    # Geofence config
    office_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    office_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geofence_radius_m = models.IntegerField(default=150)

    # Plan / subscription limits
    max_staff = models.IntegerField(default=10)
    is_setup_complete = models.BooleanField(default=False)

    logo = models.ImageField(upload_to='org_logos/', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Department(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=100)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['organization', 'name']
        ordering = ['name']

    def __str__(self):
        return f"{self.organization.name} — {self.name}"


class QuickTask(models.Model):
    """Admin-configurable quick task suggestions for worklog entries"""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='quick_tasks')
    label = models.CharField(max_length=200)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return self.label


class Announcement(models.Model):
    """News/updates posted by admin, shown on staff dashboard"""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='announcements')
    title = models.CharField(max_length=200)
    body = models.TextField()
    is_pinned = models.BooleanField(default=False)
    posted_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f"{self.organization.name} — {self.title}"
