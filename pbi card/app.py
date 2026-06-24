from flask import Flask, request, render_template, jsonify, send_file
import pandas as pd
import numpy as np
from advanced_ml import FraudDetectionEnsemble
from real_time_monitor import fraud_monitor
import sqlite3
import os
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = None
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

class FraudPrefixMiddleware(object):
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if path.startswith('/fraud/'):
            environ['PATH_INFO'] = path[6:]  # Strip '/fraud'
        elif path == '/fraud':
            environ['PATH_INFO'] = '/'
        return self.wsgi_app(environ, start_response)

app.wsgi_app = FraudPrefixMiddleware(app.wsgi_app)

# Automatically initialize the database and start the monitoring thread on import
try:
    init_db()
except Exception as e:
    print(f"Warning: Could not initialize database on import: {e}")

try:
    from real_time_monitor import fraud_monitor
    fraud_monitor.start_monitoring()
except Exception as e:
    print(f"Warning: Could not start monitoring thread on import: {e}")


def init_db():
    conn = sqlite3.connect('fraudguard.db', timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    cursor = conn.cursor()

    # Check and migrate fraud_results schema
    cursor.execute("PRAGMA table_info(fraud_results)")
    columns = [row[1] for row in cursor.fetchall()]
    if len(columns) > 0 and 'user_id' not in columns:
        cursor.execute('ALTER TABLE fraud_results RENAME TO fraud_results_old')
        cursor.execute('''
            CREATE TABLE fraud_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                transaction_id TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount >= 0),
                fraud_score REAL NOT NULL,
                is_fraud INTEGER NOT NULL CHECK(is_fraud IN (0,1)),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, transaction_id)
            )
        ''')
        cursor.execute('''
            INSERT INTO fraud_results (id, user_id, transaction_id, amount, fraud_score, is_fraud, timestamp)
            SELECT id, 1, transaction_id, amount, fraud_score, is_fraud, timestamp FROM fraud_results_old
        ''')
        cursor.execute('DROP TABLE fraud_results_old')

    # Check and migrate blockchain_log schema
    cursor.execute("PRAGMA table_info(blockchain_log)")
    columns_bc = [row[1] for row in cursor.fetchall()]
    if len(columns_bc) > 0 and 'user_id' not in columns_bc:
        cursor.execute('ALTER TABLE blockchain_log RENAME TO blockchain_log_old')
        cursor.execute('''
            CREATE TABLE blockchain_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                transaction_hash TEXT NOT NULL UNIQUE,
                previous_hash TEXT NOT NULL,
                data TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            INSERT INTO blockchain_log (id, user_id, transaction_hash, previous_hash, data, timestamp)
            SELECT id, 1, transaction_hash, previous_hash, data, timestamp FROM blockchain_log_old
        ''')
        cursor.execute('DROP TABLE blockchain_log_old')

    # Ensure tables exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fraud_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            transaction_id TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            fraud_score REAL NOT NULL,
            is_fraud INTEGER NOT NULL CHECK(is_fraud IN (0,1)),
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, transaction_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blockchain_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            transaction_hash TEXT NOT NULL UNIQUE,
            previous_hash TEXT NOT NULL,
            data TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fraud_score ON fraud_results(fraud_score DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_is_fraud ON fraud_results(is_fraud)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON fraud_results(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_blockchain_hash ON blockchain_log(transaction_hash)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON fraud_results(user_id)')

    conn.commit()
    conn.close()


def get_user_context():
    user_id = request.headers.get("X-User-Id")
    user_role = request.headers.get("X-User-Role")
    
    # Fallback for direct access without Gateway proxying
    if not user_id:
        user_id = "1"
    if not user_role:
        user_role = "admin"
        
    return int(user_id) if user_id else None, user_role


@app.route('/')
@app.route('/fraud')
@app.route('/fraud/')
def index():
    return render_template('cardinx.html')


@app.route('/upload', methods=['POST'])
@app.route('/fraud/upload', methods=['POST'])
def upload_file():
    try:
        user_id, user_role = get_user_context()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        elif file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file)
        else:
            return jsonify({'error': 'Unsupported file format'}), 400

        # Handle tab-separated files
        if len(df.columns) == 1:
            file.seek(0)
            df = pd.read_csv(file, sep='\t')

        # Normalize column names
        df.columns = [c.strip() for c in df.columns]

        # Handle credit card fraud dataset (V1-V28 + Amount + Class)
        if 'Amount' not in df.columns and 'amount' not in df.columns:
            # Use first numeric column as amount proxy
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if numeric_cols:
                df['Amount'] = df[numeric_cols[0]].abs()

        # Add timestamp if missing
        if 'timestamp' not in df.columns:
            df['timestamp'] = pd.Timestamp.now()

        detector = FraudDetectionEnsemble()
        df_processed, high_risk_transactions = detector.detect_fraud(df)

        with sqlite3.connect('fraudguard.db', timeout=30) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            fraud_data = []
            blockchain_data = []

            for _, row in df_processed.iterrows():
                fraud_data.append((
                    user_id,
                    str(row.get('id', row.name)),
                    max(0, float(row.get('amount', row.get('Amount', 0)))),
                    float(row['fraud_score']),
                    int(row['is_fraud'])
                ))
                if row['is_fraud'] == 1:
                    blockchain_data.append({
                        'transaction_id': str(row.get('id', row.name)),
                        'fraud_score': float(row['fraud_score']),
                        'alert': 'HIGH_RISK_TRANSACTION'
                    })

            conn.executemany('''
                INSERT OR REPLACE INTO fraud_results (user_id, transaction_id, amount, fraud_score, is_fraud)
                VALUES (?, ?, ?, ?, ?)
            ''', fraud_data)

            for data in blockchain_data:
                cursor = conn.cursor()
                cursor.execute('SELECT transaction_hash FROM blockchain_log WHERE user_id = ? ORDER BY id DESC LIMIT 1', (user_id,))
                result = cursor.fetchone()
                previous_hash = result[0] if result else "genesis"
                data_str = json.dumps(data, sort_keys=True)
                transaction_hash = str(hash(data_str + previous_hash))
                conn.execute('''
                    INSERT OR IGNORE INTO blockchain_log (user_id, transaction_hash, previous_hash, data)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, transaction_hash, previous_hash, data_str))

            conn.commit()

        # Direct MySQL insert for central dashboard alerts
        try:
            import mysql.connector
            mysql_conn = mysql.connector.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                port=int(os.environ.get("DB_PORT", 33066)),
                user=os.environ.get("DB_USER", "root"),
                password=os.environ.get("DB_PASSWORD", "Vem12345@"),
                database=os.environ.get("DB_DATABASE", "sentinelledger")
            )
            mysql_cursor = mysql_conn.cursor()
            for f_data in fraud_data:
                uid, tx_id, amt, score, is_f = f_data
                if is_f == 1:
                    import hashlib
                    tx_hash = hashlib.sha256(f"{uid}-{tx_id}-{score}".encode()).hexdigest()
                    mysql_cursor.execute('''
                        INSERT INTO alerts (alert_type, decision, score, blockchain_hash, user_id)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', ('transaction', 'fraud', score, tx_hash, uid))
            mysql_conn.commit()
            mysql_cursor.close()
            mysql_conn.close()
        except Exception as mysql_err:
            print(f"MySQL Alert insertion error: {mysql_err}")

        # Save processed file in user-specific folder
        user_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(user_id))
        os.makedirs(user_upload_dir, exist_ok=True)
        output_path = os.path.join(user_upload_dir, f'processed_{file.filename}')
        df_processed.to_csv(output_path, index=False)

        total_transactions = len(df_processed)
        fraud_count = df_processed['is_fraud'].sum()
        fraud_percentage = (fraud_count / total_transactions) * 100
        avg_fraud_score = df_processed['fraud_score'].mean()
        risk_distribution = df_processed['risk_category'].value_counts().to_dict()
        velocity_flags = df_processed['velocity_flag'].sum() if 'velocity_flag' in df_processed.columns else 0
        pattern_flags = df_processed['pattern_flag'].sum() if 'pattern_flag' in df_processed.columns else 0

        return jsonify({
            'success': True,
            'summary': {
                'total_transactions': total_transactions,
                'fraud_count': int(fraud_count),
                'fraud_percentage': round(fraud_percentage, 2),
                'high_risk_transactions': len(high_risk_transactions),
                'avg_fraud_score': round(avg_fraud_score, 3),
                'risk_distribution': risk_distribution,
                'behavioral_flags': {
                    'velocity_anomalies': int(velocity_flags),
                    'pattern_anomalies': int(pattern_flags)
                }
            },
            'high_risk_sample': high_risk_transactions[:5],
            'model_info': {
                'algorithms_used': ['Isolation Forest', 'One-Class SVM', 'DBSCAN'],
                'features_analyzed': len(df_processed.select_dtypes(include=[np.number]).columns),
                'confidence_level': 'High' if avg_fraud_score > 0.7 else 'Medium' if avg_fraud_score > 0.4 else 'Low'
            },
            'download_url': f'download/{os.path.basename(output_path)}'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download/<filename>')
@app.route('/fraud/download/<filename>')
def download_file(filename):
    user_id, user_role = get_user_context()
    if not user_id:
        return "Unauthorized", 401
    
    if user_role == 'admin':
        # Admin can view all directories
        for uid_dir in os.listdir(app.config['UPLOAD_FOLDER']):
            path = os.path.join(app.config['UPLOAD_FOLDER'], uid_dir, filename)
            if os.path.exists(path):
                return send_file(path, as_attachment=True)
        return "File not found", 404
    else:
        path = os.path.join(app.config['UPLOAD_FOLDER'], str(user_id), filename)
        if os.path.exists(path):
            return send_file(path, as_attachment=True)
        return "Forbidden or File not found", 403


@app.route('/download-powerbi/<filename>')
@app.route('/fraud/download-powerbi/<filename>')
def download_powerbi_file(filename):
    user_id, user_role = get_user_context()
    if not user_id:
        return "Unauthorized", 401
    
    if user_role != 'admin':
        # Enforce name check
        if f'_{user_id}.csv' not in filename and f'_{user_id}.json' not in filename:
            return "Forbidden", 403
            
    safe_path = os.path.basename(filename)
    if os.path.exists(safe_path):
        return send_file(safe_path, as_attachment=True)
    return "File not found", 404


@app.route('/export-powerbi')
@app.route('/fraud/export-powerbi')
def export_powerbi():
    user_id, user_role = get_user_context()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        from powerbi_setup import create_powerbi_views, export_for_powerbi
        from powerbi_visuals import create_powerbi_visual_data
        create_powerbi_views()
        basic_files = export_for_powerbi(user_id, user_role)
        visual_files = create_powerbi_visual_data(user_id, user_role)
        all_files = {**basic_files, **visual_files}

        with sqlite3.connect('fraudguard.db', timeout=30) as conn:
            query = 'SELECT * FROM v_daily_summary'
            params = []
            if user_role != 'admin':
                query += ' WHERE user_id = ?'
                params.append(user_id)
            query += ' ORDER BY date DESC LIMIT 1'
            stats_df = pd.read_sql_query(query, conn, params=params)
            
            summary_stats = {
                'total_transactions': int(stats_df.iloc[0]['total_transactions']),
                'fraud_count': int(stats_df.iloc[0]['fraud_count']),
                'fraud_rate': float(stats_df.iloc[0]['fraud_rate']),
                'avg_fraud_score': float(stats_df.iloc[0]['avg_risk_score']),
                'export_timestamp': datetime.now().isoformat()
            } if len(stats_df) > 0 else {'message': 'No data available'}

        return jsonify({
            'success': True,
            'files': all_files,
            'stats': summary_stats,
            'dashboard_url': '/dashboard'
        })

    except Exception as e:
        return jsonify({'error': f'Export failed: {str(e)}'}), 500


@app.route('/dashboard')
@app.route('/fraud/dashboard')
def dashboard():
    return render_template('dashboard.html')


@app.route('/api/fraud-analytics')
@app.route('/fraud/api/fraud-analytics')
def get_fraud_analytics():
    user_id, user_role = get_user_context()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
        
    conn = sqlite3.connect('fraudguard.db', timeout=30)

    pie_query = '''
        SELECT
            CASE
                WHEN fraud_score >= 0.8 THEN 'Critical'
                WHEN fraud_score >= 0.6 THEN 'High'
                WHEN fraud_score >= 0.4 THEN 'Medium'
                WHEN fraud_score >= 0.2 THEN 'Low'
                ELSE 'Minimal'
            END as risk,
            COUNT(*) as count
        FROM fraud_results
    '''
    params = []
    if user_role != 'admin':
        pie_query += ' WHERE user_id = ?'
        params.append(user_id)
    pie_query += '''
        GROUP BY
            CASE
                WHEN fraud_score >= 0.8 THEN 'Critical'
                WHEN fraud_score >= 0.6 THEN 'High'
                WHEN fraud_score >= 0.4 THEN 'Medium'
                WHEN fraud_score >= 0.2 THEN 'Low'
                ELSE 'Minimal'
            END
    '''
    pie_data = pd.read_sql_query(pie_query, conn, params=params)

    bar_query = '''
        SELECT
            strftime('%H', timestamp) as hour,
            SUM(CASE WHEN is_fraud = 1 THEN 1 ELSE 0 END) as fraud,
            SUM(CASE WHEN is_fraud = 0 THEN 1 ELSE 0 END) as normal
        FROM fraud_results
    '''
    params_bar = []
    if user_role != 'admin':
        bar_query += ' WHERE user_id = ?'
        params_bar.append(user_id)
    bar_query += '''
        GROUP BY strftime('%H', timestamp)
        ORDER BY hour
    '''
    bar_data = pd.read_sql_query(bar_query, conn, params=params_bar)

    stats_query = '''
        SELECT
            COUNT(*) as total,
            SUM(is_fraud) as fraud_count,
            SUM(CASE WHEN is_fraud = 0 THEN 1 ELSE 0 END) as legitimate_count,
            ROUND(AVG(fraud_score), 3) as avg_score,
            ROUND(SUM(amount), 2) as total_amount,
            SUM(CASE WHEN fraud_score >= 0.8 THEN 1 ELSE 0 END) as critical_alerts,
            SUM(CASE WHEN fraud_score >= 0.6 THEN 1 ELSE 0 END) as total_alerts
        FROM fraud_results
    '''
    params_stats = []
    if user_role != 'admin':
        stats_query += ' WHERE user_id = ?'
        params_stats.append(user_id)
    stats = pd.read_sql_query(stats_query, conn, params=params_stats)

    alerts_query = '''
        SELECT transaction_id, amount, fraud_score, timestamp
        FROM fraud_results
        WHERE is_fraud = 1
    '''
    params_alerts = []
    if user_role != 'admin':
        alerts_query += ' AND user_id = ?'
        params_alerts.append(user_id)
    alerts_query += '''
        ORDER BY timestamp DESC
        LIMIT 5
    '''
    recent_alerts = pd.read_sql_query(alerts_query, conn, params=params_alerts)

    conn.close()
    
    stats_dict = stats.to_dict('records')[0] if len(stats) > 0 else {}
    for key in ['total', 'fraud_count', 'legitimate_count', 'critical_alerts', 'total_alerts']:
        if stats_dict.get(key) is None:
            stats_dict[key] = 0
    if stats_dict.get('avg_score') is None:
        stats_dict['avg_score'] = 0.0
    if stats_dict.get('total_amount') is None:
        stats_dict['total_amount'] = 0.0

    return jsonify({
        'pie': pie_data.to_dict('records'),
        'bar': bar_data.to_dict('records'),
        'stats': stats_dict,
        'recent_alerts': recent_alerts.to_dict('records')
    })


@app.route('/datasets')
@app.route('/fraud/datasets')
def view_datasets():
    return render_template('datasets.html')


@app.route('/api/datasets')
@app.route('/fraud/api/datasets')
def get_datasets():
    user_id, user_role = get_user_context()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        upload_files = []
        user_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(user_id))
        
        if user_role == 'admin':
            if os.path.exists(app.config['UPLOAD_FOLDER']):
                for uid_dir in os.listdir(app.config['UPLOAD_FOLDER']):
                    dirpath = os.path.join(app.config['UPLOAD_FOLDER'], uid_dir)
                    if os.path.isdir(dirpath):
                        for filename in os.listdir(dirpath):
                            if filename.startswith('processed_'):
                                filepath = os.path.join(dirpath, filename)
                                file_stats = os.stat(filepath)
                                upload_files.append({
                                    'filename': filename,
                                    'original_name': filename.replace('processed_', '') + f" (User {uid_dir})",
                                    'size': round(file_stats.st_size / 1024, 2),
                                    'upload_date': datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M')
                                })
        else:
            if os.path.exists(user_upload_dir):
                for filename in os.listdir(user_upload_dir):
                    if filename.startswith('processed_'):
                        filepath = os.path.join(user_upload_dir, filename)
                        file_stats = os.stat(filepath)
                        upload_files.append({
                            'filename': filename,
                            'original_name': filename.replace('processed_', ''),
                            'size': round(file_stats.st_size / 1024, 2),
                            'upload_date': datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M')
                        })

        conn = sqlite3.connect('fraudguard.db', timeout=30)
        summary_query = '''
            SELECT
                COUNT(*) as total_transactions,
                SUM(is_fraud) as fraud_count,
                ROUND((SUM(is_fraud) * 100.0 / COUNT(*)), 2) as fraud_rate,
                ROUND(AVG(fraud_score), 3) as avg_risk_score,
                ROUND(SUM(amount), 2) as total_amount,
                MIN(timestamp) as first_transaction,
                MAX(timestamp) as last_transaction
            FROM fraud_results
        '''
        params = []
        if user_role != 'admin':
            summary_query += ' WHERE user_id = ?'
            params.append(user_id)
            
        summary = pd.read_sql_query(summary_query, conn, params=params)
        conn.close()

        summary_dict = summary.to_dict('records')[0] if len(summary) > 0 else {}
        for key in ['total_transactions', 'fraud_count', 'fraud_rate', 'avg_risk_score', 'total_amount']:
            if summary_dict.get(key) is None:
                summary_dict[key] = 0

        return jsonify({
            'files': upload_files,
            'summary': summary_dict
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete-dataset/<filename>', methods=['DELETE'])
def delete_dataset(filename):
    user_id, user_role = get_user_context()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        if user_role == 'admin':
            for uid_dir in os.listdir(app.config['UPLOAD_FOLDER']):
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], uid_dir, filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
                    return jsonify({'success': True})
            return jsonify({'error': 'File not found'}), 404
        else:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], str(user_id), filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                return jsonify({'success': True})
            return jsonify({'error': 'Forbidden or File not found'}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/clear-all-data', methods=['DELETE'])
def clear_all_data():
    user_id, user_role = get_user_context()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        conn = sqlite3.connect('fraudguard.db', timeout=30)
        if user_role == 'admin':
            conn.execute('DELETE FROM fraud_results')
            conn.execute('DELETE FROM blockchain_log')
        else:
            conn.execute('DELETE FROM fraud_results WHERE user_id = ?', (user_id,))
            conn.execute('DELETE FROM blockchain_log WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

        if user_role == 'admin':
            if os.path.exists(app.config['UPLOAD_FOLDER']):
                import shutil
                for item in os.listdir(app.config['UPLOAD_FOLDER']):
                    itempath = os.path.join(app.config['UPLOAD_FOLDER'], item)
                    if os.path.isdir(itempath):
                        shutil.rmtree(itempath)
                    else:
                        os.remove(itempath)
        else:
            user_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(user_id))
            if os.path.exists(user_upload_dir):
                import shutil
                shutil.rmtree(user_upload_dir)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/real-time-alerts')
def get_real_time_alerts():
    user_id, user_role = get_user_context()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        conn = sqlite3.connect('fraudguard.db', timeout=30)
        query = '''
            SELECT transaction_id, amount, fraud_score, timestamp
            FROM fraud_results
            WHERE is_fraud = 1 AND datetime(timestamp) > datetime('now', '-1 hour')
        '''
        params = []
        if user_role != 'admin':
            query += ' AND user_id = ?'
            params.append(user_id)
        query += ' ORDER BY fraud_score DESC, timestamp DESC LIMIT 10'
        
        alerts = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return jsonify({
            'alerts': alerts.to_dict('records'),
            'count': len(alerts),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitoring/start', methods=['POST'])
def start_monitoring():
    try:
        fraud_monitor.start_monitoring()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitoring/stop', methods=['POST'])
def stop_monitoring():
    try:
        fraud_monitor.stop_monitoring()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitoring/alerts')
def get_monitoring_alerts():
    user_id, user_role = get_user_context()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        alerts = fraud_monitor.get_recent_alerts(limit=20, user_id=user_id, user_role=user_role)
        return jsonify({'alerts': alerts, 'count': len(alerts), 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitoring/stats')
def get_monitoring_stats():
    user_id, user_role = get_user_context()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        return jsonify(fraud_monitor.get_monitoring_stats(user_id=user_id, user_role=user_role))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/risk-report')
def get_risk_report():
    user_id, user_role = get_user_context()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        return jsonify(fraud_monitor.generate_risk_report(user_id=user_id, user_role=user_role))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/acknowledge-alert/<int:alert_id>', methods=['POST'])
def acknowledge_alert(alert_id):
    user_id, user_role = get_user_context()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        success = fraud_monitor.acknowledge_alert(alert_id, user_id=user_id, user_role=user_role)
        if success:
            return jsonify({'success': True})
        return jsonify({'error': 'Alert not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    init_db()
    fraud_monitor.start_monitoring()
    app.run(debug=True, port=5000)
