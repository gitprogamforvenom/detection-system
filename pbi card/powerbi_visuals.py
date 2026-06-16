import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def create_powerbi_visual_data(user_id=None, user_role=None):
    """Create data optimized for Power BI attractive visualizations, isolated by user"""
    
    conn = sqlite3.connect('fraudguard.db', timeout=30)
    
    # 1. PIE/DONUT CHART DATA - Risk Distribution
    pie_query = '''
        SELECT 
            CASE 
                WHEN fraud_score >= 0.8 THEN 'Critical Risk'
                WHEN fraud_score >= 0.6 THEN 'High Risk'
                WHEN fraud_score >= 0.4 THEN 'Medium Risk'
                WHEN fraud_score >= 0.2 THEN 'Low Risk'
                ELSE 'Minimal Risk'
            END as risk_category,
            COUNT(*) as transaction_count,
            ROUND(SUM(amount), 2) as total_amount,
            ROUND(AVG(fraud_score), 3) as avg_risk_score
        FROM fraud_results
    '''
    params = []
    if user_role != 'admin' and user_id is not None:
        pie_query += ' WHERE user_id = ?'
        params.append(user_id)
    pie_query += '''
        GROUP BY 
            CASE 
                WHEN fraud_score >= 0.8 THEN 'Critical Risk'
                WHEN fraud_score >= 0.6 THEN 'High Risk'
                WHEN fraud_score >= 0.4 THEN 'Medium Risk'
                WHEN fraud_score >= 0.2 THEN 'Low Risk'
                ELSE 'Minimal Risk'
            END
        ORDER BY avg_risk_score DESC
    '''
    pie_data = pd.read_sql_query(pie_query, conn, params=params)
    
    # 2. FUNNEL CHART DATA - Fraud Detection Pipeline
    total_q = 'SELECT COUNT(*) as cnt FROM fraud_results'
    flagged_q = 'SELECT COUNT(*) as cnt FROM fraud_results WHERE fraud_score > 0.3'
    high_q = 'SELECT COUNT(*) as cnt FROM fraud_results WHERE fraud_score > 0.6'
    critical_q = 'SELECT COUNT(*) as cnt FROM fraud_results WHERE fraud_score > 0.8'
    is_fraud_q = 'SELECT COUNT(*) as cnt FROM fraud_results WHERE is_fraud = 1'
    
    funnel_params = []
    if user_role != 'admin' and user_id is not None:
        total_q += ' WHERE user_id = ?'
        flagged_q += ' WHERE user_id = ? AND fraud_score > 0.3'
        high_q += ' WHERE user_id = ? AND fraud_score > 0.6'
        critical_q += ' WHERE user_id = ? AND fraud_score > 0.8'
        is_fraud_q += ' WHERE user_id = ? AND is_fraud = 1'
        funnel_params.append(user_id)
        
    funnel_data = pd.DataFrame({
        'stage': ['Total Transactions', 'Flagged for Review', 'High Risk Detected', 'Critical Alerts', 'Confirmed Fraud'],
        'count': [
            pd.read_sql_query(total_q, conn, params=funnel_params).iloc[0]['cnt'],
            pd.read_sql_query(flagged_q, conn, params=funnel_params).iloc[0]['cnt'],
            pd.read_sql_query(high_q, conn, params=funnel_params).iloc[0]['cnt'],
            pd.read_sql_query(critical_q, conn, params=funnel_params).iloc[0]['cnt'],
            pd.read_sql_query(is_fraud_q, conn, params=funnel_params).iloc[0]['cnt']
        ],
        'percentage': [100, 0, 0, 0, 0]
    })
    
    # Calculate percentages for funnel
    total = funnel_data.iloc[0]['count']
    if total > 0:
        funnel_data['percentage'] = (funnel_data['count'] / total * 100).round(1)
    
    # 3. STACKED BAR DATA - Hourly Fraud Patterns
    stacked_query = '''
        SELECT 
            strftime('%H', timestamp) as hour,
            SUM(CASE WHEN is_fraud = 1 THEN 1 ELSE 0 END) as fraud_count,
            SUM(CASE WHEN is_fraud = 0 THEN 1 ELSE 0 END) as normal_count,
            COUNT(*) as total_transactions,
            ROUND(AVG(amount), 2) as avg_amount
        FROM fraud_results
    '''
    stacked_params = []
    if user_role != 'admin' and user_id is not None:
        stacked_query += ' WHERE user_id = ?'
        stacked_params.append(user_id)
    stacked_query += '''
        GROUP BY strftime('%H', timestamp)
        ORDER BY hour
    '''
    stacked_data = pd.read_sql_query(stacked_query, conn, params=stacked_params)
    
    # 4. TREEMAP DATA - Transaction Categories by Risk
    treemap_query = '''
        SELECT 
            CASE 
                WHEN amount < 100 THEN 'Small Transactions'
                WHEN amount < 1000 THEN 'Medium Transactions'
                WHEN amount < 5000 THEN 'Large Transactions'
                ELSE 'Very Large Transactions'
            END as amount_category,
            CASE 
                WHEN fraud_score >= 0.6 THEN 'High Risk'
                WHEN fraud_score >= 0.3 THEN 'Medium Risk'
                ELSE 'Low Risk'
            END as risk_level,
            COUNT(*) as transaction_count,
            ROUND(SUM(amount), 2) as total_value,
            ROUND(AVG(fraud_score), 3) as avg_risk_score
        FROM fraud_results
    '''
    treemap_params = []
    if user_role != 'admin' and user_id is not None:
        treemap_query += ' WHERE user_id = ?'
        treemap_params.append(user_id)
    treemap_query += '''
        GROUP BY 
            CASE 
                WHEN amount < 100 THEN 'Small Transactions'
                WHEN amount < 1000 THEN 'Medium Transactions'
                WHEN amount < 5000 THEN 'Large Transactions'
                ELSE 'Very Large Transactions'
            END,
            CASE 
                WHEN fraud_score >= 0.6 THEN 'High Risk'
                WHEN fraud_score >= 0.3 THEN 'Medium Risk'
                ELSE 'Low Risk'
            END
        ORDER BY total_value DESC
    '''
    treemap_data = pd.read_sql_query(treemap_query, conn, params=treemap_params)
    
    # 5. WATERFALL DATA - Daily Fraud Trend Changes
    waterfall_query = '''
        SELECT 
            DATE(timestamp) as date,
            SUM(is_fraud) as daily_fraud_count
        FROM fraud_results
    '''
    waterfall_params = []
    if user_role != 'admin' and user_id is not None:
        waterfall_query += ' WHERE user_id = ?'
        waterfall_params.append(user_id)
    waterfall_query += '''
        GROUP BY DATE(timestamp)
        ORDER BY date
    '''
    waterfall_data = pd.read_sql_query(waterfall_query, conn, params=waterfall_params)
    
    # Calculate waterfall changes
    if len(waterfall_data) > 1:
        waterfall_data['change'] = waterfall_data['daily_fraud_count'].diff().fillna(0)
        waterfall_data['change_type'] = waterfall_data['change'].apply(
            lambda x: 'Increase' if x > 0 else 'Decrease' if x < 0 else 'No Change'
        )
    
    # 6. 100% STACKED DATA - Risk Distribution by Time Period
    stacked_100_query = '''
        SELECT 
            CASE 
                WHEN strftime('%H', timestamp) BETWEEN '06' AND '11' THEN 'Morning'
                WHEN strftime('%H', timestamp) BETWEEN '12' AND '17' THEN 'Afternoon'
                WHEN strftime('%H', timestamp) BETWEEN '18' AND '23' THEN 'Evening'
                ELSE 'Night'
            END as time_period,
            SUM(CASE WHEN fraud_score >= 0.8 THEN 1 ELSE 0 END) as critical_risk,
            SUM(CASE WHEN fraud_score >= 0.6 AND fraud_score < 0.8 THEN 1 ELSE 0 END) as high_risk,
            SUM(CASE WHEN fraud_score >= 0.4 AND fraud_score < 0.6 THEN 1 ELSE 0 END) as medium_risk,
            SUM(CASE WHEN fraud_score < 0.4 THEN 1 ELSE 0 END) as low_risk,
            COUNT(*) as total
        FROM fraud_results
    '''
    stacked_100_params = []
    if user_role != 'admin' and user_id is not None:
        stacked_100_query += ' WHERE user_id = ?'
        stacked_100_params.append(user_id)
    stacked_100_query += '''
        GROUP BY 
            CASE 
                WHEN strftime('%H', timestamp) BETWEEN '06' AND '11' THEN 'Morning'
                WHEN strftime('%H', timestamp) BETWEEN '12' AND '17' THEN 'Afternoon'
                WHEN strftime('%H', timestamp) BETWEEN '18' AND '23' THEN 'Evening'
                ELSE 'Night'
            END
        ORDER BY 
            CASE 
                WHEN time_period = 'Morning' THEN 1
                WHEN time_period = 'Afternoon' THEN 2
                WHEN time_period = 'Evening' THEN 3
                ELSE 4
            END
    '''
    stacked_100_data = pd.read_sql_query(stacked_100_query, conn, params=stacked_100_params)
    
    conn.close()
    
    # Save all datasets with user-specific names
    pie_file = f'pbi_pie_risk_distribution_{user_id}.csv'
    funnel_file = f'pbi_funnel_detection_pipeline_{user_id}.csv'
    stacked_file = f'pbi_stacked_hourly_patterns_{user_id}.csv'
    treemap_file = f'pbi_treemap_categories_{user_id}.csv'
    waterfall_file = f'pbi_waterfall_daily_trends_{user_id}.csv'
    stacked_100_file = f'pbi_stacked100_time_periods_{user_id}.csv'
    
    pie_data.to_csv(pie_file, index=False)
    funnel_data.to_csv(funnel_file, index=False)
    stacked_data.to_csv(stacked_file, index=False)
    treemap_data.to_csv(treemap_file, index=False)
    waterfall_data.to_csv(waterfall_file, index=False)
    stacked_100_data.to_csv(stacked_100_file, index=False)
    
    return {
        'pie_donut': pie_file,
        'funnel': funnel_file,
        'stacked_bar': stacked_file,
        'treemap': treemap_file,
        'waterfall': waterfall_file,
        'stacked_100': stacked_100_file
    }

if __name__ == "__main__":
    files = create_powerbi_visual_data(user_id=1, user_role='admin')
    print("Power BI Visual Data Files Created:")
    for visual_type, filename in files.items():
        print(f"  {visual_type}: {filename}")