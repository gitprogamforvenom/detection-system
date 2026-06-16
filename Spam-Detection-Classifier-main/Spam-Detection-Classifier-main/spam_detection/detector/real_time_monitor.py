import threading
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from .models import BlockedEmail, AlertSettings, RealTimeAlert
import logging

logger = logging.getLogger(__name__)

class RealTimeSpamMonitor:
    def __init__(self):
        self.monitoring = False
        self.monitor_thread = None
        self.alert_threshold = 80.0  # Default threshold
        self.check_interval = 30  # Check every 30 seconds
        
    def start_monitoring(self):
        """Start the background monitoring system"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("Real-time spam monitoring started")
    
    def stop_monitoring(self):
        """Stop the background monitoring system"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
        logger.info("Real-time spam monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                self._check_recent_activity()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.check_interval)
    
    def _check_recent_activity(self):
        """Check for recent high-risk spam activity"""
        # Get recent blocked emails (last 5 minutes)
        recent_time = timezone.now() - timezone.timedelta(minutes=5)
        recent_blocks = BlockedEmail.objects.filter(
            blocked_at__gte=recent_time,
            confidence__gte=self.alert_threshold
        )
        
        if recent_blocks.count() >= 3:  # 3 or more high-confidence spam in 5 minutes
            self._trigger_alert(
                alert_type='HIGH_VOLUME',
                message=f"High volume spam detected: {recent_blocks.count()} emails blocked in 5 minutes",
                severity='HIGH',
                data={'count': recent_blocks.count(), 'threshold': self.alert_threshold}
            )
        
        # Check for extremely high confidence spam (95%+)
        critical_spam = recent_blocks.filter(confidence__gte=95.0)
        for spam in critical_spam:
            self._trigger_alert(
                alert_type='CRITICAL_SPAM',
                message=f"Critical spam detected with {spam.confidence:.1f}% confidence",
                severity='CRITICAL',
                data={'confidence': spam.confidence, 'email_id': spam.id}
            )
    
    def _trigger_alert(self, alert_type, message, severity, data=None):
        """Trigger a real-time alert"""
        try:
            # Save alert to database
            alert = RealTimeAlert.objects.create(
                alert_type=alert_type,
                message=message,
                severity=severity,
                data=data or {},
                triggered_at=timezone.now()
            )
            
            # Send notifications based on settings
            self._send_notifications(alert)
            
            logger.warning(f"Alert triggered: {alert_type} - {message}")
            
        except Exception as e:
            logger.error(f"Error triggering alert: {e}")
    
    def _send_notifications(self, alert):
        """Send alert notifications via configured channels"""
        try:
            settings_obj = AlertSettings.objects.first()
            if not settings_obj:
                return
            
            if settings_obj.email_notifications and settings_obj.notification_email:
                self._send_email_alert(alert, settings_obj.notification_email)
            
            # Add webhook notifications if configured
            if settings_obj.webhook_url:
                self._send_webhook_alert(alert, settings_obj.webhook_url)
                
        except Exception as e:
            logger.error(f"Error sending notifications: {e}")
    
    def _send_email_alert(self, alert, email):
        """Send email notification"""
        try:
            subject = f"🚨 Spam Alert: {alert.alert_type}"
            message = f"""
            Alert Type: {alert.alert_type}
            Severity: {alert.severity}
            Time: {alert.triggered_at}
            
            Message: {alert.message}
            
            Data: {alert.data}
            
            This is an automated alert from your Spam Detection System.
            """
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False
            )
            
        except Exception as e:
            logger.error(f"Error sending email alert: {e}")
    
    def _send_webhook_alert(self, alert, webhook_url):
        """Send webhook notification"""
        import requests
        try:
            payload = {
                'alert_type': alert.alert_type,
                'severity': alert.severity,
                'message': alert.message,
                'timestamp': alert.triggered_at.isoformat(),
                'data': alert.data
            }
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            
        except Exception as e:
            logger.error(f"Error sending webhook alert: {e}")
    
    def update_settings(self, threshold=None, interval=None):
        """Update monitoring settings"""
        if threshold is not None:
            self.alert_threshold = threshold
        if interval is not None:
            self.check_interval = interval

# Global monitor instance
spam_monitor = RealTimeSpamMonitor()