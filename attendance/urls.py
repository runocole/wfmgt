from django.urls import path
from . import views

urlpatterns = [
    # WebAuthn registration
    path('webauthn/register/begin/', views.WebAuthnRegisterBeginView.as_view(), name='webauthn-register-begin'),
    path('webauthn/register/complete/', views.WebAuthnRegisterCompleteView.as_view(), name='webauthn-register-complete'),
    path('webauthn/credentials/', views.MyWebAuthnCredentialsView.as_view(), name='webauthn-credentials'),
    path('webauthn/credentials/<int:credential_id>/', views.MyWebAuthnCredentialsView.as_view(), name='webauthn-credential-delete'),

    # WebAuthn sign-in challenge
    path('webauthn/signin/begin/', views.WebAuthnSignInBeginView.as_view(), name='webauthn-signin-begin'),

    # Sign in / sign out
    path('sign-in/', views.AttendanceSignInView.as_view(), name='attendance-sign-in'),
    path('sign-out/', views.AttendanceSignOutView.as_view(), name='attendance-sign-out'),

    # Field clock-in
    path('field-clock-in/', views.FieldClockInView.as_view(), name='field-clock-in'),
    path('admin/field-clock-ins/pending/', views.AdminPendingFieldClockInsView.as_view(), name='admin-pending-field-clockins'),
    path('admin/field-clock-ins/<int:attendance_id>/approve/', views.AdminApproveFieldClockInView.as_view(), name='admin-approve-field-clockin'),

    # Staff-facing
    path('my/today/', views.MyTodayAttendanceView.as_view(), name='my-today-attendance'),
    path('my/history/', views.MyAttendanceHistoryView.as_view(), name='my-attendance-history'),

    # Admin dashboard analytics
    path('admin/summary/', views.AdminAttendanceSummaryView.as_view(), name='admin-attendance-summary'),
    path('admin/staff-ranking/', views.AdminStaffRankingView.as_view(), name='admin-staff-ranking'),
    path('admin/trend/', views.AdminAttendanceTrendView.as_view(), name='admin-attendance-trend'),
    path('admin/department-breakdown/', views.AdminDepartmentBreakdownView.as_view(), name='admin-department-breakdown'),
    path('admin/monthly-overview/', views.AdminStaffMonthlyOverviewView.as_view(), name='admin-monthly-overview'),
    path('admin/table/', views.AdminAttendanceTableView.as_view(), name='admin-attendance-table'),
    path('admin/live-today/', views.AdminLiveTodayView.as_view(), name='admin-live-today'),
]
