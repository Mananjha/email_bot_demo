import os
import time
import base64
import re
import pickle
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

# Try to import transformers, with fallback
try:
    from transformers import pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("Transformers not available, using simple reply mode")

load_dotenv()

# Gmail API setup
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service():
    creds = None
    token_file = 'token.pickle'
    
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                raise FileNotFoundError(
                    "credentials.json not found. Please download it from Google Cloud Console "
                    "and place it in the project directory."
                )
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
    
    return build('gmail', 'v1', credentials=creds)

class EmailBot:
    def __init__(self):
        self.service = get_gmail_service()
        self.poll_interval = int(os.getenv('POLL_INTERVAL_SECONDS', 60))
        self.model_name = os.getenv('MODEL_NAME', 'microsoft/DialoGPT-small')
        
        # Initialize model
        self.chat_pipeline = None
        
        if TRANSFORMERS_AVAILABLE:
            print(f"Loading model: {self.model_name}")
            try:
                # Use pipeline for simpler loading
                self.chat_pipeline = pipeline(
                    "text-generation",
                    model=self.model_name,
                    device_map="auto"
                )
                print("Model loaded successfully!")
            except Exception as e:
                print(f"Error loading model: {e}")
                print("Falling back to simple reply mode")
                self.chat_pipeline = None
        else:
            print("Using simple reply mode (transformers not available)")
    
    def get_unreplied_emails(self):
        """Get all unread emails"""
        try:
            results = self.service.users().messages().list(
                userId='me', q='is:unread').execute()
            messages = results.get('messages', [])
            return messages
        except HttpError as error:
            print(f'Error getting emails: {error}')
            return []
    
    def get_email_content(self, message_id):
        """Extract content from email"""
        try:
            message = self.service.users().messages().get(
                userId='me', id=message_id, format='full').execute()
            
            payload = message['payload']
            headers = payload.get('headers', [])
            
            subject = ''
            from_email = ''
            body = ''
            
           
            for header in headers:
                if header['name'] == 'Subject':
                    subject = header['value']
                if header['name'] == 'From':
                    from_email = header['value']
            
            
            if 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain' and 'body' in part and 'data' in part['body']:
                        body_data = part['body']['data']
                        body = base64.urlsafe_b64decode(body_data + '===').decode('utf-8', errors='ignore')
                        break
            elif 'body' in payload and 'data' in payload['body']:
                body_data = payload['body']['data']
                body = base64.urlsafe_b64decode(body_data + '===').decode('utf-8', errors='ignore')
            
            
            body = re.sub(r'\s+', ' ', body).strip()[:500]  # Limit length
            
            return {
                'subject': subject,
                'from': from_email,
                'body': body,
                'thread_id': message['threadId'],
                'message_id': message_id
            }
            
        except Exception as error:
            print(f'Error parsing email: {error}')
            return None
    
    def generate_simple_reply(self, email_content):
        """Generate a simple contextual reply"""
        text = (email_content['subject'] + ' ' + email_content['body']).lower()
        
        if any(word in text for word in ['hello', 'hi', 'hey', 'greeting']):
            return "Hello! Thank you for your message. I'll get back to you soon."
        elif any(word in text for word in ['question', 'ask', 'help', 'support']):
            return "Thanks for your question. I'll look into this and respond properly."
        elif any(word in text for word in ['urgent', 'asap', 'important', 'emergency']):
            return "I've received your urgent message and will prioritize it."
        elif any(word in text for word in ['thank', 'thanks', 'appreciate', 'grateful']):
            return "You're welcome! I'm glad I could help."
        elif any(word in text for word in ['meeting', 'schedule', 'appointment', 'calendar']):
            return "I'll check my schedule and get back to you about the meeting."
        else:
            return "Thank you for your email. I've received it and will respond soon."
    
    def generate_ai_reply(self, email_content):
        """Generate reply using AI model"""
        try:
            prompt = f"Email subject: {email_content['subject']}\n"
            prompt += f"Email content: {email_content['body']}\n"
            prompt += "Please write a short, helpful reply to this email:"
            
            response = self.chat_pipeline(
                prompt,
                max_new_tokens=100,
                num_return_sequences=1,
                temperature=0.7,
                do_sample=True,
                pad_token_id=self.chat_pipeline.tokenizer.eos_token_id
            )
            
            reply = response[0]['generated_text'].replace(prompt, '').strip()
            reply = re.split(r'[.!?]', reply)[0]  # Take first sentence
            
            return reply[:200]  # Limit length
            
        except Exception as e:
            print(f"Error generating AI reply: {e}")
            return self.generate_simple_reply(email_content)
    
    def generate_reply(self, email_content):
        """Choose reply generation method"""
        if self.chat_pipeline:
            return self.generate_ai_reply(email_content)
        else:
            return self.generate_simple_reply(email_content)
    
    def send_reply(self, thread_id, reply_text, to_email):
        """Send reply email"""
        try:
            message = MIMEText(reply_text)
            message['To'] = to_email
            message['Subject'] = 'Re: Auto-reply'
            
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            body = {'raw': raw_message, 'threadId': thread_id}
            
            sent_message = self.service.users().messages().send(
                userId='me', body=body).execute()
            
            print(f"✓ Reply sent to {to_email}")
            return True
            
        except Exception as error:
            print(f'✗ Error sending reply: {error}')
            return False
    
    def mark_as_replied(self, message_id):
        """Mark email as read"""
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            print("✓ Email marked as read")
        except Exception as error:
            print(f'✗ Error marking email: {error}')
    
    def run(self):
        """Main bot loop"""
        print("🚀 Email Bot Started!")
        print("📧 Monitoring inbox for new emails...")
        print("🛑 Press Ctrl+C to stop")
        
        try:
            while True:
                messages = self.get_unreplied_emails()
                
                if messages:
                    print(f"📨 Found {len(messages)} new emails")
                
                for message in messages:
                    email_content = self.get_email_content(message['id'])
                    if email_content:
                        print(f"📧 From: {email_content['from']}")
                        print(f"📝 Subject: {email_content['subject']}")
                        
                        reply = self.generate_reply(email_content)
                        print(f"💬 Reply: {reply}")
                        
                        if self.send_reply(email_content['thread_id'], reply, email_content['from']):
                            self.mark_as_replied(message['id'])
                        
                        print("─" * 50)
                
                time.sleep(self.poll_interval)
                
        except KeyboardInterrupt:
            print("\n🛑 Bot stopped by user")

if __name__ == '__main__':
    bot = EmailBot()
    bot.run()