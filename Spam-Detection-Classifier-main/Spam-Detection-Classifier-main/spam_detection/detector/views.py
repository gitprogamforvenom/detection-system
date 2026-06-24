import pandas as pd
import os
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from .forms import MessageForm, FeedbackForm
from .simple_ml import spam_detector
from .models import BlockedEmail, UserFeedback, ModelMetrics, AlertSettings, RealTimeAlert, PowerBIExport
# from .real_time_monitor import spam_monitor  # Disabled for now
from .powerbi_integration import powerbi_integration

# Initialize and train model on startup
model_path = os.path.join(settings.BASE_DIR, 'spam_model.pkl')
data_path = os.path.join(settings.BASE_DIR, 'emails.csv')


from django.db.models import Q

def filter_by_user(queryset, request):
    if not request.authenticated_user_id:
        return queryset.none()
    if request.authenticated_user_role == 'admin':
        return queryset
    return queryset.filter(Q(user_id=request.authenticated_user_id) | Q(user_id__isnull=True))

def predict_message(message):
    if not spam_detector.is_trained:
        if os.path.exists(model_path):
            spam_detector.load_model(model_path)
            
    if not spam_detector.is_trained and os.path.exists(data_path):
        try:
            spam_detector.train(data_path)
            spam_detector.save_model(model_path)
        except Exception as e:
            print(f"Training error: {e}")
            
    try:
        result = spam_detector.predict(message)
        return {
            'result': result['prediction'],
            'ham_percentage': round(result['ham_probability'], 2),
            'spam_percentage': round(result['spam_probability'], 2),
            'confidence': round(result['confidence'], 2)
        }
    except Exception as e:
        print(f"Prediction error: {e}")
        return {
            'result': 'Ham',
            'ham_percentage': 85.0,
            'spam_percentage': 15.0,
            'confidence': 85.0
        }

