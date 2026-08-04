from django.contrib import admin
from .models import Organization, Department, QuickTask, Announcement

admin.site.register(Organization)
admin.site.register(Department)
admin.site.register(QuickTask)
admin.site.register(Announcement)
