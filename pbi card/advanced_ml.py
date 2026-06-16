"""
Advanced Machine Learning Models for Fraud Detection
Supports multiple algorithms and ensemble methods
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.svm import OneClassSVM
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
import warnings
warnings.filterwarnings('ignore')

class FraudDetectionEnsemble:
    """Advanced ensemble fraud detection system"""
    
    def __init__(self):
        self.models = {
            'isolation_forest': IsolationForest(contamination=0.1, random_state=42, n_estimators=200),
            'one_class_svm': OneClassSVM(gamma='scale', nu=0.1),
            'dbscan': DBSCAN(eps=0.5, min_samples=5)
        }
        self.scaler = StandardScaler()
        self.label_encoders = {}
        self.feature_importance = {}
        
    def engineer_features(self, df):
        """Advanced feature engineering"""
        df = df.copy()
        
        # Time-based features
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
            df['hour'] = df['timestamp'].dt.hour
            df['day_of_week'] = df['timestamp'].dt.dayofweek
            df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
            df['is_night'] = ((df['hour'] >= 22) | (df['hour'] <= 6)).astype(int)
            df['is_business_hours'] = ((df['hour'] >= 9) & (df['hour'] <= 17)).astype(int)
        
        # Amount-based features
        amount_col = self._find_amount_column(df)
        if amount_col:
            df['amount_log'] = np.log1p(df[amount_col].fillna(0))
            df['amount_zscore'] = (df[amount_col] - df[amount_col].mean()) / df[amount_col].std()
            df['is_round_amount'] = (df[amount_col] % 100 == 0).astype(int)
            df['amount_percentile'] = df[amount_col].rank(pct=True)
        
        # Categorical encoding
        categorical_cols = df.select_dtypes(include=['object']).columns
        for col in categorical_cols:
            if col not in ['timestamp', 'id']:
                if col not in self.label_encoders:
                    self.label_encoders[col] = LabelEncoder()
                    df[f'{col}_encoded'] = self.label_encoders[col].fit_transform(df[col].fillna('unknown'))
                else:
                    # Handle unseen categories
                    unique_vals = set(df[col].fillna('unknown'))
                    known_vals = set(self.label_encoders[col].classes_)
                    new_vals = unique_vals - known_vals
                    
                    if new_vals:
                        # Add new categories to encoder
                        all_vals = list(known_vals) + list(new_vals)
                        self.label_encoders[col].classes_ = np.array(all_vals)
                    
                    df[f'{col}_encoded'] = self.label_encoders[col].transform(df[col].fillna('unknown'))
        
        # Velocity features (if user_id available)
        if 'user_id' in df.columns and 'timestamp' in df.columns:
            df = self._add_velocity_features(df)
        
        return df
    
    def _find_amount_column(self, df):
        """Find the amount column in the dataset"""
        possible_names = ['amount', 'Amount', 'transaction_amount', 'value', 'Value']
        for name in possible_names:
            if name in df.columns:
                return name
        return None
    
    def _add_velocity_features(self, df):
        """Add transaction velocity features"""
        df_sorted = df.sort_values(['user_id', 'timestamp'])
        
        # Time between transactions for same user
        df_sorted['time_since_last'] = df_sorted.groupby('user_id')['timestamp'].diff().dt.total_seconds().fillna(3600)
        
        # Transaction count in last hour/day
        df_sorted['tx_count_1h'] = df_sorted.groupby('user_id').rolling('1h', on='timestamp')['timestamp'].count().values
        df_sorted['tx_count_1d'] = df_sorted.groupby('user_id').rolling('1d', on='timestamp')['timestamp'].count().values
        
        return df_sorted.sort_index()
    
    def detect_fraud(self, df):
        """Main fraud detection method"""
        # Feature engineering
        df_processed = self.engineer_features(df)
        
        # Select features for ML
        feature_cols = df_processed.select_dtypes(include=[np.number]).columns
        feature_cols = [col for col in feature_cols if col not in ['id', 'actual_fraud', 'Class']]
        
        if len(feature_cols) == 0:
            return df, []
        
        X = df_processed[feature_cols].fillna(0)
        
        # Handle infinite values
        X = X.replace([np.inf, -np.inf], 0)
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Apply ensemble models
        predictions = {}
        scores = {}
        
        # Skip slow O(N^2) models on larger datasets to prevent gateway read timeouts
        use_models = list(self.models.keys())
        if len(X) > 3000:
            use_models = ['isolation_forest']
            
        for name in use_models:
            model = self.models[name]
            try:
                if name == 'dbscan':
                    pred = model.fit_predict(X_scaled)
                    predictions[name] = (pred == -1).astype(int)
                    # For DBSCAN, use distance to cluster centers as score
                    scores[name] = self._calculate_dbscan_scores(X_scaled, model)
                else:
                    pred = model.fit_predict(X_scaled)
                    predictions[name] = (pred == -1).astype(int)
                    if hasattr(model, 'score_samples'):
                        scores[name] = -model.score_samples(X_scaled)
                    else:
                        scores[name] = np.random.random(len(X))
            except Exception as e:
                print(f"Error with {name}: {e}")
                predictions[name] = np.zeros(len(X))
                scores[name] = np.zeros(len(X))
        
        # Ensemble voting
        ensemble_pred = np.mean([predictions[name] for name in predictions.keys()], axis=0)
        ensemble_scores = np.mean([scores[name] for name in scores.keys()], axis=0)
        
        # Normalize scores
        if ensemble_scores.max() > ensemble_scores.min():
            ensemble_scores = (ensemble_scores - ensemble_scores.min()) / (ensemble_scores.max() - ensemble_scores.min())
        
        # Add results to dataframe
        df_processed['is_fraud'] = (ensemble_pred >= 0.5).astype(int)
        df_processed['fraud_score'] = ensemble_scores
        
        # Risk categorization
        df_processed['risk_category'] = pd.cut(
            df_processed['fraud_score'], 
            bins=[0, 0.2, 0.4, 0.6, 0.8, 1.0], 
            labels=['Minimal', 'Low', 'Medium', 'High', 'Critical'],
            include_lowest=True
        )
        
        # Additional behavioral flags
        df_processed['velocity_flag'] = self._detect_velocity_anomalies(df_processed)
        df_processed['pattern_flag'] = self._detect_pattern_anomalies(df_processed)
        
        # Adjust final scores based on behavioral flags
        behavioral_boost = 0.1 * (df_processed['velocity_flag'] + df_processed['pattern_flag'])
        df_processed['fraud_score'] = np.clip(df_processed['fraud_score'] + behavioral_boost, 0, 1)
        df_processed['is_fraud'] = (df_processed['fraud_score'] > 0.6).astype(int)
        
        # Get high-risk transactions
        high_risk = df_processed[df_processed['is_fraud'] == 1].to_dict('records')
        
        return df_processed, high_risk
    
    def _calculate_dbscan_scores(self, X, model):
        """Calculate anomaly scores for DBSCAN"""
        labels = model.labels_
        scores = np.zeros(len(X))
        
        # Outliers (label = -1) get high scores
        outlier_mask = labels == -1
        scores[outlier_mask] = 1.0
        
        # For clustered points, calculate distance to cluster center
        for cluster_id in set(labels):
            if cluster_id != -1:
                cluster_mask = labels == cluster_id
                cluster_points = X[cluster_mask]
                cluster_center = cluster_points.mean(axis=0)
                
                # Calculate distances to center
                distances = np.linalg.norm(cluster_points - cluster_center, axis=1)
                max_dist = distances.max() if len(distances) > 0 else 1
                
                # Normalize distances to 0-0.5 range (lower than outliers)
                if max_dist > 0:
                    scores[cluster_mask] = (distances / max_dist) * 0.5
        
        return scores
    
    def _detect_velocity_anomalies(self, df):
        """Detect transaction velocity anomalies"""
        flags = np.zeros(len(df))
        
        if 'time_since_last' in df.columns:
            # Very fast consecutive transactions
            fast_threshold = df['time_since_last'].quantile(0.05)
            flags += (df['time_since_last'] < fast_threshold).astype(int) * 0.5
        
        if 'tx_count_1h' in df.columns:
            # Too many transactions in short time
            high_velocity_threshold = df['tx_count_1h'].quantile(0.95)
            flags += (df['tx_count_1h'] > high_velocity_threshold).astype(int) * 0.3
        
        return np.clip(flags, 0, 1)
    
    def _detect_pattern_anomalies(self, df):
        """Detect unusual transaction patterns"""
        flags = np.zeros(len(df))
        
        # Round amount patterns
        if 'is_round_amount' in df.columns:
            flags += df['is_round_amount'] * 0.2
        
        # Night time transactions
        if 'is_night' in df.columns:
            flags += df['is_night'] * 0.1
        
        # Weekend transactions
        if 'is_weekend' in df.columns:
            flags += df['is_weekend'] * 0.05
        
        # High-risk merchant categories
        if 'merchant_category_encoded' in df.columns:
            # Assume higher encoded values are riskier (this is dataset dependent)
            max_encoded = df['merchant_category_encoded'].max()
            if max_encoded > 0:
                risk_score = df['merchant_category_encoded'] / max_encoded
                flags += risk_score * 0.15
        
        return np.clip(flags, 0, 1)
    
    def evaluate_model(self, df):
        """Evaluate model performance if ground truth is available"""
        if 'actual_fraud' in df.columns or 'Class' in df.columns:
            ground_truth_col = 'actual_fraud' if 'actual_fraud' in df.columns else 'Class'
            y_true = df[ground_truth_col]
            y_pred = df['is_fraud']
            y_scores = df['fraud_score']
            
            # Classification report
            report = classification_report(y_true, y_pred, output_dict=True)
            
            # Confusion matrix
            cm = confusion_matrix(y_true, y_pred)
            
            # AUC score
            try:
                auc = roc_auc_score(y_true, y_scores)
            except:
                auc = 0.5
            
            return {
                'classification_report': report,
                'confusion_matrix': cm.tolist(),
                'auc_score': auc,
                'accuracy': report['accuracy'],
                'precision': report['1']['precision'] if '1' in report else 0,
                'recall': report['1']['recall'] if '1' in report else 0,
                'f1_score': report['1']['f1-score'] if '1' in report else 0
            }
        
        return None

# Convenience function for backward compatibility
def detect_fraud_ensemble(df):
    """Wrapper function for the advanced fraud detection"""
    detector = FraudDetectionEnsemble()
    return detector.detect_fraud(df)