from django.urls import path
from . import views

urlpatterns = [
    path('', views.Home, name='home'),
    path('documentation/', views.documentation, name='documentation'),
    path('blocked/', views.blocked_emails, name='blocked_emails'),
    path('retrain/', views.retrain_model, name='retrain_model'),
    path('feedback/', views.submit_feedback, name='submit_feedback'),
    path('metrics/', views.model_metrics, name='model_metrics'),
    
    # Real-time alerts
    path('alerts/', views.real_time_alerts, name='real_time_alerts'),
    path('alerts/acknowledge/<int:alert_id>/', views.acknowledge_alert, name='acknowledge_alert'),
    path('alerts/settings/', views.alert_settings, name='alert_settings'),
    
    # Power BI Integration
    path('powerbi/export/', views.powerbi_export, name='powerbi_export'),
    path('powerbi/config/', views.powerbi_dashboard_config, name='powerbi_config'),
    
    # API endpoints
    path('api/status/', views.api_status, name='api_status'),
]