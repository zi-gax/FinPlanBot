import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram Bot Token
API_token = os.getenv('TELEGRAM_BOT_TOKEN')

# Multiple Gemini API keys for failover support
# Load from environment variables (.env file)
# Add as many API keys as you want - the bot will automatically switch to the next one if one hits a limit
GEMINI_API_KEYS = [
    key for key in [
        os.getenv('GEMINI_API_KEY_1'),
        os.getenv('GEMINI_API_KEY_2'),
        os.getenv('GEMINI_API_KEY_3'),
        os.getenv('GEMINI_API_KEY_4'),
        os.getenv('GEMINI_API_KEY_5'),
        os.getenv('GEMINI_API_KEY_6'),
        os.getenv('GEMINI_API_KEY_7'),
        os.getenv('GEMINI_API_KEY_8'),
        os.getenv('GEMINI_API_KEY_9'),
        os.getenv('GEMINI_API_KEY_10'),
    ] if key is not None
]

# Admin IDs - load from environment (comma-separated)
ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '452131035')
ADMIN_IDS = [int(uid.strip()) for uid in ADMIN_IDS_STR.split(',') if uid.strip().isdigit()]

# Database configuration
DATABASE_FILE = os.getenv('DATABASE_FILE', 'finplan.db')

# Logging configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'bot.log')

# Bot configuration
BOT_START_MAX_RETRIES = int(os.getenv('BOT_START_MAX_RETRIES', '5'))
BOT_START_RETRY_DELAY = int(os.getenv('BOT_START_RETRY_DELAY', '3'))
BOT_PREFLIGHT_RETRIES = int(os.getenv('BOT_PREFLIGHT_RETRIES', '3'))

# Network Resilience Configuration
NETWORK_RETRY_MAX_ATTEMPTS = int(os.getenv('NETWORK_RETRY_MAX_ATTEMPTS', '10'))
NETWORK_RETRY_INITIAL_DELAY = float(os.getenv('NETWORK_RETRY_INITIAL_DELAY', '1'))
NETWORK_RETRY_MAX_DELAY = float(os.getenv('NETWORK_RETRY_MAX_DELAY', '60'))
NETWORK_RETRY_EXPONENTIAL_BASE = float(os.getenv('NETWORK_RETRY_EXPONENTIAL_BASE', '2'))

# Connection timeout settings (seconds)
BOT_CONNECTION_TIMEOUT = int(os.getenv('BOT_CONNECTION_TIMEOUT', '30'))
BOT_READ_TIMEOUT = int(os.getenv('BOT_READ_TIMEOUT', '30'))

# Environment type
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

# Validation
if not API_token:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set!")
if not GEMINI_API_KEYS:
    raise ValueError("At least one GEMINI_API_KEY environment variable is required!")
if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS environment variable is not set or invalid!")
