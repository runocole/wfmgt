from django.db import models
from workforce.models import StaffProfile


class Attendance(models.Model):
    METHOD_CHOICES = [
        ('geofence', 'Geofence'),
        ('manual', 'Manual'),
        ('biometric', 'Biometric'),
    ]
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('late', 'Late'),
        ('absent', 'Absent'),
    ]

    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField()

    sign_in_time = models.DateTimeField(null=True, blank=True)
    sign_in_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    sign_in_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    sign_in_method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='geofence')
    geofence_verified = models.BooleanField(default=False)
    biometric_verified = models.BooleanField(default=False)

    ATTENDANCE_TYPE_CHOICES = [('office', 'Office'), ('field', 'Field/Not at Work')]
    attendance_type = models.CharField(max_length=20, choices=ATTENDANCE_TYPE_CHOICES, default='office')

    APPROVAL_CHOICES = [('not_required', 'Not Required'), ('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')]
    approval_status = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default='not_required')
    reason = models.TextField(blank=True, null=True)
    approved_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_attendance')
    approved_at = models.DateTimeField(null=True, blank=True)

    sign_out_time = models.DateTimeField(null=True, blank=True)
    sign_out_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    sign_out_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='present')
    distance_from_office_m = models.FloatField(null=True, blank=True)
    attendance_grade = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['staff', 'date']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['staff', 'date']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return f"{self.staff} — {self.date} — {self.status}"


class WebAuthnCredential(models.Model):
    """Registered biometric (Face ID / fingerprint) credential for a staff member"""
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='webauthn_credentials')
    credential_id = models.CharField(max_length=255, unique=True)
    public_key = models.TextField()
    sign_count = models.BigIntegerField(default=0)
    device_label = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.staff} — {self.device_label or 'device'}"


class WebAuthnChallenge(models.Model):
    """Short-lived one-time challenge used during WebAuthn registration/sign-in"""
    PURPOSE_CHOICES = [('register', 'Register'), ('signin', 'Sign In')]

    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='webauthn_challenges')
    challenge = models.CharField(max_length=255)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.staff} — {self.purpose} — {'used' if self.used else 'pending'}"
