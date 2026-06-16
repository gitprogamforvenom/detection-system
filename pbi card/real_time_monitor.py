"""
Real-time Fraud Monitoring System
Provides live alerts and continuous monitoring
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import threading
import time

class FraudMonitor:
    """Real-time fraud monitoring and alerting system"""
    
    def __init__(self, db_path='fraudguard.db'):
        self.db_path = db_path
        self.alert_thresholds = {
            'high_fraud_rate': 0.05,  # 5% fraud rate triggers alert
            'critical_fraud_rate': 0.10,  # 10% fraud rate triggers critical alert
            'high_risk_score': 0.8,  # Individual transaction risk score
            'velocity_threshold': 10,  # Transactions per hour per user
            'amount_threshold': 1000  # High amount threshold
        }
        self.monitoring = False
        self.alerts = []
    
    def start_monitoring(self):
        """Start real-time monitoring in background thread"""
        self.monitoring = True
        monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor_thread.start()
        print('Real-time fraud monitoring started')
    
    def stop_monitoring(self):
        """Stop real-time monitoring"""
        self.monitoring = False
        print('Real-time fraud monitoring stopped')
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                self._check_fraud_patterns()
                self._check_velocity_anomalies()
                self._check_amount_anomalies()
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                print(f"Monitoring error: {e}")
                time.sleep(60)  # Wait longer on error
    
    def _check_fraud_patterns(self):
        """Check for unusual fraud patterns grouped by user"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            recent_stats = pd.read_sql_query('''
                SELECT 
                    user_id,
                    COUNT(*) as total,
                    SUM(is_fraud) as fraud_count,
                    AVG(fraud_score) as avg_score
                FROM fraud_results 
                WHERE datetime(timestamp) > datetime('now', '-1 hour')
                GROUP BY user_id
            ''', conn)
            
            for _, row in recent_stats.iterrows():
                user_id = row['user_id']
                if not user_id:
                    continue
                total = row['total']
                if total > 10:
                    fraud_rate = row['fraud_count'] / total
                    if fraud_rate >= self.alert_thresholds['critical_fraud_rate']:
                        self._create_alert(user_id, 'critical', f'Critical fraud rate: {fraud_rate:.1%} in last hour')
                    elif fraud_rate >= self.alert_thresholds['high_fraud_rate']:
                        self._create_alert(user_id, 'high', f'High fraud rate: {fraud_rate:.1%} in last hour')
            conn.close()
        except Exception as e:
            print(f"Pattern check error: {e}")
    
    def _check_velocity_anomalies(self):
        """Check for transaction velocity anomalies grouped by user"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            velocity_check = pd.read_sql_query('''
                SELECT 
                    user_id,
                    COUNT(*) as tx_count,
                    AVG(fraud_score) as avg_risk
                FROM fraud_results 
                WHERE datetime(timestamp) > datetime('now', '-1 hour')
                GROUP BY user_id
                HAVING COUNT(*) > ?
            ''', conn, params=[self.alert_thresholds['velocity_threshold']])
            
            for _, row in velocity_check.iterrows():
                user_id = row['user_id']
                if user_id:
                    self._create_alert(user_id, 'high', 
                        f'High velocity detected: {row["tx_count"]} transactions in 1 hour')
            conn.close()
        except Exception as e:
            print(f"Velocity check error: {e}")
    
    def _check_amount_anomalies(self):
        """Check for unusual transaction amounts grouped by user"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            high_amounts = pd.read_sql_query('''
                SELECT user_id, transaction_id, amount, fraud_score
                FROM fraud_results 
                WHERE amount > ? AND datetime(timestamp) > datetime('now', '-10 minutes')
                ORDER BY amount DESC
            ''', conn, params=[self.alert_thresholds['amount_threshold']])
            
            for _, row in high_amounts.iterrows():
                user_id = row['user_id']
                if not user_id:
                    continue
                if row['fraud_score'] > self.alert_thresholds['high_risk_score']:
                    self._create_alert(user_id, 'critical', 
                        f'High-risk large transaction: ${row["amount"]:.2f} (Risk: {row["fraud_score"]:.2f})')
                else:
                    self._create_alert(user_id, 'info', 
                        f'Large transaction detected: ${row["amount"]:.2f}')
            conn.close()
        except Exception as e:
            print(f"Amount check error: {e}")
    
    def _create_alert(self, user_id, severity, message):
        """Create and store user-associated alert"""
        alert = {
            'id': len(self.alerts) + 1,
            'user_id': user_id,
            'severity': severity,
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'acknowledged': False
        }
        self.alerts.append(alert)
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]
        print(f"[{user_id}] {severity.upper()}: {message}")
    
    def get_recent_alerts(self, limit=10, user_id=None, user_role=None):
        """Get recent alerts filtered by user context"""
        filtered = self.alerts
        if user_role != 'admin' and user_id is not None:
            filtered = [a for a in self.alerts if a.get('user_id') == user_id]
        return sorted(filtered, key=lambda x: x['timestamp'], reverse=True)[:limit]
    
    def acknowledge_alert(self, alert_id, user_id=None, user_role=None):
        """Acknowledge an alert with ownership validation"""
        for alert in self.alerts:
            if alert['id'] == alert_id:
                if user_role == 'admin' or user_id is None or alert.get('user_id') == user_id:
                    alert['acknowledged'] = True
                    return True
        return False
    
    def get_monitoring_stats(self, user_id=None, user_role=None):
        """Get monitoring system statistics filtered by user context"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            
            stats_query = 'SELECT COUNT(*) as total_transactions, SUM(is_fraud) as total_fraud, AVG(fraud_score) as avg_risk_score, MAX(timestamp) as last_transaction FROM fraud_results'
            recent_query = "SELECT strftime('%H', timestamp) as hour, COUNT(*) as transactions, SUM(is_fraud) as fraud_count FROM fraud_results WHERE datetime(timestamp) > datetime('now', '-24 hours')"
            
            params = []
            if user_role != 'admin' and user_id is not None:
                stats_query += ' WHERE user_id = ?'
                recent_query += ' AND user_id = ?'
                params.append(user_id)
                
            recent_query += " GROUP BY strftime('%H', timestamp) ORDER BY hour"
            
            stats = pd.read_sql_query(stats_query, conn, params=params)
            recent_activity = pd.read_sql_query(recent_query, conn, params=params)
            conn.close()
            
            filtered_alerts = self.alerts
            if user_role != 'admin' and user_id is not None:
                filtered_alerts = [a for a in self.alerts if a.get('user_id') == user_id]
                
            stats_dict = stats.to_dict('records')[0] if len(stats) > 0 else {}
            for key in ['total_transactions', 'total_fraud']:
                if stats_dict.get(key) is None:
                    stats_dict[key] = 0
            if stats_dict.get('avg_risk_score') is None:
                stats_dict['avg_risk_score'] = 0.0

            return {
                'overall_stats': stats_dict,
                'recent_activity': recent_activity.to_dict('records'),
                'alert_summary': {
                    'total_alerts': len(filtered_alerts),
                    'unacknowledged': len([a for a in filtered_alerts if not a['acknowledged']]),
                    'critical_alerts': len([a for a in filtered_alerts if a['severity'] == 'critical']),
                    'monitoring_status': 'active' if self.monitoring else 'inactive'
                }
            }
        except Exception as e:
            return {'error': str(e)}
    
    def generate_risk_report(self, user_id=None, user_role=None):
        """Generate user-isolated risk report"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30)
            
            risk_query = '''
                SELECT 
                    CASE 
                        WHEN fraud_score >= 0.8 THEN 'Critical'
                        WHEN fraud_score >= 0.6 THEN 'High'
                        WHEN fraud_score >= 0.4 THEN 'Medium'
                        WHEN fraud_score >= 0.2 THEN 'Low'
                        ELSE 'Minimal'
                    END as risk_level,
                    COUNT(*) as count,
                    AVG(amount) as avg_amount
                FROM fraud_results
            '''
            time_query = '''
                SELECT 
                    strftime('%H', timestamp) as hour,
                    AVG(fraud_score) as avg_risk,
                    COUNT(*) as transaction_count
                FROM fraud_results
            '''
            top_query = '''
                SELECT transaction_id, amount, fraud_score, timestamp
                FROM fraud_results
                WHERE fraud_score > 0.7
            '''
            
            params = []
            if user_role != 'admin' and user_id is not None:
                risk_query += ' WHERE user_id = ?'
                time_query += ' WHERE user_id = ?'
                top_query += ' AND user_id = ?'
                params.append(user_id)
                
            risk_query += '''
                GROUP BY 
                    CASE 
                        WHEN fraud_score >= 0.8 THEN 'Critical'
                        WHEN fraud_score >= 0.6 THEN 'High'
                        WHEN fraud_score >= 0.4 THEN 'Medium'
                        WHEN fraud_score >= 0.2 THEN 'Low'
                        ELSE 'Minimal'
                    END
            '''
            time_query += " GROUP BY strftime('%H', timestamp) ORDER BY avg_risk DESC"
            top_query += ' ORDER BY fraud_score DESC, amount DESC LIMIT 20'
            
            risk_dist = pd.read_sql_query(risk_query, conn, params=params)
            time_patterns = pd.read_sql_query(time_query, conn, params=params)
            top_risks = pd.read_sql_query(top_query, conn, params=params)
            conn.close()
            
            report = {
                'generated_at': datetime.now().isoformat(),
                'risk_distribution': risk_dist.to_dict('records'),
                'time_patterns': time_patterns.to_dict('records'),
                'top_risks': top_risks.to_dict('records'),
                'recommendations': self._generate_recommendations(risk_dist, time_patterns)
            }
            return report
        except Exception as e:
            return {'error': str(e)}
    
    def _generate_recommendations(self, risk_dist, time_patterns):
        """Generate security recommendations based on patterns"""
        recommendations = []
        
        # Check risk distribution
        if len(risk_dist) > 0:
            critical_count = risk_dist[risk_dist['risk_level'] == 'Critical']['count'].sum()
            total_count = risk_dist['count'].sum()
            
            if critical_count / total_count > 0.05:
                recommendations.append({
                    'priority': 'high',
                    'category': 'risk_management',
                    'message': 'High number of critical risk transactions detected. Consider lowering transaction limits.'
                })
        
        # Check time patterns
        if len(time_patterns) > 0:
            night_hours = time_patterns[time_patterns['hour'].isin(['22', '23', '00', '01', '02', '03', '04', '05'])]
            if len(night_hours) > 0 and night_hours['avg_risk'].mean() > 0.5:
                recommendations.append({
                    'priority': 'medium',
                    'category': 'time_based',
                    'message': 'Higher fraud risk during night hours. Consider additional verification for night transactions.'
                })
        
        # General recommendations
        recommendations.extend([
            {
                'priority': 'medium',
                'category': 'monitoring',
                'message': 'Enable real-time SMS/email alerts for transactions above $500.'
            },
            {
                'priority': 'low',
                'category': 'user_education',
                'message': 'Educate users about secure transaction practices and fraud indicators.'
            }
        ])
        
        return recommendations

# Global monitor instance
fraud_monitor = FraudMonitor()