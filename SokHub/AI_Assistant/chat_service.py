# chat_service.py
from django.utils.crypto import get_random_string
from typing import Dict, List, Optional
import json
from datetime import datetime, timedelta
from .models import ChatSession, ChatMessage, ConversationMemory

class ChatService:
    def __init__(self):
        self.max_history_length = 20  # Keep last 20 messages in context
        self.session_timeout = timedelta(minutes=30)
    
    def create_chat_session(self, user, context: Dict = None) -> ChatSession:
        """Create a new chat session"""
        if user:
            session_id = f"{user.id}_{get_random_string(10)}"
        else:
            session_id = f"anon_{get_random_string(15)}"
            
        session = ChatSession.objects.create(
            user=user,
            session_id=session_id,
            context=context or {},
            metadata={
                'user_agent': context.get('user_agent', '') if context else '',
                'ip_address': context.get('ip_address', '') if context else '',
                'platform': context.get('platform', 'web') if context else 'web'
            }
        )
        
        # Add welcome message
        welcome_msg = self._get_welcome_message(user)
        self.add_message(
            session=session,
            role='assistant',
            content=welcome_msg,
            metadata={'type': 'welcome'}
        )
        
        return session
    
    def get_or_create_session(self, user, session_id: str = None) -> ChatSession:
        """Get existing session or create new one"""
        if session_id:
            try:
                # If user is None, we just rely on session_id being unique/secret
                kwargs = {'session_id': session_id, 'is_active': True}
                if user:
                    kwargs['user'] = user
                
                session = ChatSession.objects.get(**kwargs)
                
                # Check if session timed out
                if datetime.now() - session.updated_at > self.session_timeout:
                    session.is_active = False
                    session.save()
                    return self.create_chat_session(user)
                
                return session
            except ChatSession.DoesNotExist:
                pass
        
        return self.create_chat_session(user)
    
    def add_message(self, session: ChatSession, role: str, 
                   content: str, metadata: Dict = None) -> ChatMessage:
        """Add a message to chat session"""
        message = ChatMessage.objects.create(
            session=session,
            role=role,
            content=content,
            metadata=metadata or {}
        )
        
        # Update session timestamp
        session.save(update_fields=['updated_at'])
        
        return message
    
    def get_conversation_history(self, session: ChatSession, 
                                limit: int = None) -> List[Dict]:
        """Get conversation history for context"""
        if limit is None:
            limit = self.max_history_length
        
        messages = ChatMessage.objects.filter(
            session=session
        ).order_by('-timestamp')[:limit]
        
        # Format for AI context
        formatted_messages = []
        for msg in reversed(messages):  # Oldest first
            formatted_messages.append({
                'role': msg.role,
                'content': msg.content,
                'timestamp': msg.timestamp.isoformat(),
                'metadata': msg.metadata
            })
        
        return formatted_messages
    
    def update_conversation_context(self, session: ChatSession, 
                                   updates: Dict):
        """Update chat context (user preferences, current task, etc.)"""
        current_context = session.context
        current_context.update(updates)
        session.context = current_context
        session.save(update_fields=['context', 'updated_at'])
    
    def store_conversation_memory(self, user, key: str, value: str, 
                                 confidence: float = 1.0):
        """Store important information from conversation"""
        if not user:
            return None
            
        memory, created = ConversationMemory.objects.update_or_create(
            user=user,
            key=key,
            defaults={
                'value': value,
                'confidence': confidence,
                'updated_at': datetime.now()
            }
        )
        
        return memory
    
    def get_conversation_memories(self, user, prefix: str = None) -> List[Dict]:
        """Get stored conversation memories"""
        if not user:
            return []
            
        query = ConversationMemory.objects.filter(user=user)
        if prefix:
            query = query.filter(key__startswith=prefix)
        
        memories = []
        for memory in query.order_by('-updated_at'):
            memories.append({
                'key': memory.key,
                'value': memory.value,
                'confidence': memory.confidence,
                'updated_at': memory.updated_at
            })
        
        return memories
    
    def generate_conversation_summary(self, session: ChatSession) -> str:
        """Generate summary of conversation"""
        messages = ChatMessage.objects.filter(session=session)
        
        user_messages = messages.filter(role='user')[:5]
        
        summary_parts = []
        
        # Extract key intents from user messages
        for msg in user_messages:
            if 'intent' in msg.metadata:
                intent = msg.metadata['intent']
                summary_parts.append(f"User wanted to {intent}")
        
        # Extract key information
        if session.context:
            for key, value in session.context.items():
                if key.startswith('user_'):
                    summary_parts.append(f"User mentioned {key}: {value}")
        
        # Limit summary length
        summary = ". ".join(summary_parts[:3])
        if len(summary_parts) > 3:
            summary += f" and {len(summary_parts) - 3} more things"
        
        return summary
    
    def _get_welcome_message(self, user) -> str:
        """Get personalized welcome message"""
        if not user:
            return (
                "Hello! I'm your SokHub AI assistant. "
                "I can help you find products. "
                "How can I help you today?"
            )
            
        # Check if returning user
        previous_sessions = ChatSession.objects.filter(
            user=user
        ).exclude(id=self.id if hasattr(self, 'id') else 0)
        
        if previous_sessions.exists():
            last_session = previous_sessions.first()
            
            # Get user memories
            memories = self.get_conversation_memories(user)
            
            if memories:
                return (
                    f"Welcome back! I remember you were interested in {memories[0]['value']}. "
                    f"How can I help you today?"
                )
            else:
                return "Welcome back! How can I assist you today?"
        else:
            # First time user
            return (
                "Hello! I'm your SokHub AI assistant. "
                "I can help you find products, locate stores, or assist vendors with business insights. "
                "How can I help you today?"
            )
    
    def close_session(self, session: ChatSession):
        """Close a chat session"""
        session.is_active = False
        session.save()
        
        if session.user:
            # Generate final summary and store
            summary = self.generate_conversation_summary(session)
            self.store_conversation_memory(
                user=session.user,
                key=f"session_summary_{session.session_id}",
                value=summary,
                confidence=0.8
            )
    
    def get_active_sessions_count(self, user) -> int:
        """Get count of active sessions for user"""
        if not user:
            return 0
        return ChatSession.objects.filter(
            user=user,
            is_active=True
        ).count()

# Singleton instance
chat_service = ChatService()