from django.urls import path
from . import views

urlpatterns = [
    # ------------------------
    # Auth
    # ------------------------
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('change-password/', views.change_password, name='change_password'),

    # ------------------------
    # Dashboards
    # ------------------------
    path('dashboard/', views.dashboard, name='dashboard'),
    path('staff_dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('manager_dashboard/', views.manager_dashboard, name='manager_dashboard'),
    path('cluster_dashboard/', views.cluster_dashboard, name='cluster_dashboard'),
    path('owner_dashboard/', views.owner_dashboard, name='owner_dashboard'),
    path('admin_dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('export/users/', views.export_users_csv, name='export_users_csv'),

    # ------------------------
    # Tickets
    # ------------------------
    path('raise_ticket/', views.raise_ticket, name='raise_ticket'),
    path('raise_staff_log/', views.raise_staff_log, name='raise_staff_log'),
    path('iconnect_form/', views.iconnect_form_view, name='iconnect_form'),
    path('view_all_tickets/', views.view_all_tickets, name='view_all_tickets'),
    path("my-logs/", views.my_logs_view, name="my_logs"),


    # ------------------------
    # Ticket Actions
    # ------------------------
    path('ticket/<int:ticket_id>/reassign/', views.reassign_ticket, name='reassign_ticket'),
    path('ticket/<int:ticket_id>/close/', views.close_ticket, name='close_ticket'),
    path('ticket/<int:ticket_id>/confirm/', views.confirm_resolution, name='confirm_resolution'),
    path('ticket/<int:ticket_id>/resolve/', views.resolve_ticket, name='resolve_ticket'),

    # ------------------------
    # Owner/Staff Confirmation
    # ------------------------
    path('owner/confirm_ticket/<int:ticket_id>/', views.confirm_ticket_resolution, name='confirm_ticket_resolution'),
    path('staff/confirm_closure/<int:ticket_id>/', views.confirm_ticket_closure, name='staff_confirm_ticket_closure'),
    path("confirm_ticket_closure/<int:ticket_id>/", views.confirm_ticket_closure, name="confirm_ticket_closure"),
    path("acknowledge_log/<int:log_id>/", views.acknowledge_log, name="acknowledge_log"),
    path("my-tickets/", views.my_tickets_view, name="my_tickets"),



    # ------------------------
    # Cluster Manager Views
    # ------------------------
    path('view_kitchen_managers/', views.view_kitchen_managers, name='view_kitchen_managers'),
    path('view_kitchen_staff/', views.view_kitchen_staff, name='view_kitchen_staff'),
    path('view_kitchen_logs/', views.view_kitchen_logs, name='view_kitchen_logs'),
    path(
    "kitchen-log-report/",
    views.kitchen_log_report,
    name="kitchen_log_report"),

    # ------------------------
    # Cluster Manager Ticket Handling
    # ------------------------
    path('close_cluster_ticket/<int:ticket_id>/', views.close_cluster_ticket, name='close_cluster_ticket'),
    path('confirm_cluster_ticket/<int:ticket_id>/', views.confirm_cluster_ticket, name='confirm_cluster_ticket'),
    path("view_cluster_tickets/", views.view_cluster_tickets, name="view_cluster_tickets"),
    
    

    # ------------------------
    # Salary Slip
    # ------------------------
    path('salary_slip/', views.staff_salary_slip, name='staff_salary_slip'),

    # ------------------------
    # Order Photos
    # ------------------------

    path("upload-order-photo/", views.upload_order_photo, name="upload_order_photo"),
    path("view-order-photos/", views.view_order_photos, name="view_order_photos"),
    path("filter-order-photos/", views.filter_order_photos, name="filter_order_photos"),

    # urls.py
    path("cluster/update-staff-time/", views.update_staff_time, name="update_staff_time"),
    path("admin/ot-sac-list/", views.admin_ot_sac_list, name="admin_ot_sac_list"),
    path("cluster/ot-sac-list/", views.cluster_ot_sac_list, name="cluster_ot_sac_list"),
    path('export/staff-updates/', views.export_staff_updates_csv, name='export_staff_updates_csv'),

    path("attendance/punch-in/", views.punch_in, name="punch_in"),
    path("attendance/punch-out/", views.punch_out, name="punch_out"),
    path("cluster/attendance-report/",views.cluster_attendance_report,name="cluster_attendance_report"),



    # ------------------------
# Quality Feedback
# ------------------------
    path("raise_quality_feedback/",views.raise_quality_feedback,name="raise_quality_feedback",),
    path("view_quality_feedback/",views.view_quality_feedback,name="view_quality_feedback",),
    path("quality-feedback-analytics/", views.quality_feedback_analytics, name="quality_feedback_analytics"),
    path("acknowledge_quality_feedback/<int:feedback_id>/",views.acknowledge_quality_feedback,name="acknowledge_quality_feedback",),
    path(
    "bulk_upload_quality_feedback/",
    views.bulk_upload_quality_feedback,
    name="bulk_upload_quality_feedback",),
    path("export/quality-feedback/",views.export_quality_feedback_csv,name="export_quality_feedback_csv",),

    
]

