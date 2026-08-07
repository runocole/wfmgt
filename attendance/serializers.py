from rest_framework import serializers
from .models import Attendance, WebAuthnCredential


class AttendanceSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()

    class Meta:
        model = Attendance
        fields = [
            'id', 'staff', 'staff_name', 'department', 'date',
            'sign_in_time', 'sign_in_lat', 'sign_in_lng', 'sign_in_method',
            'geofence_verified', 'biometric_verified',
            'attendance_type', 'approval_status', 'reason',
            'approved_by', 'approved_at',
            'sign_out_time', 'sign_out_lat', 'sign_out_lng',
            'status', 'distance_from_office_m', 'attendance_grade',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'status', 'distance_from_office_m', 'attendance_grade', 'geofence_verified',
            'biometric_verified', 'approved_by', 'approved_at', 'created_at', 'updated_at',
        ]

    def get_staff_name(self, obj):
        return str(obj.staff)

    def get_department(self, obj):
        return obj.staff.department_fk.name if obj.staff.department_fk else (obj.staff.department or 'General')


class SignInRequestSerializer(serializers.Serializer):
    """Payload for the geofence + biometric sign-in endpoint"""
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    accuracy = serializers.FloatField(required=False, allow_null=True)
    webauthn_credential_id = serializers.CharField(required=False, allow_blank=True)
    webauthn_authenticator_data = serializers.CharField(required=False, allow_blank=True)
    webauthn_client_data_json = serializers.CharField(required=False, allow_blank=True)
    webauthn_signature = serializers.CharField(required=False, allow_blank=True)


class FieldClockInRequestSerializer(serializers.Serializer):
    """Payload for 'Not at Work' field clock-in"""
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    accuracy = serializers.FloatField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True)


class WebAuthnCredentialSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebAuthnCredential
        fields = ['id', 'credential_id', 'device_label', 'created_at']
        read_only_fields = ['id', 'created_at']
