from datetime import datetime, timedelta
from geopy.distance import geodesic


def calculate_distance_meters(lat1, lng1, lat2, lng2):
    """Returns distance in meters between two lat/lng points."""
    return geodesic((float(lat1), float(lng1)), (float(lat2), float(lng2))).meters


def check_geofence(staff_lat, staff_lng, organization):
    """
    Checks whether staff coordinates fall within the organization's geofence.
    Returns (is_within_geofence: bool, distance_m: float)
    """
    if organization.office_latitude is None or organization.office_longitude is None:
        # No geofence configured for this org — treat as not verifiable
        return False, None

    distance = calculate_distance_meters(
        staff_lat, staff_lng,
        organization.office_latitude, organization.office_longitude
    )
    is_within = distance <= organization.geofence_radius_m
    return is_within, round(distance, 1)


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
