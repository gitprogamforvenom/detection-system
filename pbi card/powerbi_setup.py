import sqlite3
import pandas as pd
from datetime import datetime
import os

def create_powerbi_views():
    """Create optimized views for Power BI connection"""
    conn = sqlite3.connect('fraudguard.db', timeout=30)
    
    conn.execute('DROP VIEW IF EXISTS v_fraud_analytics')
    conn.execute('DROP VIEW IF EXISTS v_daily_summary')
    conn.execute('DROP VIEW IF EXISTS v_hourly_trends')
    
    # Create fraud analytics view
    conn.execute('''
        CREATE VIEW v_fraud_analytics AS
        SELECT 
            user_id,
            transaction_id,
            amount,
            fraud_score,
            is_fraud,
            CASE WHEN is_fraud = 1 THEN 'Fraud' ELSE 'Normal' END as status,
            CASE 
                WHEN fraud_score > 0.8 THEN 'Critical'
                WHEN fraud_score > 0.6 THEN 'High'
                WHEN fraud_score > 0.4 THEN 'Medium'
                ELSE 'Low'
            END as risk_level,
            DATE(timestamp) as date,
            strftime('%H', timestamp) as hour,
            timestamp
        FROM fraud_results
    ''')
    
    # Create daily summary view
    conn.execute('''
        CREATE VIEW v_daily_summary AS
        SELECT 
            user_id,
            DATE(timestamp) as date,
            COUNT(*) as total_transactions,
            SUM(is_fraud) as fraud_count,
            ROUND(AVG(fraud_score), 3) as avg_risk_score,
            ROUND((SUM(is_fraud) * 100.0 / COUNT(*)), 2) as fraud_rate
        FROM fraud_results
        GROUP BY user_id, DATE(timestamp)
    ''')
    
    # Create hourly trends view
    conn.execute('''
        CREATE VIEW v_hourly_trends AS
        SELECT 
            user_id,
            strftime('%H', timestamp) as hour,
            COUNT(*) as transactions,
            SUM(is_fraud) as fraud_count,
            ROUND((SUM(is_fraud) * 100.0 / COUNT(*)), 2) as fraud_rate
        FROM fraud_results
        GROUP BY user_id, strftime('%H', timestamp)
    ''')
    
    conn.commit()
    conn.close()

def export_for_powerbi(user_id=None, user_role=None):
    """Export structured data for Power BI with auto-refresh capability, isolated by user"""
    conn = sqlite3.connect('fraudguard.db', timeout=30)
    
    # Export main analytics data
    q_analytics = 'SELECT * FROM v_fraud_analytics'
    p_analytics = []
    if user_role != 'admin' and user_id is not None:
        q_analytics += ' WHERE user_id = ?'
        p_analytics.append(user_id)
    q_analytics += ' ORDER BY timestamp DESC'
    analytics_df = pd.read_sql_query(q_analytics, conn, params=p_analytics)
    f_analytics = f'pbi_fraud_analytics_{user_id}.csv'
    analytics_df.to_csv(f_analytics, index=False)
    
    # Export daily summary
    q_daily = 'SELECT * FROM v_daily_summary'
    p_daily = []
    if user_role != 'admin' and user_id is not None:
        q_daily += ' WHERE user_id = ?'
        p_daily.append(user_id)
    q_daily += ' ORDER BY date DESC'
    daily_df = pd.read_sql_query(q_daily, conn, params=p_daily)
    f_daily = f'pbi_daily_summary_{user_id}.csv'
    daily_df.to_csv(f_daily, index=False)
    
    # Export hourly trends
    q_hourly = 'SELECT * FROM v_hourly_trends'
    p_hourly = []
    if user_role != 'admin' and user_id is not None:
        q_hourly += ' WHERE user_id = ?'
        p_hourly.append(user_id)
    q_hourly += ' ORDER BY hour'
    hourly_df = pd.read_sql_query(q_hourly, conn, params=p_hourly)
    f_hourly = f'pbi_hourly_trends_{user_id}.csv'
    hourly_df.to_csv(f_hourly, index=False)
    
    # Export blockchain alerts
    q_bc = '''
        SELECT 
            id,
            user_id,
            transaction_hash,
            JSON_EXTRACT(data, '$.transaction_id') as transaction_id,
            JSON_EXTRACT(data, '$.fraud_score') as fraud_score,
            JSON_EXTRACT(data, '$.alert') as alert_type,
            DATE(timestamp) as alert_date,
            TIME(timestamp) as alert_time,
            timestamp
        FROM blockchain_log
    '''
    p_bc = []
    if user_role != 'admin' and user_id is not None:
        q_bc += ' WHERE user_id = ?'
        p_bc.append(user_id)
    q_bc += ' ORDER BY timestamp DESC'
    blockchain_df = pd.read_sql_query(q_bc, conn, params=p_bc)
    f_bc = f'pbi_blockchain_alerts_{user_id}.csv'
    blockchain_df.to_csv(f_bc, index=False)
    
    conn.close()
    
    return {
        'analytics': f_analytics,
        'daily_summary': f_daily, 
        'hourly_trends': f_hourly,
        'blockchain_alerts': f_bc
    }

if __name__ == "__main__":
    create_powerbi_views()
    files = export_for_powerbi(user_id=1, user_role='admin')
    print("Power BI files created:")
    for key, file in files.items():
        print(f"  {key}: {file}")