def Home(request):
    prediction = None
    error = None
    blocked_count = filter_by_user(BlockedEmail.objects.all(), request).count()
    recent_alerts = filter_by_user(RealTimeAlert.objects.filter(acknowledged=False), request)[:5]
    
    if request.method == 'POST':
        form = MessageForm(request.POST, request.FILES)
        if form.is_valid():
            message = form.cleaned_data['text']
            email_file = form.cleaned_data['email_file']
            
            if email_file:
                try:
                    file_name = email_file.name.lower()
                    
                    if file_name.endswith('.csv'):
                        try:
                            file_content = email_file.read().decode('utf-8')
                            import io
                            try:
                                csv_data = pd.read_csv(io.StringIO(file_content))
                            except:
                                csv_data = pd.read_csv(io.StringIO(file_content), sep=';')
                            
                            if csv_data.empty:
                                raise ValueError("CSV file is empty")
                            
                            processed_count = 0
                            spam_detected = 0
                            ham_detected = 0
                            
                            email_col = None
                            for col in csv_data.columns:
                                col_lower = str(col).lower().strip()
                                if col_lower in ['text', 'message', 'email', 'content', 'body', 'sms', 'v2']:
                                    email_col = col
                                    break
                            
                            if email_col is None:
                                max_avg_len = 0
                                for col in csv_data.columns:
                                    try:
                                        avg_len = csv_data[col].astype(str).str.len().mean()
                                        if avg_len > max_avg_len:
                                            max_avg_len = avg_len
                                            email_col = col
                                    except:
                                        continue
                            
                            if email_col is None:
                                email_col = csv_data.columns[0]
                            
                            for idx, row in csv_data.iterrows():
                                if processed_count >= 50:
                                    break
                                
                                try:
                                    email_text = str(row[email_col]).strip()
                                    if email_text in ['nan', 'NaN', 'None', ''] or len(email_text) < 5:
                                        continue
                                    
                                    pred = predict_message(email_text)
                                    processed_count += 1
                                    
                                    if pred['result'] == 'Spam':
                                        spam_detected += 1
                                        if pred['confidence'] > 70:
                                            risk_level = 'critical' if pred['confidence'] > 95 else 'high' if pred['confidence'] > 85 else 'medium'
                                            BlockedEmail.objects.create(
                                                user_id=request.authenticated_user_id,
                                                email_text=email_text[:1000],
                                                confidence=pred['confidence'],
                                                source='csv_upload',
                                                risk_level=risk_level
                                            )
                                            try:
                                                import mysql.connector
                                                mysql_conn = mysql.connector.connect(
                                                    host=os.environ.get("DB_HOST", "mysql-kuif.railway.internal"),
                                                    port=int(os.environ.get("DB_PORT", 3306)),
                                                    user=os.environ.get("DB_USER", "root"),
                                                    password=os.environ.get("DB_PASSWORD", "smbIROLNRlRhchdzTGuNaqNWdHkBKaay"),
                                                    database=os.environ.get("DB_DATABASE", "railway")
                                                )
                                                mysql_cursor = mysql_conn.cursor()
                                                mysql_cursor.execute(
                                                    "INSERT INTO alerts (alert_type, decision, score, blockchain_hash, user_id) VALUES (%s, %s, %s, %s, %s)",
                                                    ('email', 'spam', pred['confidence'] / 100.0, None, request.authenticated_user_id)
                                                )
                                                mysql_conn.commit()
                                                mysql_cursor.close()
                                                mysql_conn.close()
                                            except Exception as err:
                                                print(f"MySQL Alert insertion error: {err}")
                                    else:
                                        ham_detected += 1
                                        
                                except Exception as e:
                                    print(f"Error processing row {idx}: {e}")
                                    continue
                            
                            if processed_count == 0:
                                raise ValueError("No valid emails found in CSV")
                            
                            prediction = {
                                'result': 'Dataset Processed',
                                'processed_count': processed_count,
                                'spam_detected': spam_detected,
                                'ham_count': ham_detected,
                                'spam_percentage': round((spam_detected / processed_count * 100) if processed_count > 0 else 0, 1),
                                'ham_percentage': round((ham_detected / processed_count * 100) if processed_count > 0 else 0, 1),
                                'column_used': str(email_col)
                            }
                            
                        except Exception as csv_error:
                            error = f"CSV processing error: {str(csv_error)}"
                            print(f"CSV Error: {csv_error}")
                    else:
                        file_content = email_file.read().decode('utf-8')
                        prediction = predict_message(file_content)
                        
                        risk_level = 'low'
                        if prediction['confidence'] > 95:
                            risk_level = 'critical'
                        elif prediction['confidence'] > 85:
                            risk_level = 'high'
                        elif prediction['confidence'] > 70:
                            risk_level = 'medium'
                        
                        if prediction['result'] == 'Spam' and prediction['confidence'] > 70:
                            BlockedEmail.objects.create(
                                user_id=request.authenticated_user_id,
                                email_text=file_content[:1000],
                                confidence=prediction['confidence'],
                                source='file_upload',
                                risk_level=risk_level
                            )
                            try:
                                import mysql.connector
                                mysql_conn = mysql.connector.connect(
                                    host=os.environ.get("DB_HOST", "mysql-kuif.railway.internal"),
                                    port=int(os.environ.get("DB_PORT", 3306)),
                                    user=os.environ.get("DB_USER", "root"),
                                    password=os.environ.get("DB_PASSWORD", "smbIROLNRlRhchdzTGuNaqNWdHkBKaay"),
                                    database=os.environ.get("DB_DATABASE", "railway")
                                )
                                mysql_cursor = mysql_conn.cursor()
                                mysql_cursor.execute(
                                    "INSERT INTO alerts (alert_type, decision, score, blockchain_hash, user_id) VALUES (%s, %s, %s, %s, %s)",
                                    ('email', 'spam', prediction['confidence'] / 100.0, None, request.authenticated_user_id)
                                )
                                mysql_conn.commit()
                                mysql_cursor.close()
                                mysql_conn.close()
                            except Exception as err:
                                print(f"MySQL Alert insertion error: {err}")
                        
                except Exception as e:
                    error = f"Error reading file: {str(e)}"
                    print(f"File processing error: {e}")
            elif message:
                prediction = predict_message(message)
                
                risk_level = 'low'
                if prediction['confidence'] > 95:
                    risk_level = 'critical'
                elif prediction['confidence'] > 85:
                    risk_level = 'high'
                elif prediction['confidence'] > 70:
                    risk_level = 'medium'
                
                if prediction and prediction['result'] == 'Spam' and prediction['confidence'] > 70:
                    BlockedEmail.objects.create(
                        user_id=request.authenticated_user_id,
                        email_text=message[:1000],
                        confidence=prediction['confidence'],
                        source='manual_input',
                        risk_level=risk_level
                    )
                    try:
                        import mysql.connector
                        mysql_conn = mysql.connector.connect(
                            host=os.environ.get("DB_HOST", "mysql-kuif.railway.internal"),
                            port=int(os.environ.get("DB_PORT", 3306)),
                            user=os.environ.get("DB_USER", "root"),
                            password=os.environ.get("DB_PASSWORD", "smbIROLNRlRhchdzTGuNaqNWdHkBKaay"),
                            database=os.environ.get("DB_DATABASE", "railway")
                        )
                        mysql_cursor = mysql_conn.cursor()
                        mysql_cursor.execute(
                            "INSERT INTO alerts (alert_type, decision, score, blockchain_hash, user_id) VALUES (%s, %s, %s, %s, %s)",
                            ('email', 'spam', prediction['confidence'] / 100.0, None, request.authenticated_user_id)
                        )
                        mysql_conn.commit()
                        mysql_cursor.close()
                        mysql_conn.close()
                    except Exception as err:
                        print(f"MySQL Alert insertion error: {err}")
            else:
                error = "Please enter text or upload a file"
    else:
        form = MessageForm()
        
    return render(request, 'home.html', {
        'form': form, 
        'prediction': prediction,
        'error': error,
        'blocked_count': blocked_count,
        'recent_alerts': recent_alerts
    })

