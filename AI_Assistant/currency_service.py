# currency_service.py
import requests
from decimal import Decimal
import json
from datetime import datetime, timedelta
from django.core.cache import cache

class CurrencyConverter:
    """Handle currency conversions with multi-language support"""
    
    # Exchange rates for common currencies (RWF as base)
    BASE_CURRENCY = 'RWF'
    
    # Common exchange rates (approx)
    EXCHANGE_RATES = {
        'USD': 0.00078,    # 1 RWF = 0.00078 USD
        'EUR': 0.00072,    # 1 RWF = 0.00072 EUR
        'GBP': 0.00062,    # 1 RWF = 0.00062 GBP
        'KES': 0.092,      # 1 RWF = 0.092 KES
        'UGX': 2.85,       # 1 RWF = 2.85 UGX
        'TZS': 1.82,       # 1 RWF = 1.82 TZS
        'FRW': 1.0,        # Same for Rwanda Franc
        'RWF': 1.0,        # Base currency
    }
    
    # Currency names in multiple languages
    CURRENCY_NAMES = {
        'en': {
            'USD': 'US Dollar',
            'EUR': 'Euro',
            'GBP': 'British Pound',
            'KES': 'Kenyan Shilling',
            'UGX': 'Ugandan Shilling',
            'TZS': 'Tanzanian Shilling',
            'RWF': 'Rwandan Franc'
        },
        'fr': {
            'USD': 'Dollar américain',
            'EUR': 'Euro',
            'GBP': 'Livre sterling',
            'KES': 'Shilling kényan',
            'UGX': 'Shilling ougandais',
            'TZS': 'Shilling tanzanien',
            'RWF': 'Franc rwandais'
        },
        'rw': {
            'USD': 'Idolari ry\'Abanyamerika',
            'EUR': 'Yuro',
            'GBP': 'Livre y\'Ubwongereza',
            'KES': 'Shillingi ya Kenya',
            'UGX': 'Shillingi ya Uganda',
            'TZS': 'Shillingi ya Tanzania',
            'RWF': 'Amafaranga y\'u Rwanda'
        }
    }
    
    @staticmethod
    def detect_currency_request(text, language='en'):
        """Detect if user is asking for currency conversion"""
        text_lower = text.lower()
        
        currency_keywords = {
            'en': ['convert', 'exchange', 'dollar', 'euro', 'pound', 'shilling', 'currency', 'how much in'],
            'fr': ['convertir', 'changer', 'dollar', 'euro', 'livre', 'shilling', 'devise'],
            'rw': ['hindura', 'amafaranga', 'idolari', 'yuro', 'livre', 'shillingi']
        }
        
        keywords = currency_keywords.get(language, currency_keywords['en'])
        return any(keyword in text_lower for keyword in keywords)
    
    @staticmethod
    def extract_currency_amount(text):
        """Extract amount and target currency from text"""
        import re
        
        # Find numbers with commas and decimals
        amount_pattern = r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)'
        matches = re.findall(amount_pattern, text)
        
        if not matches:
            return None, None
        
        # Get the amount (first number found)
        amount_str = matches[0].replace(',', '')
        try:
            amount = float(amount_str)
        except:
            amount = None
        
        # Detect target currency
        text_lower = text.lower()
        currency_map = {
            'usd': 'USD', 'dollar': 'USD', '$': 'USD',
            'eur': 'EUR', 'euro': 'EUR', '€': 'EUR',
            'gbp': 'GBP', 'pound': 'GBP', '£': 'GBP',
            'kes': 'KES', 'kenyan': 'KES',
            'ugx': 'UGX', 'ugandan': 'UGX',
            'tzs': 'TZS', 'tanzanian': 'TZS',
            'rwf': 'RWF', 'franc': 'RWF', 'frw': 'RWF'
        }
        
        target_currency = 'USD'  # Default
        for word, curr in currency_map.items():
            if word in text_lower:
                target_currency = curr
                break
        
        return amount, target_currency
    
    @staticmethod
    def convert(amount_rwf, target_currency):
        """Convert RWF to target currency"""
        if not amount_rwf or target_currency not in CurrencyConverter.EXCHANGE_RATES:
            return None
        
        rate = CurrencyConverter.EXCHANGE_RATES[target_currency]
        return amount_rwf * rate
    
    @staticmethod
    def format_conversion(amount_rwf, target_currency, language='en'):
        """Format conversion result with proper language"""
        converted = CurrencyConverter.convert(amount_rwf, target_currency)
        
        if not converted:
            return None
        
        currency_name = CurrencyConverter.CURRENCY_NAMES.get(
            language, CurrencyConverter.CURRENCY_NAMES['en']
        ).get(target_currency, target_currency)
        
        # Format numbers based on language
        if language == 'fr':
            amount_str = f"{amount_rwf:,.0f} RWF"
            converted_str = f"{converted:,.2f} {target_currency}"
        elif language == 'rw':
            amount_str = f"Amafaranga {amount_rwf:,.0f}"
            converted_str = f"{converted:,.2f} {target_currency}"
        else:  # English
            amount_str = f"RWF {amount_rwf:,.0f}"
            converted_str = f"{target_currency} {converted:,.2f}"
        
        return f"{amount_str} = {converted_str} ({currency_name})"

# Singleton instance
currency_converter = CurrencyConverter()