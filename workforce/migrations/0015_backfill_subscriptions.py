from django.db import migrations
from django.utils import timezone


def backfill_subscriptions(apps, schema_editor):
    Subscription = apps.get_model('workforce', 'Subscription')
    App = apps.get_model('workforce', 'App')
    Organization = apps.get_model('organizations', 'Organization')

    # 1. Backfill organization on any existing subscription rows via user's staff_profile
    updated = 0
    for sub in Subscription.objects.filter(organization__isnull=True, user__isnull=False):
        staff_profile = getattr(sub.user, 'staff_profile', None)
        if staff_profile and staff_profile.organization_id:
            sub.organization_id = staff_profile.organization_id
            sub.save(update_fields=['organization'])
            updated += 1
    print(f"Backfilled organization on {updated} existing subscription(s).")

    # 2. Ensure a Worklog App entry exists
    worklog_app, created = App.objects.get_or_create(
        name='Worklog',
        defaults={
            'description': 'Staff work log and time tracking',
            'icon_name': 'ClipboardList',
            'order': 1,
        }
    )
    if created:
        print("Created 'Worklog' App entry.")

    # 3. Give OTIC a free, active Worklog subscription
    org = Organization.objects.filter(slug='otic-geosystems').first()
    if org:
        sub, created = Subscription.objects.get_or_create(
            organization=org,
            app=worklog_app,
            defaults={
                'plan': 'enterprise',
                'status': 'active',
                'amount_paid': 0,
                'start_date': timezone.now(),
                'end_date': None,  # no expiry
            }
        )
        if not created and sub.status != 'active':
            sub.status = 'active'
            sub.amount_paid = 0
            sub.save(update_fields=['status', 'amount_paid'])
        print(f"OTIC Worklog subscription: {'created' if created else 'updated'} — status=active, amount_paid=0.")
    else:
        print("WARNING: OTIC organization not found — subscription not created.")


def reverse_backfill(apps, schema_editor):
    Subscription = apps.get_model('workforce', 'Subscription')
    Organization = apps.get_model('organizations', 'Organization')
    org = Organization.objects.filter(slug='otic-geosystems').first()
    if org:
        Subscription.objects.filter(organization=org, amount_paid=0).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('workforce', '0014_subscription_add_organization'),
        ('organizations', '0002_backfill_otic_org'),
    ]

    operations = [
        migrations.RunPython(backfill_subscriptions, reverse_backfill),
    ]
