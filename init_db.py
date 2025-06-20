"""
Database initialization script.
Run this script to create the database and tables.
"""

import os
import mysql.connector
from dotenv import load_dotenv
from app import create_app
from common.database import db
from sqlalchemy import text

# --- Auth models ---
from auth.models.models import (
    User,
    MerchantProfile,
    RefreshToken,
    EmailVerification,
    PhoneVerification,
    UserRole,
    AuthProvider
)
from auth.models.merchant_document import (
    MerchantDocument,
    VerificationStatus,
    DocumentType,
    DocumentStatus
)
from auth.models.country_config import (
    CountryConfig,
    CountryCode
)

# --- Superadmin models ---
from models.category import Category
from models.brand import Brand
from models.brand_request import BrandRequest
from models.attribute import Attribute
from models.attribute_value import AttributeValue
from models.category_attribute import CategoryAttribute
from models.promotion import Promotion
from models.product_promotion import ProductPromotion
from models.tax_category import TaxCategory
from models.homepage import HomepageCategory
from models.subscription import SubscriptionPlan

from models.gst_rule import GSTRule

from models.merchant_transaction import MerchantTransacti

# --- Merchant models ---
from models.product import Product
from models.product_meta import ProductMeta
from models.product_tax import ProductTax
from models.product_shipping import ProductShipping
from models.product_media import ProductMedia
from models.product_stock import ProductStock
from models.review import Review
from models.product_attribute import ProductAttribute
from models.recently_viewed import RecentlyViewed

# --- Live Streaming models ---
from models.live_stream import LiveStream, LiveStreamComment, LiveStreamViewer, StreamStatus

# --- Payment models ---
from models.payment_card import PaymentCard
from models.enums import CardTypeEnum, CardStatusEnum

# --- Monitoring models ---
from models.system_monitoring import SystemMonitoring

# --- Newsletter models ---
from models.newsletter_subscription import NewsletterSubscription


# Load environment variables
load_dotenv()

def create_database():
    """Create the database if it doesn't exist."""
    db_uri = os.getenv('DATABASE_URI')
    db_name = db_uri.split('/')[-1]

    # Extract credentials and host from URI
    auth_part = db_uri.split('@')[0].split('://')[1]
    user = auth_part.split(':')[0]
    password = auth_part.split(':')[1]
    host = db_uri.split('@')[1].split('/')[0]

    try:
        conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password
        )

        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        print(f"Database '{db_name}' created or already exists.")

        cursor.close()
        conn.close()
    except mysql.connector.Error as err:
        print(f"Error: {err}")

def init_country_configs():
    """Initialize country-specific configurations."""
    print("\nInitializing Country Configurations:")
    print("-------------------------------------")
    
    # Initialize India configuration
    print("\nIndia (IN) Configuration:")
    print("-------------------------")
    india_docs = CountryConfig.get_required_documents(CountryCode.INDIA.value)
    print(f"Required Documents: {len(india_docs)} documents configured")
    
    india_validations = CountryConfig.get_field_validations(CountryCode.INDIA.value)
    print(f"Field Validations: {len(india_validations)} validation rules configured")
    
    india_bank_fields = CountryConfig.get_bank_fields(CountryCode.INDIA.value)
    print(f"Bank Fields: {len(india_bank_fields)} bank fields configured")
    
    india_tax_fields = CountryConfig.get_tax_fields(CountryCode.INDIA.value)
    print(f"Tax Fields: {len(india_tax_fields)} tax fields configured")

    # Initialize Global configuration
    print("\nGlobal Configuration:")
    print("---------------------")
    global_docs = CountryConfig.get_required_documents(CountryCode.GLOBAL.value)
    print(f"Required Documents: {len(global_docs)} documents configured")
    
    global_validations = CountryConfig.get_field_validations(CountryCode.GLOBAL.value)
    print(f"Field Validations: {len(global_validations)} validation rules configured")
    
    global_bank_fields = CountryConfig.get_bank_fields(CountryCode.GLOBAL.value)
    print(f"Bank Fields: {len(global_bank_fields)} bank fields configured")
    
    global_tax_fields = CountryConfig.get_tax_fields(CountryCode.GLOBAL.value)
    print(f"Tax Fields: {len(global_tax_fields)} tax fields configured")

    print("\nCountry configurations initialized successfully.")

def init_tax_categories():
    """Initialize standard tax categories."""
    print("\nInitializing Tax Categories:")
    print("----------------------------")
    
    tax_categories = [
        {
            'name': 'Standard Rate',
            'description': 'Standard tax rate applicable to most goods and services',
            'tax_rate': 18.00
        },
        {
            'name': 'Reduced Rate',
            'description': 'Reduced tax rate for specific goods and services',
            'tax_rate': 12.00
        },
        {
            'name': 'Zero Rate',
            'description': 'Zero tax rate for exempted goods and services',
            'tax_rate': 0.00
        }
    ]
    
    for tax_data in tax_categories:
        existing_tax = TaxCategory.query.filter_by(name=tax_data['name']).first()
        if not existing_tax:
            tax_category = TaxCategory(**tax_data)
            db.session.add(tax_category)
            print(f"Created tax category: {tax_data['name']} ({tax_data['tax_rate']}%)")
    
    db.session.commit()
    print("Tax categories initialized successfully.")

