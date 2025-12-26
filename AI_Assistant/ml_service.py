# ml_service.py
try:
    import numpy as np
except ImportError:
    np = None

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except Exception:
    # scikit-learn not available in the environment; fall back to simple logic
    TfidfVectorizer = None
    cosine_similarity = None
    SKLEARN_AVAILABLE = False
import re
import json
from collections import Counter
import pickle
from django.core.cache import cache

class MLAssistant:
    """Machine Learning powered assistant"""
    
    def __init__(self):
        if SKLEARN_AVAILABLE and TfidfVectorizer is not None:
            try:
                self.vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)
            except Exception:
                self.vectorizer = None
        else:
            self.vectorizer = None
        self.user_intents = {}
        self.product_embeddings = {}
        
    def extract_features(self, text):
        """Extract features from text for ML analysis"""
        # Clean text
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)
        
        # Extract n-grams
        words = text.split()
        features = {
            'length': len(words),
            'has_question': '?' in text,
            'has_number': bool(re.search(r'\d', text)),
            'has_currency': bool(re.search(r'\$|€|£|RWF|USD|EUR', text, re.IGNORECASE)),
            'keywords': words[:10]  # First 10 words as keywords
        }
        
        return features
    
    def detect_intent(self, text, user_id=None, context=None):
        """Detect user intent using ML"""
        features = self.extract_features(text)
        
        # Check for greetings
        greetings = ['hi', 'hello', 'hey', 'bonjour', 'muraho', 'habari']
        if any(word in text.lower() for word in greetings):
            return 'greeting'
        
        # Check for product search
        product_words = ['product', 'buy', 'price', 'cost', 'shop', 'store', 'item', 'thing']
        if any(word in text.lower() for word in product_words):
            return 'product_search'
        
        # Check for vendor queries
        vendor_words = ['vendor', 'sell', 'business', 'report', 'sales', 'order', 'stock']
        if any(word in text.lower() for word in vendor_words):
            return 'vendor_query'
        
        # Check for currency conversion
        currency_words = ['convert', 'exchange', 'dollar', 'euro', 'pound', 'shilling']
        if any(word in text.lower() for word in currency_words):
            return 'currency_conversion'
        
        # Check for help
        help_words = ['help', 'assist', 'guide', 'how to', 'what is']
        if any(word in text.lower() for word in help_words):
            return 'help_request'
        
        return 'general_inquiry'
    
    def calculate_similarity(self, query, products):
        """Calculate similarity between query and products"""
        if not products:
            return []
        
        # Create text representations of products
        product_texts = []
        for product in products:
            text = f"{product.name} {product.description or ''} {product.category or ''}"
            product_texts.append(text.lower())
        
        # Add query to the list
        all_texts = [query.lower()] + product_texts
        
        try:
            if SKLEARN_AVAILABLE and self.vectorizer is not None:
                # Create TF-IDF matrix
                tfidf_matrix = self.vectorizer.fit_transform(all_texts)

                # Calculate similarity between query and each product
                query_vector = tfidf_matrix[0]
                product_vectors = tfidf_matrix[1:]

                similarities = cosine_similarity(query_vector, product_vectors)[0]

                # Rank products by similarity
                ranked_products = []
                for i, similarity in enumerate(similarities):
                    ranked_products.append({
                        'product': products[i],
                        'similarity': float(similarity)
                    })

                # Sort by similarity (highest first)
                ranked_products.sort(key=lambda x: x['similarity'], reverse=True)
                return ranked_products

            # Fallback when scikit-learn isn't available: use simple token overlap score
            ranked_products = []
            query_tokens = set(re.sub(r"[^\w\s]", "", query.lower()).split())
            for product in products:
                text = f"{product.name} {product.description or ''} {product.category or ''}".lower()
                tokens = set(re.sub(r"[^\w\s]", "", text).split())
                if not tokens:
                    score = 0.0
                else:
                    common = query_tokens.intersection(tokens)
                    score = len(common) / max(1, len(tokens))
                ranked_products.append({'product': product, 'similarity': float(score)})

            ranked_products.sort(key=lambda x: x['similarity'], reverse=True)
            return ranked_products

        except Exception as e:
            print(f"Similarity calculation error: {e}")
            # Fallback: return products as-is
            return [{'product': p, 'similarity': 0.0} for p in products]
    
    def analyze_sentiment(self, text):
        """Simple sentiment analysis"""
        positive_words = ['good', 'great', 'excellent', 'amazing', 'love', 'thanks', 'thank', 'helpful']
        negative_words = ['bad', 'poor', 'terrible', 'hate', 'worst', 'awful', 'problem', 'issue']
        
        text_lower = text.lower()
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        else:
            return 'neutral'
    
    def learn_from_interaction(self, user_id, query, response, feedback=None):
        """Learn from user interactions to improve responses"""
        if user_id not in self.user_intents:
            self.user_intents[user_id] = Counter()
        
        intent = self.detect_intent(query)
        self.user_intents[user_id][intent] += 1
        
        # Store in cache for persistence
        cache_key = f"ml_assistant_{user_id}"
        cache.set(cache_key, dict(self.user_intents[user_id]), timeout=86400)  # 24 hours
    
    def get_user_preferences(self, user_id):
        """Get learned preferences for a user"""
        cache_key = f"ml_assistant_{user_id}"
        preferences = cache.get(cache_key, {})
        
        if preferences:
            # Find most common intent
            if preferences:
                most_common = max(preferences.items(), key=lambda x: x[1])
                return {'preferred_intent': most_common[0], 'interaction_count': most_common[1]}
        
        return {'preferred_intent': None, 'interaction_count': 0}

# Singleton instance
ml_assistant = MLAssistant()