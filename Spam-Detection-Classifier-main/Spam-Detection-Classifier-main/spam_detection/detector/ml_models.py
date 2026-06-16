import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.naive_bayes import MultinomialNB
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import re
import pickle
import os
from textblob import TextBlob
import joblib

class AdvancedSpamDetector:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=10000,
            ngram_range=(1, 3),
            stop_words='english',
            min_df=2,
            max_df=0.95
        )
        self.ensemble_model = None
        self.is_trained = False
        
    def extract_features(self, text):
        """Extract advanced features from email text"""
        features = {}
        
        # Basic text features
        features['length'] = len(text)
        features['word_count'] = len(text.split())
        features['char_count'] = len(text)
        features['avg_word_length'] = np.mean([len(word) for word in text.split()])
        
        # Spam indicators
        features['exclamation_count'] = text.count('!')
        features['question_count'] = text.count('?')
        features['dollar_count'] = text.count('$')
        features['percent_count'] = text.count('%')
        features['caps_ratio'] = sum(1 for c in text if c.isupper()) / len(text) if text else 0
        
        # URL and email patterns
        features['url_count'] = len(re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text))
        features['email_count'] = len(re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text))
        
        # Spam keywords
        spam_keywords = ['free', 'win', 'winner', 'cash', 'prize', 'urgent', 'limited', 'offer', 'click', 'buy', 'sale']
        features['spam_keywords'] = sum(1 for word in spam_keywords if word.lower() in text.lower())
        
        # Sentiment analysis
        blob = TextBlob(text)
        features['sentiment_polarity'] = blob.sentiment.polarity
        features['sentiment_subjectivity'] = blob.sentiment.subjectivity
        
        return features
    
    def preprocess_text(self, text):
        """Clean and preprocess text"""
        # Convert to lowercase
        text = text.lower()
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Remove special characters but keep important ones
        text = re.sub(r'[^\w\s!?$%@.]', ' ', text)
        
        return text
    
    def train(self, data_path):
        """Train the ensemble model"""
        # Load data
        df = pd.read_csv(data_path)
        
        # Preprocess text
        df['text'] = df['text'].apply(self.preprocess_text)
        
        # Extract features
        feature_data = []
        for text in df['text']:
            features = self.extract_features(text)
            feature_data.append(features)
        
        feature_df = pd.DataFrame(feature_data)
        
        # TF-IDF features
        tfidf_features = self.vectorizer.fit_transform(df['text'])
        
        # Combine features
        from scipy.sparse import hstack
        combined_features = hstack([tfidf_features, feature_df.values])
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            combined_features, df['spam'], test_size=0.2, random_state=42
        )
        
        # Create ensemble model (remove MultinomialNB due to negative values)
        rf = RandomForestClassifier(n_estimators=100, random_state=42)
        lr = LogisticRegression(random_state=42, max_iter=2000)
        svm = SVC(probability=True, random_state=42, kernel='linear')
        
        self.ensemble_model = VotingClassifier(
            estimators=[('rf', rf), ('lr', lr), ('svm', svm)],
            voting='soft'
        )
        
        # Train model
        self.ensemble_model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = self.ensemble_model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        print(f"Model accuracy: {accuracy:.4f}")
        
        self.is_trained = True
        return accuracy
    
    def predict(self, text):
        """Predict if email is spam"""
        if not self.is_trained:
            raise ValueError("Model not trained yet")
        
        # Preprocess
        processed_text = self.preprocess_text(text)
        
        # Extract features
        features = self.extract_features(processed_text)
        feature_array = np.array(list(features.values())).reshape(1, -1)
        
        # TF-IDF features
        tfidf_features = self.vectorizer.transform([processed_text])
        
        # Combine features
        from scipy.sparse import hstack
        combined_features = hstack([tfidf_features, feature_array])
        
        # Predict
        prediction = self.ensemble_model.predict(combined_features)[0]
        probabilities = self.ensemble_model.predict_proba(combined_features)[0]
        
        return {
            'prediction': 'Spam' if prediction == 1 else 'Ham',
            'spam_probability': probabilities[1] * 100,
            'ham_probability': probabilities[0] * 100,
            'confidence': max(probabilities) * 100
        }
    
    def save_model(self, path):
        """Save trained model"""
        model_data = {
            'vectorizer': self.vectorizer,
            'ensemble_model': self.ensemble_model,
            'is_trained': self.is_trained
        }
        joblib.dump(model_data, path)
    
    def load_model(self, path):
        """Load trained model"""
        if os.path.exists(path):
            model_data = joblib.load(path)
            self.vectorizer = model_data['vectorizer']
            self.ensemble_model = model_data['ensemble_model']
            self.is_trained = model_data['is_trained']
            return True
        return False

# Global model instance
spam_detector = AdvancedSpamDetector()