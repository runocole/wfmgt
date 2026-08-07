from datetime import datetime, timedelta
from geopy.distance import geodesic


def calculate_distance_meters(lat1, lng1, lat2, lng2):
    """Returns distance in meters between two lat/lng points."""
    return geodesic((float(lat1), float(lng1)), (float(lat2), float(lng2))).meters


def check_geofence(staff_lat, staff_lng, organization, accuracy=None):
    """
    Checks whether staff coordinates fall within the organization's geofence.
    Returns (is_within_geofence: bool, distance_m: float, needs_better_gps: bool)

    If the device's reported GPS accuracy is worse than MAX_ACCEPTABLE_ACCURACY,
    we don't trust the reading enough to make a fraud-relevant decision either way
    -- we ask for a retry instead of silently accepting a wide margin of error.
    """
    MAX_ACCEPTABLE_ACCURACY = 30  # meters; readings worse than this are rejected

    if organization.office_latitude is None or organization.office_longitude is None:
        return False, None, False

    if accuracy is not None and accuracy > MAX_ACCEPTABLE_ACCURACY:
        return False, None, True

    distance = calculate_distance_meters(
        staff_lat, staff_lng,
        organization.office_latitude, organization.office_longitude
    )
    is_within = distance <= organization.geofence_radius_m
    return is_within, round(distance, 1), False


def determine_attendance_status(sign_in_time, organization):
    """
    Determines 'present' vs 'late' based on org's work_start_time + late_threshold_minutes.
    sign_in_time: a timezone-aware datetime (typically UTC).
    Converts to the organization's local timezone before comparing.
    """
    import pytz
    org_tz = pytz.timezone(organization.timezone or 'UTC')
    local_sign_in = sign_in_time.astimezone(org_tz)

    work_start = organization.work_start_time  # a time object, in org-local time
    threshold_minutes = organization.late_threshold_minutes

    cutoff_naive = datetime.combine(local_sign_in.date(), work_start) + timedelta(minutes=threshold_minutes)
    cutoff = org_tz.localize(cutoff_naive)

    if local_sign_in <= cutoff:
        return 'present'
    return 'late'


def get_worklog_lock_time(organization):
    """
    Returns the (work_start_time, cutoff_time) window that should be locked
    on the WorkLog when a staff member signs in late.
    e.g. work_start=8:00, threshold=45min -> locked window is 8:00-8:45
    """
    threshold_minutes = organization.late_threshold_minutes
    work_start = organization.work_start_time
    cutoff_naive = datetime.combine(datetime.today(), work_start) + timedelta(minutes=threshold_minutes)
    return work_start, cutoff_naive.time()


def calculate_attendance_grade(sign_in_time, organization):
    """
    Grades sign-in time against HR's fixed time bands (local org time).
    Returns a float grade 0.0-1.0 if within a defined band, or None if
    signed in outside all bands (e.g. very late) or missing.
    None means 'not graded' -- NOT the same as absent/zero. The person
    still showed up, they just fall outside HR's graded window.
    """
    import pytz
    if sign_in_time is None:
        return None

    org_tz = pytz.timezone(organization.timezone or 'UTC')
    local_time = sign_in_time.astimezone(org_tz).time()

    bands = [
        (datetime.strptime('06:30', '%H:%M').time(), datetime.strptime('07:45', '%H:%M').time(), 1.0),
        (datetime.strptime('07:46', '%H:%M').time(), datetime.strptime('08:00', '%H:%M').time(), 0.9),
        (datetime.strptime('08:01', '%H:%M').time(), datetime.strptime('08:15', '%H:%M').time(), 0.75),
        (datetime.strptime('08:16', '%H:%M').time(), datetime.strptime('08:30', '%H:%M').time(), 0.65),
        (datetime.strptime('08:31', '%H:%M').time(), datetime.strptime('08:45', '%H:%M').time(), 0.5),
        (datetime.strptime('08:46', '%H:%M').time(), datetime.strptime('09:00', '%H:%M').time(), 0.45),
        (datetime.strptime('09:00', '%H:%M').time(), datetime.strptime('09:15', '%H:%M').time(), 0.25),
    ]

    for start, end, grade in bands:
        if start <= local_time <= end:
            return grade

    return None


def get_org_today(organization):
    """
    Returns 'today' as a date object in the organization's local timezone,
    not the server's raw UTC date. Prevents attendance records from being
    stamped with the wrong calendar day near midnight UTC boundaries.
    """
    import pytz
    from django.utils import timezone as django_timezone
    org_tz = pytz.timezone(organization.timezone or 'UTC')
    return django_timezone.now().astimezone(org_tz).date()
