"""Minimal AIService used by service.py

Provides lightweight implementations of:
- AIService.detect_language(text)
- AIService.check_inappropriate_content(text)
- AIService.get_greeting_response(user, language)

This is intentionally small and dependency-free.
"""
import re
from typing import Tuple, Optional


class AIService:
    # Simple heuristics for language detection
    _FRENCH_KEYWORDS = {
        'bonjour', 'merci', "s'il", 'svp', 'au revoir', 'salut', 'monsieur', 'madame', 'comment'
    }
    _RW_KEYWORDS = {
        'muraho', 'amakuru', 'mwiriwe', 'mwaramutse', 'urakoze', 'ndabona', 'bite', 'neza'
    }
    _SW_KEYWORDS = {
        'jambo', 'habari', 'asante', 'kwaheri', 'shikamoo', 'mambo', 'poa', 'karibu'
    }

    # Basic inappropriate words list — extend as needed
    _BAD_WORDS = {
        'damn', 'shit', 'stupid', 'idiot', 'fuck', 'bastard', 'bitch'
    }

    @staticmethod
    def detect_language(text: str) -> str:
        """Return a language code: 'en', 'fr', 'rw', or 'sw'."""
        if not text:
            return 'en'
        lower = text.lower()
        
        # Check for simple French keywords
        for kw in AIService._FRENCH_KEYWORDS:
            if kw in lower:
                return 'fr'
        
        # Check for Kinyarwanda keywords
        for kw in AIService._RW_KEYWORDS:
            if kw in lower:
                return 'rw'
                
        # Check for Swahili keywords
        for kw in AIService._SW_KEYWORDS:
            if kw in lower:
                return 'sw'
                
        return 'en'

    @staticmethod
    def check_inappropriate_content(text: str) -> Tuple[bool, Optional[str]]:
        """Return (is_inappropriate, matched_keyword) if a bad word is found."""
        if not text:
            return False, None
        lower = text.lower()
        # word-boundary search
        for bad in AIService._BAD_WORDS:
            if re.search(rf"\b{re.escape(bad)}\b", lower):
                return True, bad
        return False, None

    @staticmethod
    def get_greeting_response(user, language: str = 'en') -> str:
        """Return a short greeting string appropriate to language and user."""
        name = None
        if user is not None:
            # Try first name, then username
            name = getattr(user, 'first_name', None)
            if not name:
                name = getattr(user, 'username', None)
            
            # If still no name (unlikely for authenticated user), fall back
            if not name:
                name = "Client"

        if language == 'fr':
            if name:
                return f"Bonjour {name}! Comment puis-je vous aider aujourd'hui?"
            return "Bonjour! Comment puis-je vous aider aujourd'hui?"
        
        if language == 'rw':
            if name:
                return f"Muraho {name}! Nakora iki ngo nkunganire uyu munsi?"
            return "Muraho! Nakora iki ngo nkunganire uyu munsi?"
            
        if language == 'sw':
            if name:
                return f"Habari {name}! Nikusaidie aje leo?"
            return "Habari! Nikusaidie aje leo?"

        # default: English
        if name:
            return f"Hello {name}! How can I help you today?"
        return "Hello! How can I help you today?"


__all__ = ['AIService']
