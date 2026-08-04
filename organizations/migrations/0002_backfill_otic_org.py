from django.db import migrations


def backfill_otic(apps, schema_editor):
    Organization = apps.get_model('organizations', 'Organization')
    Department = apps.get_model('organizations', 'Department')
    StaffProfile = apps.get_model('workforce', 'StaffProfile')

    org, created = Organization.objects.get_or_create(
        slug='otic-geosystems',
        defaults={
            'name': 'OTIC Geosystems',
            'timezone': 'Africa/Lagos',
            'work_start_time': '08:00',
            'work_end_time': '17:00',
            'late_threshold_minutes': 45,
            'working_days': [0, 1, 2, 3, 4],
            'office_latitude': 6.441142,
            'office_longitude': 3.528104,
            'geofence_radius_m': 15,
            'max_staff': 100,
            'is_setup_complete': True,
        }
    )

    staff_qs = StaffProfile.objects.filter(organization__isnull=True)
    dept_cache = {}

    for staff in staff_qs:
        dept_name = (staff.department or 'General').strip() or 'General'
        if dept_name not in dept_cache:
            dept_obj, _ = Department.objects.get_or_create(
                organization=org, name=dept_name
            )
            dept_cache[dept_name] = dept_obj
        staff.organization = org
        staff.department_fk = dept_cache[dept_name]
        staff.save(update_fields=['organization', 'department_fk'])

    print(f"Backfilled {staff_qs.count()} staff into '{org.name}' across {len(dept_cache)} departments.")


def reverse_backfill(apps, schema_editor):
    Organization = apps.get_model('organizations', 'Organization')
    StaffProfile = apps.get_model('workforce', 'StaffProfile')
    org = Organization.objects.filter(slug='otic-geosystems').first()
    if org:
        StaffProfile.objects.filter(organization=org).update(organization=None, department_fk=None)
        org.departments.all().delete()
        org.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0001_initial'),
        ('workforce', '0013_staffprofile_department_fk_staffprofile_organization'),
    ]

    operations = [
        migrations.RunPython(backfill_otic, reverse_backfill),
    ]
