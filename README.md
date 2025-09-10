# Email Auto-Reply Bot

A simple Python bot that watches a Gmail inbox and automatically replies to emails using an open-source LLM.

## Features

- Watches a Gmail label for new emails
- Uses Hugging Face Transformers for LLM responses
- Replies in the same email thread
- Configurable polling interval

## Setup
1. **Download Credentials-json file from google cloud and add that file in your project root directory(named as credentials.json).**
   
2. **Clone the repository**
   ```bash
   git clone <your-repo>
   cd email-bot
   pip install -r requirements.txt
   python bot.py
