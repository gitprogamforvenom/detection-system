from django.db import models
from django.contrib.auth.models import User

class BlockedEmail(models.Model):
    user_id = models.IntegerField(null=True, blank=True)
    email_text = models.TextField()
    blocked_at = models.DateTimeField(auto_now_add=True)
    confidence = models.FloatField(default=0.0)
    source = models.CharField(max_length=50, default='manual')
    risk_level = models.CharField(max_length=20, default='medium')
    
    def __str__(self):
        return f"Blocked: {self.email_text[:50]}..."
    
    class Meta:
        ordering = ['-blocked_at']

class UserFeedback(models.Model):
    """Store user feedback for model improvement"""
    user_id = models.IntegerField(null=True, blank=True)
    email_text = models.TextField()
    predicted_class = models.CharField(max_length=10)
    actual_class = models.CharField(max_length=10)
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Feedback: {self.predicted_class} -> {self.actual_class}"

class ModelMetrics(models.Model):
    """Track model performance metrics"""
    user_id = models.IntegerField(null=True, blank=True)
    accuracy = models.FloatField()
    precision = models.FloatField()
    recall = models.FloatField()
    f1_score = models.FloatField()
    training_date = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Metrics {self.training_date}: Acc={self.accuracy:.3f}"

class AlertSettings(models.Model):
    """Configuration for real-time alerts"""
    user_id = models.IntegerField(null=True, blank=True)
    alert_threshold = models.FloatField(default=80.0, help_text="Confidence threshold for alerts")
    email_notifications = models.BooleanField(default=True)
    notification_email = models.EmailField(blank=True)
    webhook_url = models.URLField(blank=True)
    check_interval = models.IntegerField(default=30, help_text="Check interval in seconds")
    high_volume_threshold = models.IntegerField(default=3, help_text="Number of emails to trigger volume alert")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Alert Settings (Threshold: {self.alert_threshold}%)"
    
    class Meta:
        verbose_name_plural = "Alert Settings"

class RealTimeAlert(models.Model):
    """Store real-time alerts"""
    SEVERITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical'),
    ]
    
    ALERT_TYPE_CHOICES = [
        ('HIGH_VOLUME', 'High Volume Spam'),
        ('CRITICAL_SPAM', 'Critical Spam Detected'),
        ('SYSTEM_ERROR', 'System Error'),
        ('MODEL_DRIFT', 'Model Performance Drift'),
    ]
    
    user_id = models.IntegerField(null=True, blank=True)
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    triggered_at = models.DateTimeField(auto_now_add=True)
    acknowledged = models.BooleanField(default=False)
    acknowledged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.alert_type} - {self.severity} ({self.triggered_at})"
    
    class Meta:
        ordering = ['-triggered_at']

class PowerBIExport(models.Model):
    """Track Power BI data exports"""
    user_id = models.IntegerField(null=True, blank=True)
    export_type = models.CharField(max_length=50)
    date_range_days = models.IntegerField()
    exported_at = models.DateTimeField(auto_now_add=True)
    exported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    file_size = models.IntegerField(null=True, blank=True)
    record_count = models.IntegerField(null=True, blank=True)
    
    def __str__(self):
        return f"Power BI Export: {self.export_type} ({self.exported_at})"
    
    class Meta:
        ordering = ['-exported_at']