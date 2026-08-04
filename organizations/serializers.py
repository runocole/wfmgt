from rest_framework import serializers
from .models import Organization


class OrganizationSettingsSerializer(serializers.ModelSerializer):
    """
    Editable settings for org admins: work hours, late threshold, working days.
    Geofence coordinates/radius are deliberately excluded — those are
    set at onboarding only, to prevent accidental/fraudulent changes.
    """
    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'work_start_time', 'work_end_time',
            'late_threshold_minutes', 'working_days', 'timezone',
        ]
        read_only_fields = ['id', 'name']