def init_brand_categories():
    """Initialize brand-category relationships."""
    print("\nInitializing Brand-Category Relationships:")
    print("----------------------------------------")
    print("Brand-category relationships will be managed manually by users.")
    print("No automatic associations will be made.")
    
    # No automatic associations - brands will be associated with categories
    # through user actions in the application
    db.session.commit()
    print("Brand-category relationships initialized successfully.")

def init_product_stocks():
    """Initialize product stocks for existing products."""
    print("\nInitializing Product Stocks:")
    print("---------------------------")
    
    # Get all products without stock records
    products = Product.query.all()
    
    for product in products:
        existing_stock = ProductStock.query.filter_by(product_id=product.product_id).first()
        if not existing_stock:
            stock = ProductStock(
                product_id=product.product_id,
                stock_qty=0,
                low_stock_threshold=5,  # Default threshold
               
            )
            db.session.add(stock)
            print(f"Created stock record for product: {product.product_name}")
    
    db.session.commit()
    print("Product stocks initialized successfully.")

def init_recently_viewed():
    """Initialize recently viewed table."""
    print("\nInitializing Recently Viewed Table:")
    print("----------------------------------")
    
    # Check if the table exists using SQLAlchemy inspector
    inspector = db.inspect(db.engine)
    if 'recently_viewed' not in inspector.get_table_names():
        print("Creating recently_viewed table...")
        RecentlyViewed.__table__.create(db.engine)
        print("Recently viewed table created successfully.")
    else:
        print("Recently viewed table already exists.")

def init_homepage_categories():
    """Initialize homepage categories table."""
    print("\nInitializing Homepage Categories:")
    print("--------------------------------")
    
    # Check if the table exists using SQLAlchemy inspector
    inspector = db.inspect(db.engine)
    if 'homepage_categories' not in inspector.get_table_names():
        print("Creating homepage_categories table...")
        HomepageCategory.__table__.create(db.engine)
        print("Homepage categories table created successfully.")
    else:
        print("Homepage categories table already exists.")

