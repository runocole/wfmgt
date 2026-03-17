from django.urls import path
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse
from . import views

# CSRF token endpoint
@ensure_csrf_cookie
def get_csrf_token(request):
    return JsonResponse({'detail': 'CSRF cookie set'})

urlpatterns = [
    # ============================================
    # HOME ENDPOINTS 
    # ============================================
    
    # Auth endpoints
    path('auth/register/', views.RegisterView.as_view(), name='register'),
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('auth/logout/', views.LogoutView.as_view(), name='logout'),
    path('auth/me/', views.CurrentUserView.as_view(), name='current-user'),
    path('auth/csrf/', get_csrf_token, name='csrf'),  # ADD THIS LINE
    
    # App endpoints
    path('apps/', views.AppListView.as_view(), name='app-list'),
    path('apps/<int:pk>/', views.AppDetailView.as_view(), name='app-detail'),
    
    # Subscription endpoints
    path('subscriptions/', views.UserSubscriptionView.as_view(), name='user-subscriptions'),
    path('subscriptions/<int:subscription_id>/pay/', views.SubscriptionPaymentView.as_view(), name='subscription-pay'),
    path('apps/<int:app_id>/access/', views.CheckAppAccessView.as_view(), name='check-access'),
    path('my-subscriptions/', views.UserSubscriptionsListView.as_view(), name='my-subscriptions'),
    
    # ============================================
    # NEW WORK LOG SYSTEM ENDPOINTS
    # ============================================
    
    # Staff Profile
    path('worklog/profile/', views.StaffProfileView.as_view(), name='worklog-profile'),
    path('worklog/staff-list/', views.StaffListView.as_view(), name='staff-list'),
    # Work Logs (Staff)
    path('worklog/entries/', views.WorkLogListCreateView.as_view(), name='worklog-list'),
    path('worklog/entries/<int:pk>/', views.WorkLogDetailView.as_view(), name='worklog-detail'),
    path('worklog/team/', views.TeamWorkLogsView.as_view(), name='worklog-team'),
    path('worklog/today/', views.TodayWorkLogsView.as_view(), name='worklog-today'),
    
    # Dashboard
    path('worklog/dashboard/', views.StaffDashboardView.as_view(), name='worklog-dashboard'),
    
    # Leave Requests
    path('worklog/leaves/', views.LeaveListCreateView.as_view(), name='worklog-leaves'),
    path('worklog/leaves/<int:pk>/', views.LeaveDetailView.as_view(), name='worklog-leave-detail'),
    
    # ============================================
    # ADMIN ENDPOINTS 
    # ============================================
    path('admin/worklog/staff/create/', views.AdminCreateStaffView.as_view(), name='admin-create-staff'),
    path('admin/worklog/export/', views.AdminExportView.as_view(), name='admin-export'),
    
    # Staff Management
    path('admin/worklog/staff/', views.AdminStaffListView.as_view(), name='admin-worklog-staff'),
    
    # Analytics
    path('admin/worklog/rankings/', views.AdminRankingView.as_view(), name='admin-worklog-rankings'),
    path('admin/worklog/summary/', views.AdminSummaryView.as_view(), name='admin-worklog-summary'),
    
    # All Work Logs (with filters)
    path('admin/worklog/all/', views.AdminWorkLogsView.as_view(), name='admin-worklog-all'),
    
    # Leave Management
    path('admin/worklog/leaves/', views.AdminLeaveRequestsView.as_view(), name='admin-worklog-leaves'),
    path('admin/worklog/leaves/<int:leave_id>/approve/', views.AdminApproveLeaveView.as_view(), name='admin-worklog-leave-approve'),
]