from django.apps import AppConfig


class DetectorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'detector'

    def ready(self):
        try:
            from .real_time_monitor import spam_monitor
            spam_monitor.start_monitoring()
        except Exception as e:
            print(f"Warning: Could not start spam monitor: {e}")