def documentation(request):
    return render(request, 'documentation.html')

def blocked_emails(request):
    """View blocked spam emails"""
    blocked = filter_by_user(BlockedEmail.objects.all(), request).order_by('-blocked_at')[:50]
    return render(request, 'blocked_emails.html', {'blocked_emails': blocked})

def real_time_alerts(request):
    """View and manage real-time alerts"""
    alerts = filter_by_user(RealTimeAlert.objects.all(), request).order_by('-triggered_at')[:100]
    unacknowledged_count = filter_by_user(RealTimeAlert.objects.filter(acknowledged=False), request).count()
    
    return render(request, 'alerts.html', {
        'alerts': alerts,
        'unacknowledged_count': unacknowledged_count
    })

def acknowledge_alert(request, alert_id):
    """Acknowledge a real-time alert"""
    if request.method == 'POST':
        try:
            alert = filter_by_user(RealTimeAlert.objects, request).get(id=alert_id)
            alert.acknowledged = True
            alert.acknowledged_at = timezone.now()
            alert.save()
            return JsonResponse({'status': 'success'})
        except RealTimeAlert.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Alert not found'})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

def alert_settings(request):
    """Configure alert settings"""
    if not request.authenticated_user_id:
        return redirect('home')
        
    settings_obj, created = AlertSettings.objects.get_or_create(user_id=request.authenticated_user_id)
    
    if request.method == 'POST':
        settings_obj.alert_threshold = float(request.POST.get('alert_threshold', 80.0))
        settings_obj.email_notifications = request.POST.get('email_notifications') == 'on'
        settings_obj.notification_email = request.POST.get('notification_email', '')
        settings_obj.webhook_url = request.POST.get('webhook_url', '')
        settings_obj.check_interval = int(request.POST.get('check_interval', 30))
        settings_obj.high_volume_threshold = int(request.POST.get('high_volume_threshold', 3))
        settings_obj.save()
        
        messages.success(request, 'Alert settings updated successfully!')
        return redirect('alert_settings')
    
    return render(request, 'alert_settings.html', {'settings': settings_obj})

