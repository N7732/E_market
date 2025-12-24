# voice_service.py
import io
import base64
import tempfile
import os
from django.core.files.base import ContentFile
from django.conf import settings
from typing import Optional, Tuple, Dict
import numpy as np
from .models import VoiceProfile

# Optional imports with graceful fallback
try:
    import speech_recognition as sr
except ImportError:
    sr = None
    print("SpeechRecognition not installed. Voice features limited.")

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None
    print("pyttsx3 not installed. TTS features limited.")

try:
    from gtts import gTTS
except ImportError:
    gTTS = None

try:
    import whisper
except ImportError:
    whisper = None

try:
    import librosa
except ImportError:
    librosa = None

class VoiceService:
    def __init__(self):
        # Initialize speech recognizer
        self.recognizer = sr.Recognizer() if sr else None
        
        # Initialize text-to-speech engines
        self.tts_engine = None
        if pyttsx3:
            try:
                self.tts_engine = pyttsx3.init()
                self._configure_tts()
            except Exception as e:
                print(f"Failed to init pyttsx3: {e}")
        
        # Initialize Whisper for offline speech recognition
        self.whisper_model = None
        if whisper:
            self._load_whisper_model()
        
        # Voice profiles storage
        self.voice_profiles = {}
    
    def _configure_tts(self):
        """Configure text-to-speech engine"""
        if not self.tts_engine: return
        
        try:
            voices = self.tts_engine.getProperty('voices')
            # Set voice properties
            self.tts_engine.setProperty('rate', 150)  # Speed
            self.tts_engine.setProperty('volume', 0.9)  # Volume
            
            # Try to find a good voice
            for voice in voices:
                if 'english' in voice.name.lower():
                    self.tts_engine.setProperty('voice', voice.id)
                    break
        except Exception as e:
            print(f"Error configuring TTS: {e}")
    
    def _load_whisper_model(self):
        """Load Whisper model for offline speech recognition"""
        try:
            # Use smallest model for faster loading
            self.whisper_model = whisper.load_model("tiny")
            print("Whisper model loaded for offline speech recognition")
        except Exception as e:
            print(f"Could not load Whisper model: {e}")
    
    def speech_to_text(self, audio_data, use_online: bool = True) -> Dict:
        """
        Convert speech to text using multiple methods
        Returns: {'text': 'recognized text', 'confidence': 0.95, 'method': 'google'}
        """
        if not self.recognizer:
            return {'text': '', 'confidence': 0, 'method': 'none', 'error': 'SpeechRecognition not installed'}

        results = []
        
        # Method 1: Google Web Speech API (online, most accurate)
        if use_online:
            try:
                text = self.recognizer.recognize_google(audio_data)
                results.append({
                    'text': text,
                    'confidence': 0.95,
                    'method': 'google'
                })
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"Google Speech Recognition error: {e}")
            except Exception:
                pass
        
        # Method 2: Whisper (offline, good accuracy)
        if self.whisper_model and hasattr(audio_data, 'get_wav_data'):
            try:
                # Convert audio data to numpy array
                audio_np = np.frombuffer(
                    audio_data.get_wav_data(), 
                    dtype=np.int16
                ).astype(np.float32) / 32768.0
                
                # Transcribe
                result = self.whisper_model.transcribe(audio_np)
                results.append({
                    'text': result['text'],
                    'confidence': 0.85,
                    'method': 'whisper'
                })
            except Exception as e:
                print(f"Whisper error: {e}")
        
        # Method 3: Sphinx (offline, less accurate)
        try:
            if hasattr(self.recognizer, 'recognize_sphinx'):
                text = self.recognizer.recognize_sphinx(audio_data)
                results.append({
                    'text': text,
                    'confidence': 0.6,
                    'method': 'sphinx'
                })
        except (sr.UnknownValueError, AttributeError, Exception):
            pass
        
        # Choose best result
        if results:
            # Prefer higher confidence
            best_result = max(results, key=lambda x: x['confidence'])
            return best_result
        
        return {'text': '', 'confidence': 0, 'method': 'none'}
    
    def text_to_speech(self, text: str, 
                      voice_type: str = 'default',
                      speed: float = 1.0) -> Tuple[bytes, str]:
        """
        Convert text to speech
        Returns: (audio_bytes, content_type)
        """
        # Method 1: Google TTS (online, better quality)
        if gTTS:
            try:
                tts = gTTS(text=text, lang='en', slow=False)
                
                # Save to bytes
                audio_bytes = io.BytesIO()
                tts.write_to_fp(audio_bytes)
                audio_bytes.seek(0)
                
                return audio_bytes.read(), 'audio/mpeg'
            except Exception as e:
                print(f"Google TTS error: {e}")
        
        # Method 2: pyttsx3 (offline)
        if self.tts_engine:
            try:
                # Save to temporary file
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                    temp_path = f.name
                
                self.tts_engine.save_to_file(text, temp_path)
                self.tts_engine.runAndWait()
                
                with open(temp_path, 'rb') as f:
                    audio_bytes = f.read()
                
                os.unlink(temp_path)
                
                return audio_bytes, 'audio/mpeg'
            except Exception as e:
                print(f"pyttsx3 error: {e}")
        
        # Fallback: Return empty
        return b'', 'audio/mpeg'
    
    def process_voice_command(self, audio_file, user_id: int = None) -> Dict:
        """Process voice command end-to-end"""
        if not self.recognizer:
            return {
                'success': False,
                'error': 'Voice service not available (libraries missing)',
                'text': '',
                'response': "Voice services are not installed on the server."
            }

        try:
            # Read audio file
            audio_data = sr.AudioFile(audio_file)
            
            with audio_data as source:
                # Adjust for ambient noise
                self.recognizer.adjust_for_ambient_noise(source)
                audio = self.recognizer.record(source)
            
            # Convert to text
            stt_result = self.speech_to_text(audio)
            
            if not stt_result['text']:
                return {
                    'success': False,
                    'error': 'Could not recognize speech',
                    'text': '',
                    'response': "I couldn't understand that. Please try again."
                }
            
            # Process text with AI
            from .service import EnhancedAIService
            
            ai_response = EnhancedAIService.process_chat_message(
                message=stt_result['text'],
                user_id=user_id
            )
            
            # Convert response to speech
            tts_audio, content_type = self.text_to_speech(ai_response['response'])
            
            return {
                'success': True,
                'text': stt_result['text'],
                'response_text': ai_response['response'],
                'response_audio': base64.b64encode(tts_audio).decode('utf-8') if tts_audio else None,
                'audio_content_type': content_type,
                'intent': ai_response.get('intent', 'general'),
                'confidence': stt_result.get('confidence', 0)
            }
        except Exception as e:
            return {
                'success': False, 
                'error': str(e),
                'response': 'Error processing voice.'
            }
    
    def create_voice_profile(self, user_id: int, audio_samples: list):
        """Create voice profile for user (for speaker recognition)"""
        if not librosa or not np:
            print("Librosa/Numpy missing, skipping voice profile")
            return

        # Extract voice features
        features = []
        
        for audio_sample in audio_samples:
            try:
                # Convert to numpy array
                audio_np = np.frombuffer(
                    audio_sample.get_wav_data(), 
                    dtype=np.int16
                ).astype(np.float32) / 32768.0
                
                # Extract MFCC features
                mfcc = librosa.feature.mfcc(
                    y=audio_np, 
                    sr=16000, 
                    n_mfcc=13
                )
                
                # Calculate mean MFCC
                mean_mfcc = np.mean(mfcc, axis=1)
                features.append(mean_mfcc)
            except Exception as e:
                print(f"Error extracting features: {e}")
        
        # Store average features
        if features:
            avg_features = np.mean(features, axis=0)
            self.voice_profiles[user_id] = avg_features.tolist()
            
            # Save to database
            VoiceProfile.objects.update_or_create(
                user_id=user_id,
                defaults={
                    'features': avg_features.tolist(),
                    'sample_count': len(audio_samples)
                }
            )
    
    def identify_speaker(self, audio_data) -> Optional[int]:
        """Identify speaker from voice"""
        if not self.voice_profiles or not librosa:
            return None
        
        try:
            # Extract features from input
            audio_np = np.frombuffer(
                audio_data.get_wav_data(), 
                dtype=np.int16
            ).astype(np.float32) / 32768.0
            
            mfcc = librosa.feature.mfcc(
                y=audio_np, 
                sr=16000, 
                n_mfcc=13
            )
            input_features = np.mean(mfcc, axis=1)
            
            # Find closest match
            min_distance = float('inf')
            matched_user = None
            
            for user_id, profile_features in self.voice_profiles.items():
                distance = np.linalg.norm(
                    input_features - np.array(profile_features)
                )
                
                if distance < min_distance and distance < 10:  # Threshold
                    min_distance = distance
                    matched_user = user_id
            
            return matched_user
        except Exception:
            return None
    
    def transcribe_audio_file(self, file_path: str) -> str:
        """Transcribe audio file using Whisper"""
        if not self.whisper_model:
            if whisper:
                self._load_whisper_model()
            else:
                return ""
        
        try:
            result = self.whisper_model.transcribe(file_path)
            return result['text']
        except Exception:
            return ""

# Singleton instance
voice_service = VoiceService()