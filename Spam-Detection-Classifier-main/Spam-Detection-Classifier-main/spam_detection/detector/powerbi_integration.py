import pandas as pd
import json
from datetime import datetime, timedelta
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from .models import BlockedEmail, UserFeedback, ModelMetrics, RealTimeAlert
import io
import base64

class PowerBIIntegration:
    def __init__(self):
        self.data_sources = {
            'blocked_emails': self._get_blocked_emails_data,
            'model_metrics': self._get_model_metrics_data,
            'alert_summary': self._get_alert_summary_data,
            'feedback_analysis': self._get_feedback_analysis_data,
            'trend_analysis': self._get_trend_analysis_data
        }
    
    def export_to_powerbi_format(self, data_type='all', date_range=30, user_id=None, user_role=None):
        """Export data in Power BI compatible format"""
        end_date = timezone.now()
        start_date = end_date - timedelta(days=date_range)
        
        if data_type == 'all':
            # Export all data sources
            datasets = {}
            for source_name, source_func in self.data_sources.items():
                datasets[source_name] = source_func(start_date, end_date, user_id, user_role)
            return datasets
        elif data_type in self.data_sources:
            # Export specific data source
            return {data_type: self.data_sources[data_type](start_date, end_date, user_id, user_role)}
        else:
            raise ValueError(f"Unknown data type: {data_type}")
    
    def _get_blocked_emails_data(self, start_date, end_date, user_id, user_role):
        """Get blocked emails data for Power BI"""
        qs = BlockedEmail.objects.filter(blocked_at__range=[start_date, end_date])
        if user_role != 'admin' and user_id is not None:
            qs = qs.filter(user_id=user_id)
        blocked_emails = qs.values(
            'id', 'blocked_at', 'confidence', 'source'
        )
        
        df = pd.DataFrame(list(blocked_emails))
        if not df.empty:
            df['blocked_date'] = pd.to_datetime(df['blocked_at']).dt.date
            df['blocked_hour'] = pd.to_datetime(df['blocked_at']).dt.hour
            df['confidence_category'] = pd.cut(
                df['confidence'], 
                bins=[0, 70, 85, 95, 100], 
                labels=['Medium', 'High', 'Very High', 'Critical']
            )
        
        return df.to_dict('records')
    
    def _get_model_metrics_data(self, start_date, end_date, user_id, user_role):
        """Get model performance metrics for Power BI"""
        qs = ModelMetrics.objects.filter(training_date__range=[start_date, end_date])
        if user_role != 'admin' and user_id is not None:
            qs = qs.filter(user_id=user_id)
        metrics = qs.values(
            'accuracy', 'precision', 'recall', 'f1_score', 'training_date'
        )
        
        df = pd.DataFrame(list(metrics))
        if not df.empty:
            df['training_date'] = pd.to_datetime(df['training_date'])
        
        return df.to_dict('records')
    
    def _get_alert_summary_data(self, start_date, end_date, user_id, user_role):
        """Get alert summary data for Power BI"""
        try:
            qs = RealTimeAlert.objects.filter(triggered_at__range=[start_date, end_date])
            if user_role != 'admin' and user_id is not None:
                qs = qs.filter(user_id=user_id)
            alerts = qs.values(
                'alert_type', 'severity', 'triggered_at'
            )
            
            df = pd.DataFrame(list(alerts))
            if not df.empty:
                df['alert_date'] = pd.to_datetime(df['triggered_at']).dt.date
                df['alert_hour'] = pd.to_datetime(df['triggered_at']).dt.hour
            
            return df.to_dict('records')
        except:
            return []
    
    def _get_feedback_analysis_data(self, start_date, end_date, user_id, user_role):
        """Get user feedback analysis for Power BI"""
        qs = UserFeedback.objects.filter(created_at__range=[start_date, end_date])
        if user_role != 'admin' and user_id is not None:
            qs = qs.filter(user_id=user_id)
        feedback = qs.values(
            'predicted_class', 'actual_class', 'created_at'
        )
        
        df = pd.DataFrame(list(feedback))
        if not df.empty:
            df['feedback_date'] = pd.to_datetime(df['created_at']).dt.date
            df['is_correct'] = df['predicted_class'] == df['actual_class']
        
        return df.to_dict('records')
    
    def _get_trend_analysis_data(self, start_date, end_date, user_id, user_role):
        """Get trend analysis data for Power BI"""
        qs = BlockedEmail.objects.filter(blocked_at__range=[start_date, end_date])
        if user_role != 'admin' and user_id is not None:
            qs = qs.filter(user_id=user_id)
        blocked_emails = qs
        
        # Group by date and calculate metrics
        daily_data = []
        current_date = start_date.date()
        end_date_only = end_date.date()
        
        while current_date <= end_date_only:
            day_start = timezone.make_aware(datetime.combine(current_date, datetime.min.time()))
            day_end = day_start + timedelta(days=1)
            
            day_blocked = blocked_emails.filter(blocked_at__range=[day_start, day_end])
            
            daily_data.append({
                'date': current_date.isoformat(),
                'total_blocked': day_blocked.count(),
                'high_confidence_blocked': day_blocked.filter(confidence__gte=85).count(),
                'critical_blocked': day_blocked.filter(confidence__gte=95).count(),
                'avg_confidence': float(day_blocked.aggregate(
                    avg_conf=models.Avg('confidence')
                )['avg_conf'] or 0)
            })
            
            current_date += timedelta(days=1)
        
        return daily_data
    
    def generate_powerbi_dashboard_config(self):
        """Generate Power BI dashboard configuration"""
        config = {
            "version": "1.0",
            "name": "Spam Detection Analytics Dashboard",
            "description": "Comprehensive spam detection analytics and monitoring",
            "datasets": [
                {
                    "name": "BlockedEmails",
                    "description": "Blocked spam emails data",
                    "columns": [
                        {"name": "id", "type": "Integer", "description": "Email ID"},
                        {"name": "blocked_at", "type": "DateTime", "description": "Block timestamp"},
                        {"name": "confidence", "type": "Decimal", "description": "Detection confidence"},
                        {"name": "source", "type": "String", "description": "Detection source"},
                        {"name": "blocked_date", "type": "Date", "description": "Block date"},
                        {"name": "blocked_hour", "type": "Integer", "description": "Block hour"},
                        {"name": "confidence_category", "type": "String", "description": "Confidence level"}
                    ]
                },
                {
                    "name": "ModelMetrics",
                    "description": "ML model performance metrics",
                    "columns": [
                        {"name": "accuracy", "type": "Decimal", "description": "Model accuracy"},
                        {"name": "precision", "type": "Decimal", "description": "Model precision"},
                        {"name": "recall", "type": "Decimal", "description": "Model recall"},
                        {"name": "f1_score", "type": "Decimal", "description": "F1 score"},
                        {"name": "training_date", "type": "DateTime", "description": "Training date"}
                    ]
                },
                {
                    "name": "TrendAnalysis",
                    "description": "Daily spam detection trends",
                    "columns": [
                        {"name": "date", "type": "Date", "description": "Analysis date"},
                        {"name": "total_blocked", "type": "Integer", "description": "Total blocked emails"},
                        {"name": "high_confidence_blocked", "type": "Integer", "description": "High confidence blocks"},
                        {"name": "critical_blocked", "type": "Integer", "description": "Critical blocks"},
                        {"name": "avg_confidence", "type": "Decimal", "description": "Average confidence"}
                    ]
                }
            ],
            "suggested_visualizations": [
                {
                    "type": "Line Chart",
                    "title": "Spam Detection Trends",
                    "x_axis": "date",
                    "y_axis": "total_blocked",
                    "dataset": "TrendAnalysis"
                },
                {
                    "type": "Pie Chart",
                    "title": "Confidence Level Distribution",
                    "values": "confidence_category",
                    "dataset": "BlockedEmails"
                },
                {
                    "type": "Gauge",
                    "title": "Model Accuracy",
                    "value": "accuracy",
                    "dataset": "ModelMetrics"
                },
                {
                    "type": "Bar Chart",
                    "title": "Hourly Spam Distribution",
                    "x_axis": "blocked_hour",
                    "y_axis": "count",
                    "dataset": "BlockedEmails"
                }
            ],
            "kpis": [
                {
                    "name": "Total Blocked Emails",
                    "description": "Total number of blocked spam emails",
                    "calculation": "COUNT(BlockedEmails.id)"
                },
                {
                    "name": "Average Confidence",
                    "description": "Average detection confidence",
                    "calculation": "AVERAGE(BlockedEmails.confidence)"
                },
                {
                    "name": "Model Accuracy",
                    "description": "Latest model accuracy",
                    "calculation": "LATEST(ModelMetrics.accuracy)"
                }
            ]
        }
        
        return config
    
    def export_to_csv(self, data_type='all', date_range=30, user_id=None, user_role=None):
        """Export data to CSV format for Power BI import"""
        datasets = self.export_to_powerbi_format(data_type, date_range, user_id, user_role)
        
        if len(datasets) == 1:
            # Single dataset
            df = pd.DataFrame(list(datasets.values())[0])
            return df.to_csv(index=False)
        else:
            # Multiple datasets - create a zip file
            import zipfile
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for name, data in datasets.items():
                    df = pd.DataFrame(data)
                    csv_data = df.to_csv(index=False)
                    zip_file.writestr(f"{name}.csv", csv_data)
            
            zip_buffer.seek(0)
            return zip_buffer.getvalue()
    
    def export_to_json(self, data_type='all', date_range=30, user_id=None, user_role=None):
        """Export data to JSON format for Power BI REST API"""
        datasets = self.export_to_powerbi_format(data_type, date_range, user_id, user_role)
        
        # Add metadata
        export_data = {
            "export_timestamp": timezone.now().isoformat(),
            "date_range_days": date_range,
            "datasets": datasets,
            "dashboard_config": self.generate_powerbi_dashboard_config()
        }
        
        return json.dumps(export_data, default=str, indent=2)

# Global Power BI integration instance
powerbi_integration = PowerBIIntegration()