def powerbi_export(request):
    """Export data for Power BI"""
    if request.method == 'POST':
        export_type = request.POST.get('export_type', 'all')
        date_range = int(request.POST.get('date_range', 30))
        format_type = request.POST.get('format', 'json')
        
        try:
            if format_type == 'csv':
                data = powerbi_integration.export_to_csv(export_type, date_range, request.authenticated_user_id, request.authenticated_user_role)
                response = HttpResponse(data, content_type='text/csv')
                response['Content-Disposition'] = f'attachment; filename="spam_data_{export_type}_{request.authenticated_user_id}.csv"'
            else:
                data = powerbi_integration.export_to_json(export_type, date_range, request.authenticated_user_id, request.authenticated_user_role)
                response = HttpResponse(data, content_type='application/json')
                response['Content-Disposition'] = f'attachment; filename="spam_data_{export_type}_{request.authenticated_user_id}.json"'
            
            # Log the export
            PowerBIExport.objects.create(
                user_id=request.authenticated_user_id,
                export_type=export_type,
                date_range_days=date_range,
                file_size=len(data),
                record_count=0
            )
            
            return response
            
        except Exception as e:
            messages.error(request, f'Export failed: {str(e)}')
    
    export_history = filter_by_user(PowerBIExport.objects.all(), request).order_by('-exported_at')[:10]
    
    return render(request, 'powerbi_export.html', {
        'export_history': export_history
    })

def powerbi_dashboard_config(request):
    """Get Power BI dashboard configuration"""
    config = powerbi_integration.generate_powerbi_dashboard_config()
    return JsonResponse(config)

def retrain_model(request):
    """Retrain the model with latest data"""
    if request.method == 'POST':
        try:
            accuracy = spam_detector.train(data_path)
            spam_detector.save_model(model_path)
            
            ModelMetrics.objects.create(
                user_id=request.authenticated_user_id,
                accuracy=accuracy,
                precision=0.0,
                recall=0.0,
                f1_score=0.0
            )
            
            messages.success(request, f"Model retrained successfully! New accuracy: {accuracy:.4f}")
        except Exception as e:
            messages.error(request, f"Error retraining model: {str(e)}")
    
    return render(request, 'retrain.html')

def submit_feedback(request):
    """Handle user feedback submission"""
    if request.method == 'POST':
        correct = request.POST.get('correct')
        comments = request.POST.get('comments', '')
        
        UserFeedback.objects.create(
            user_id=request.authenticated_user_id,
            email_text="",
            predicted_class="",
            actual_class="spam" if correct == "no" else "ham",
            feedback=comments
        )
        
        messages.success(request, "Thank you for your feedback!")
        return redirect('home')
    
    return redirect('home')

def model_metrics(request):
    """Display model performance metrics"""
    latest_metrics = filter_by_user(ModelMetrics.objects.all(), request).order_by('-training_date').first()
    all_metrics = filter_by_user(ModelMetrics.objects.all(), request).order_by('-training_date')[:10]
    
    feedback_stats = {
        'total_feedback': filter_by_user(UserFeedback.objects.all(), request).count(),
        'correct_predictions': filter_by_user(UserFeedback.objects.filter(predicted_class='spam'), request).count(),
    }
    
    return render(request, 'metrics.html', {
        'latest_metrics': latest_metrics,
        'all_metrics': all_metrics,
        'feedback_stats': feedback_stats,
        'blocked_count': filter_by_user(BlockedEmail.objects.all(), request).count()
    })

def api_status(request):
    """API endpoint for system status"""
    status = {
        'monitoring_active': False,
        'total_blocked': filter_by_user(BlockedEmail.objects.all(), request).count(),
        'unacknowledged_alerts': filter_by_user(RealTimeAlert.objects.filter(acknowledged=False), request).count(),
        'model_accuracy': 0.0,
        'last_training': None
    }
    
    latest_metrics = filter_by_user(ModelMetrics.objects.all(), request).order_by('-training_date').first()
    if latest_metrics:
        status['model_accuracy'] = latest_metrics.accuracy
        status['last_training'] = latest_metrics.training_date.isoformat()
        
    return JsonResponse(status)