import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import re
import os
import joblib

class SimpleSpamDetector:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(max_features=5000, stop_words='english')
        self.model = RandomForestClassifier(n_estimators=50, random_state=42)
        self.is_trained = False
        
    def preprocess_text(self, text):
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def train(self, data_path):
        df = pd.read_csv(data_path)
        df['text'] = df['text'].apply(self.preprocess_text)
        
        X = self.vectorizer.fit_transform(df['text'])
        y = df['spam']
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        self.model.fit(X_train, y_train)
        y_pred = self.model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        
        self.is_trained = True
        return accuracy
    
    def predict(self, text, use_model=True):
        if not self.is_trained or not use_model:
            # Advanced pattern-based detection
            spam_patterns = {
                'high_risk': ['viagra', 'cialis', 'penis', 'enlargement', 'lottery', 'winner', 'congratulations', 'million dollars', 'inheritance', 'nigerian prince'],
                'medium_risk': ['free money', 'cash prize', 'urgent', 'act now', 'limited time', 'click here', 'make money', 'work from home'],
                'low_risk': ['free', 'sale', 'discount', 'offer', 'deal']
            }
            
            text_lower = text.lower()
            high_count = sum(1 for word in spam_patterns['high_risk'] if word in text_lower)
            medium_count = sum(1 for word in spam_patterns['medium_risk'] if word in text_lower)
            low_count = sum(1 for word in spam_patterns['low_risk'] if word in text_lower)
            
            # Calculate spam score
            spam_score = (high_count * 30) + (medium_count * 15) + (low_count * 5)
            
            # Check for legitimate patterns
            legit_patterns = ['meeting', 'schedule', 'project', 'report', 'invoice', 'receipt', 'confirmation']
            legit_count = sum(1 for word in legit_patterns if word in text_lower)
            
            if legit_count > 0:
                spam_score = max(0, spam_score - (legit_count * 10))
            
            if spam_score >= 40:
                confidence = min(95, 70 + spam_score)
                return {
                    'prediction': 'Spam',
                    'spam_probability': confidence,
                    'ham_probability': 100 - confidence,
                    'confidence': confidence
                }
            elif spam_score >= 15:
                confidence = 60 + spam_score
                return {
                    'prediction': 'Spam',
                    'spam_probability': confidence,
                    'ham_probability': 100 - confidence,
                    'confidence': confidence
                }
            else:
                confidence = max(75, 90 - spam_score)
                return {
                    'prediction': 'Ham',
                    'spam_probability': 100 - confidence,
                    'ham_probability': confidence,
                    'confidence': confidence
                }
        
        try:
            processed_text = self.preprocess_text(text)
            X = self.vectorizer.transform([processed_text])
            
            prediction = self.model.predict(X)[0]
            probabilities = self.model.predict_proba(X)[0]
            
            # Ensure minimum confidence threshold
            confidence = max(probabilities)
            if confidence < 0.6:  # Low confidence, use pattern-based backup
                return self.predict(text, use_model=False)  # Use pattern-based method
            
            return {
                'prediction': 'Spam' if prediction == 1 else 'Ham',
                'spam_probability': round(probabilities[1] * 100, 2),
                'ham_probability': round(probabilities[0] * 100, 2),
                'confidence': round(confidence * 100, 2)
            }
        except Exception as e:
            print(f"Model prediction error: {e}")
            # Fallback to pattern-based detection
            return self.predict(text, use_model=False)
    
    def save_model(self, path):
        model_data = {
            'vectorizer': self.vectorizer,
            'model': self.model,
            'is_trained': self.is_trained
        }
        joblib.dump(model_data, path)
    
    def load_model(self, path):
        if os.path.exists(path):
            try:
                model_data = joblib.load(path)
                self.vectorizer = model_data['vectorizer']
                self.model = model_data['model']
                self.is_trained = model_data['is_trained']
                return True
            except:
                return False
        return False

spam_detector = SimpleSpamDetector()