def init_subscription_plans():
    """Initialize standard subscription plans."""
    print("\nInitializing Subscription Plans:")
    print("------------------------------")
    
    # Check if can_place_premium column exists, if not add it
    try:
        with db.engine.connect() as conn:
            conn.execute(text("""
                SELECT can_place_premium 
                FROM subscription_plans 
                LIMIT 1
            """))
    except Exception:
        print("Adding can_place_premium column to subscription_plans table...")
        with db.engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE subscription_plans 
                ADD COLUMN can_place_premium BOOLEAN NOT NULL DEFAULT FALSE
            """))
            conn.commit()
    
    subscription_plans = [
        {
            'name': 'Basic',
            'description': 'Basic subscription plan with limited features',
            'featured_limit': 10,
            'promo_limit': 10,
            'duration_days': 30,
            'price': 29.99,
            'active_flag': True,
            'can_place_premium': False,
            'approval_status': 'approved'
        },
        {
            'name': 'Professional',
            'description': 'Professional subscription plan with advanced features',
            'featured_limit': 50,
            'promo_limit': 50,
            'duration_days': 30,
            'price': 79.99,
            'active_flag': True,
            'can_place_premium': True,
            'approval_status': 'approved'
        },
        {
            'name': 'Enterprise',
            'description': 'Enterprise subscription plan with unlimited features',
            'featured_limit': 999999,
            'promo_limit': 999999,
            'duration_days': 30,
            'price': 199.99,
            'active_flag': True,
            'can_place_premium': True,
            'approval_status': 'approved'
        }
    ]
    
    for plan_data in subscription_plans:
        existing_plan = SubscriptionPlan.query.filter_by(name=plan_data['name']).first()
        if not existing_plan:
            subscription_plan = SubscriptionPlan(**plan_data)
            db.session.add(subscription_plan)
            print(f"Created subscription plan: {plan_data['name']} (${plan_data['price']})")
        else:
            # Update existing plan with new values
            for key, value in plan_data.items():
                setattr(existing_plan, key, value)
            print(f"Updated subscription plan: {plan_data['name']} (${plan_data['price']})")
    
    db.session.commit()
    print("Subscription plans initialized successfully.")

def init_payment_cards():
    """Initialize payment cards table and encryption key."""
    print("\nInitializing Payment Cards:")
    print("--------------------------")
    
    # Check if the table exists using SQLAlchemy inspector
    inspector = db.inspect(db.engine)
    if 'payment_cards' not in inspector.get_table_names():
        print("Creating payment_cards table...")
        PaymentCard.__table__.create(db.engine)
        print("Payment cards table created successfully.")
    else:
        print("Payment cards table already exists.")
    
    # Check if CARD_ENCRYPTION_KEY exists in app config
    app = create_app()
    with app.app_context():
        if not app.config.get('CARD_ENCRYPTION_KEY'):
            from cryptography.fernet import Fernet
            app.config['CARD_ENCRYPTION_KEY'] = Fernet.generate_key()
            print("Generated new card encryption key.")
        else:
            print("Card encryption key already exists.")

def init_system_monitoring():
    """Initialize system monitoring table."""
    print("\nInitializing System Monitoring:")
    print("-----------------------------")
    
    # Check if the table exists using SQLAlchemy inspector
    inspector = db.inspect(db.engine)
    if 'system_monitoring' not in inspector.get_table_names():
        print("Creating system_monitoring table...")
        SystemMonitoring.__table__.create(db.engine)
        print("System monitoring table created successfully.")
    else:
        print("System monitoring table already exists.")
    
    # Create initial system status record
    initial_status = SystemMonitoring.create_service_status(
        service_name='system_init',
        status='up',
        response_time=0.0,
        memory_usage=0.0,
        cpu_usage=0.0
    )
    db.session.add(initial_status)
    db.session.commit()
    print("Initial system status record created.")

def init_live_streaming():
    """Initialize live streaming tables."""
    print("\nInitializing Live Streaming Tables:")
    print("---------------------------------")
    
    # Check if the tables exist using SQLAlchemy inspector
    inspector = db.inspect(db.engine)
    tables = ['live_streams', 'live_stream_comments', 'live_stream_viewers']
    
    for table in tables:
        if table not in inspector.get_table_names():
            print(f"Creating {table} table...")
            if table == 'live_streams':
                LiveStream.__table__.create(db.engine)
            elif table == 'live_stream_comments':
                LiveStreamComment.__table__.create(db.engine)
            elif table == 'live_stream_viewers':
                LiveStreamViewer.__table__.create(db.engine)
            print(f"{table} table created successfully.")
        else:
            print(f"{table} table already exists.")
    
    # Add stream_status enum if it doesn't exist
    try:
        with db.engine.connect() as conn:
            conn.execute(text("""
                SELECT stream_status 
                FROM live_streams 
                LIMIT 1
            """))
    except Exception:
        print("Adding stream_status enum to live_streams table...")
        with db.engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE live_streams 
                MODIFY COLUMN status ENUM('scheduled', 'live', 'ended', 'cancelled') 
                NOT NULL DEFAULT 'scheduled'
            """))
            conn.commit()
    
    print("Live streaming tables initialized successfully.")

def migrate_profile_img_column():
    """Add profile_img column to users table if it doesn't exist."""
    print("\nMigrating profile_img column:")
    print("----------------------------")
    
    inspector = db.inspect(db.engine)
    
    if 'users' in inspector.get_table_names():
        existing_columns = [col['name'] for col in inspector.get_columns('users')]
        
        if 'profile_img' not in existing_columns:
            print("Adding profile_img column to users table...")
            try:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE users ADD COLUMN profile_img VARCHAR(512) NULL"))
                    conn.commit()
                print("✓ profile_img column added successfully")
            except Exception as e:
                print(f"✗ Failed to add profile_img column: {str(e)}")
        else:
            print("✓ profile_img column already exists")
    else:
        print("✗ users table does not exist")

def init_database():
    """Initialize the database with all tables and initial data."""
    app = create_app()
    with app.app_context():
        print("Initializing Database:")
        print("=====================")
        
        # Create database if it doesn't exist
        create_database()
        
        # Create all tables
        print("\nCreating tables...")
        db.create_all()
        print("✓ All tables created successfully.")
        
        # Run migrations
        migrate_profile_img_column()
        
        # Initialize data
        init_country_configs()
        init_tax_categories()
        init_brand_categories()
        init_product_stocks()
        init_recently_viewed()
        init_homepage_categories()
        init_subscription_plans()
        init_payment_cards()
        init_system_monitoring()
        init_live_streaming()
        
        # Create super admin user if not exists
        admin_email = os.getenv("SUPER_ADMIN_EMAIL")
        admin_first_name = os.getenv("SUPER_ADMIN_FIRST_NAME")
        admin_last_name = os.getenv("SUPER_ADMIN_LAST_NAME")
        admin_password = os.getenv("SUPER_ADMIN_PASSWORD")

        admin = User.get_by_email(admin_email)
        if not admin:
            admin = User(
                email=admin_email,
                first_name=admin_first_name,
                last_name=admin_last_name,
                role=UserRole.SUPER_ADMIN,
                is_email_verified=True
            )
            admin.set_password(admin_password)
            admin.save()
            print("Super admin user created.")
        
        print("\nDatabase initialization completed successfully!")


if __name__ == "__main__":
    create_database()
    init_database()
    print("Database initialization completed.")
