from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status

from workforce.models import StaffProfile
from .models import Organization
from .serializers import OrganizationSettingsSerializer


class OrganizationSettingsView(APIView):
    permission_classes = [IsAdminUser]

    def _get_org(self, request):
        try:
            staff = StaffProfile.objects.select_related('organization').get(user=request.user)
        except StaffProfile.DoesNotExist:
            return None
        return staff.organization

    def get(self, request):
        org = self._get_org(request)
        if not org:
            return Response({'error': 'Organization not found for this admin.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(OrganizationSettingsSerializer(org).data)

    def patch(self, request):
        org = self._get_org(request)
        if not org:
            return Response({'error': 'Organization not found for this admin.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = OrganizationSettingsSerializer(org, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
