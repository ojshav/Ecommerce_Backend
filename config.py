import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Base configuration shared across environments."""
    
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev_key_not_for_production')
    DEBUG = False
    TESTING = False

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URI', 'mysql+pymysql://root:nihalsql@localhost:3306/ecommerce_db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # JWT
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt_dev_key_not_for_production')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=7)  # Increased from 1 hour to 7 days to reduce token expiration issues during API testing
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # Google OAuth
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
    GOOGLE_DISCOVERY_URL = 'https://accounts.google.com/.well-known/openid-configuration'

    # Redis Cache - DISABLED by default to avoid connection errors
    # Set CACHE_TYPE='redis' and REDIS_URL in environment if you want to use Redis
    CACHE_TYPE = 'null'  # Always use null cache - no Redis connection attempts
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutes
    # Don't set REDIS_URL or CACHE_REDIS_URL - this prevents Flask-Caching from trying to connect

    # Cloudinary
    CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')
    ALLOWED_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'svg', 'png', 'gif', 'webp', 'pdf', 'doc', 'docx']

    # GoDaddy Webmail SMTP Configuration
    MAIL_SERVER = 'smtpout.secureserver.net'  # GoDaddy SMTP server
    MAIL_PORT = 587  # GoDaddy uses port 587 for TLS
    MAIL_USE_TLS = True  # Enable TLS for GoDaddy
    MAIL_USE_SSL = False  # SSL is not used when TLS is enabled
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')  # Your GoDaddy email address (e.g., noreply@yourdomain.com)
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')  # Your GoDaddy email password
    MAIL_DEFAULT_SENDER = (os.getenv('MAIL_SENDER_NAME', 'AOIN'), os.getenv('MAIL_USERNAME'))

    FRONTEND_URL = 'http://localhost:5173'

    EXCHANGE_RATE_API_KEY = os.getenv('EXCHANGE_RATE_API_KEY', 'f60545f362ec1fdd1e5e7338')
    CARD_ENCRYPTION_KEY = os.getenv('CARD_ENCRYPTION_KEY')
    
    # ShipRocket Configuration
    SHIPROCKET_EMAIL = os.getenv('SHIPROCKET_EMAIL')
    SHIPROCKET_PASSWORD = os.getenv('SHIPROCKET_PASSWORD')
    SHIPROCKET_BASE_URL = 'https://apiv2.shiprocket.in/v1/external'

    # AWS / Translate
    AWS_REGION = os.getenv('AWS_REGION', 'ap-south-1')
    FEATURE_TRANSLATION = os.getenv('FEATURE_TRANSLATION', 'false').lower() in ('1', 'true', 'yes')
    
    # Razorpay Configuration
    RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID', 'rzp_test_1DP5mmOlF5G5ag')
    RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET', 'your_secret_key')

class DevelopmentConfig(Config):
    """Configuration for development environment."""
    DEBUG = True

class ProductionConfig(Config):
    """Configuration for production environment."""
    SECRET_KEY = os.getenv('SECRET_KEY')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URI')
    DEBUG = False

# Environment mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

def get_config():
    """Return the configuration class based on FLASK_ENV."""
    env = os.getenv('FLASK_ENV', 'default')
    return config.get(env, config['default'])
