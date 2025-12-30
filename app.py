from flask import Flask, jsonify, request,make_response, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from common.cache import cached
import os
import cloudinary
import cloudinary.uploader
import cloudinary.api
from config import get_config
from common.database import db
from common.cache import cache
from auth.routes import auth_bp
from auth.document_route import document_bp
from auth.country_route import country_bp
from api.users.routes import users_bp
from api.merchants.routes import merchants_bp
from auth import email_init
from models import *  # Import all models
from models.system_monitoring import SystemMonitoring

from routes.superadmin_routes import superadmin_bp
from routes.merchant_routes import merchant_dashboard_bp
from routes.product_routes import product_bp
from routes.category_routes import category_bp
from routes.brand_routes import brand_bp
from routes.homepage_routes import homepage_bp
from routes.cart_routes import cart_bp
from routes.wishlist_routes import wishlist_bp
from routes.order_routes import order_bp
from routes.user_address_routes import user_address_bp
from routes.currency_routes import currency_bp
from routes.feature_product_routes import feature_product_bp

from routes.promo_product_routes import promo_product_bp
from auth.admin_routes import admin_bp
from routes.payment_card_routes import payment_card_bp
from routes.review_routes import review_bp
from routes.analytics_routes import analytics_bp

from routes.merchant_support_routes import merchant_support_bp
from routes.admin_support_routes import admin_support_bp
from routes.user_support_routes import user_support_bp
from routes.promotion_routes import superadmin_promotion_bp
from routes.promo_code_routes import promo_code_bp
from routes.merchant_transaction_routes import merchant_transaction_bp

from routes.games_routes import games_bp
from routes.shiprocket_routes import shiprocket_bp
from routes.live_stream_public_routes import live_stream_public_bp
from routes.shop.shop_product_routes import shop_product_bp
from routes.shop.shop_routes import shop_bp
from routes.shop.shop_category_routes import shop_category_bp
from routes.shop.shop_brand_routes import shop_brand_bp
from routes.shop.shop_attribute_routes import shop_attribute_bp
from routes.shop.shop_stock_routes import shop_stock_bp
from routes.shop.variant_routes import variant_bp
from routes.shop.shop_review_routes import shop_review_bp

# Public shop routes
from routes.shop.public.public_shop_routes import public_shop_bp
from routes.shop.public.public_shop_product_routes import public_shop_product_bp
from routes.shop.public.public_shop_category_routes import public_shop_category_bp
from routes.shop.public.public_shop_brand_routes import public_shop_brand_bp
from routes.shop.public.public_shop_cart_routes import public_shop_cart_bp
from routes.shop.public.public_shop_wishlsit_routes import public_shop_wishlist_bp
from routes.shop.public.public_shop_order_routes import public_shop_order_bp

from routes.upload_routes import upload_bp
from routes.translate_routes import translate_bp
from routes.razorpay_routes import razorpay_bp
from routes.ai_image_upload import ai_image_upload_bp


from flasgger import Swagger
from cryptography.fernet import Fernet
import time
import psutil
import traceback
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import threading
from controllers.newsletter_public_controller import newsletter_public_bp
from flask import send_from_directory as flask_send_from_directory


ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://kea.mywire.org:5300",
    "https://aoinstore.com"
    
]

def add_headers(response):
    origin = request.headers.get('Origin')
    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
    else:
        response.headers['Access-Control-Allow-Origin'] = 'null'  # or omit completely if strict

    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-CSRF-Token'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Max-Age'] = '3600'  # Cache preflight requests for 1 hour
    return response

def create_app(config_name='default'):
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(get_config())
    # Set max content length for file uploads (100MB for videos)
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
    # Increase request timeout for large file uploads (10 minutes)
    # Note: This is for the development server. Production servers (gunicorn, uwsgi) have their own timeout settings
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Don't cache uploaded files
    
    # Configure werkzeug to handle large file uploads better
    # Increase the max form data size (default is usually 16MB)
    from werkzeug.formparser import default_stream_factory
    import tempfile
    import os
    
    # Use a larger buffer for multipart parsing
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
    
    # Configure werkzeug to use a larger buffer for multipart parsing
    # This helps prevent ClientDisconnected errors
    try:
        # Set environment variable for werkzeug
        os.environ['WERKZEUG_RUN_MAIN'] = 'true'
    except:
        pass
    
    # app.config['CARD_ENCRYPTION_KEY'] = Fernet.generate_key()  

    # Configure Cloudinary
    cloudinary.config(
        cloud_name=app.config.get('CLOUDINARY_CLOUD_NAME'),
        api_key=app.config.get('CLOUDINARY_API_KEY'),
        api_secret=app.config.get('CLOUDINARY_API_SECRET'),
        secure=True
    )

    # Configure Swagger
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": 'apispec',
                "route": '/apispec.json',
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/docs"
    }

    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "Ecommerce Backend API",
            "description": "API documentation for Ecommerce Backend",
            "version": "1.0.0",
            "contact": {
                "email": "Scalixity@gmail.com"
            }
        },
        "securityDefinitions": {
            "Bearer": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "description": "JWT Authorization header using the Bearer scheme. Example: \"Authorization: Bearer {token}\""
            }
        },
        "security": [
            {
                "Bearer": []
            }
        ]
    }

    Swagger(app, config=swagger_config, template=swagger_template)

    # Configure CORS with more specific settings
    # IMPORTANT: For file uploads, we need to allow all headers and methods
    CORS(app, 
         resources={
             r"/api/*": {
                 "origins": ALLOWED_ORIGINS,
                 "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
                 "allow_headers": ["Content-Type", "Authorization", "X-CSRF-Token", "Accept"],
                 "expose_headers": ["Content-Type", "Authorization"]
             }
         },
         supports_credentials=True,
         allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "Accept"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
         max_age=3600)  # Cache preflight requests for 1 hour

    # Initialize extensions
    db.init_app(app)
    
    # Initialize cache - use null cache (no Redis required)
    # Set CACHE_TYPE to null BEFORE init_app to prevent any Redis connection attempts
    app.config['CACHE_TYPE'] = 'null'
    app.config.pop('REDIS_URL', None)  # Remove REDIS_URL to prevent Flask-Caching from trying to connect
    app.config.pop('CACHE_REDIS_URL', None)  # Remove CACHE_REDIS_URL as well
    try:
        cache.init_app(app)
    except Exception as e:
        # If cache initialization fails, just continue - caching is optional
        app.logger.warning(f"Cache initialization failed (non-critical): {str(e)}")
    
    jwt = JWTManager(app)
    email_init.init_app(app)
    migrate = Migrate(app, db)

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(merchants_bp, url_prefix='/api/merchants')
    app.register_blueprint(document_bp, url_prefix='/api/merchant/documents')
    app.register_blueprint(superadmin_bp, url_prefix='/api/superadmin')
    app.register_blueprint(merchant_dashboard_bp, url_prefix='/api/merchant-dashboard')
    app.register_blueprint(country_bp)
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(product_bp)
    app.register_blueprint(category_bp, url_prefix='/api/categories')
    app.register_blueprint(brand_bp, url_prefix='/api/brands')
    app.register_blueprint(homepage_bp, url_prefix='/api/homepage')
    app.register_blueprint(cart_bp, url_prefix='/api/cart')
    app.register_blueprint(wishlist_bp, url_prefix='/api/wishlist')
    app.register_blueprint(order_bp, url_prefix='/api/orders')
    app.register_blueprint(user_address_bp, url_prefix='/api/user-address')
    app.register_blueprint(currency_bp)
    app.register_blueprint(feature_product_bp, url_prefix='/api/featured-products')
    app.register_blueprint(promo_product_bp, url_prefix='/api/promo-products')
    app.register_blueprint(payment_card_bp)
    app.register_blueprint(review_bp, url_prefix='/api/reviews')

    app.register_blueprint(merchant_support_bp)
    app.register_blueprint(admin_support_bp)
    app.register_blueprint(user_support_bp)

    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    
    app.register_blueprint(superadmin_promotion_bp)
    app.register_blueprint(promo_code_bp)
    app.register_blueprint(merchant_transaction_bp, url_prefix='/api')

    app.register_blueprint(games_bp)
    app.register_blueprint(shiprocket_bp)
    app.register_blueprint(live_stream_public_bp)
    app.register_blueprint(shop_product_bp)
    app.register_blueprint(shop_bp)
    app.register_blueprint(shop_category_bp)
    app.register_blueprint(shop_brand_bp)
    app.register_blueprint(shop_attribute_bp)
    app.register_blueprint(shop_stock_bp)
    app.register_blueprint(variant_bp, url_prefix='/api/shop')
    app.register_blueprint(shop_review_bp)

    
    # Register public shop routes
    app.register_blueprint(public_shop_bp)
    app.register_blueprint(public_shop_product_bp)
    app.register_blueprint(public_shop_category_bp)
    app.register_blueprint(public_shop_brand_bp)
    app.register_blueprint(public_shop_cart_bp, url_prefix='/api/shop-cart')
    app.register_blueprint(public_shop_wishlist_bp)
    app.register_blueprint(public_shop_order_bp, url_prefix='/api')

    app.register_blueprint(newsletter_public_bp, url_prefix='/api/public')

    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(razorpay_bp)
    app.register_blueprint(ai_image_upload_bp)

    # Optional: Translation endpoints behind feature flag
    if app.config.get('FEATURE_TRANSLATION'):
        app.register_blueprint(translate_bp)

    # Serve static files (temporary uploads for AI processing)
    @app.route('/static/temp_uploads/<path:filename>')
    def serve_temp_upload(filename):
        """Serve temporary uploaded files"""
        static_folder = os.path.join(app.root_path, 'static', 'temp_uploads')
        return send_from_directory(static_folder, filename)

    # Add custom headers to every response
    app.after_request(add_headers)

    # Handle OPTIONS preflight requests FIRST (before other middleware)
    # This must be registered BEFORE the monitoring middleware
    @app.before_request
    def handle_preflight():
        # Log ALL requests immediately to see if they're reaching Flask
        print(f"[FLASK_REQUEST] {request.method} {request.path} - Request reached Flask!")
        
        if request.method == "OPTIONS":
            print(f"[PREFLIGHT] OPTIONS request for {request.path}")
            print(f"[PREFLIGHT] Origin: {request.headers.get('Origin')}")
            print(f"[PREFLIGHT] Access-Control-Request-Method: {request.headers.get('Access-Control-Request-Method')}")
            print(f"[PREFLIGHT] Access-Control-Request-Headers: {request.headers.get('Access-Control-Request-Headers')}")
            response = jsonify({})
            origin = request.headers.get('Origin')
            if origin in ALLOWED_ORIGINS:
                response.headers.add("Access-Control-Allow-Origin", origin)
            else:
                response.headers.add("Access-Control-Allow-Origin", ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*")
            response.headers.add('Access-Control-Allow-Headers', "Content-Type, Authorization, X-CSRF-Token, Accept")
            response.headers.add('Access-Control-Allow-Methods', "GET, POST, PUT, DELETE, OPTIONS, PATCH")
            response.headers.add('Access-Control-Allow-Credentials', 'true')
            response.headers.add('Access-Control-Max-Age', '3600')
            print(f"[PREFLIGHT] Returning preflight response")
            return response
    
    # Add monitoring middleware
    @app.before_request
    def before_request():
        request.start_time = time.time()
        # Log ALL requests to see if they're reaching the server
        print(f"[BEFORE_REQUEST] {request.method} {request.path}")
        print(f"[BEFORE_REQUEST] Content-Type: {request.content_type}")
        print(f"[BEFORE_REQUEST] Content-Length: {request.content_length}")
        print(f"[BEFORE_REQUEST] Remote Address: {request.remote_addr}")
        
        # Special logging for media uploads
        if '/products/' in request.path and '/media' in request.path:
            print(f"[BEFORE_REQUEST] *** MEDIA UPLOAD REQUEST DETECTED ***")
            print(f"[BEFORE_REQUEST] Method: {request.method}")
            print(f"[BEFORE_REQUEST] Path: {request.path}")
            print(f"[BEFORE_REQUEST] Content-Type: {request.content_type}")
            print(f"[BEFORE_REQUEST] Content-Length: {request.content_length}")
            print(f"[BEFORE_REQUEST] Origin: {request.headers.get('Origin')}")
            # DO NOT access request.files or request.form here - it triggers multipart parsing
            # which can cause ClientDisconnected errors for large files
            # These will be available in the actual route handler after parsing completes

    @app.after_request
    def after_request(response):
        if hasattr(request, 'start_time'):
            response_time = (time.time() - request.start_time) * 1000  # Convert to milliseconds
            
            # Get system metrics
            process = psutil.Process()
            memory_usage = process.memory_info().rss / 1024 / 1024  # Convert to MB
            
            # Get CPU usage with interval
            try:
                # Get CPU usage with a small interval to ensure accurate reading
                cpu_usage = process.cpu_percent(interval=0.1)
                if cpu_usage == 0:
                    # If still 0, try getting system-wide CPU usage
                    cpu_usage = psutil.cpu_percent(interval=0.1)
            except Exception as e:
                print(f"Error getting CPU usage: {str(e)}")
                cpu_usage = 0
            
            # Determine status based on response status code
            status = 'up'
            if response.status_code >= 400:
                status = 'error'
                # Log error responses for debugging
                if '/products/' in request.path and '/media' in request.path:
                    print(f"[AFTER_REQUEST] {request.method} {request.path} -> {response.status_code}")
                    print(f"[AFTER_REQUEST] Response: {response.get_data(as_text=True)[:500]}")
                # Create error monitoring record for API errors
                monitoring = SystemMonitoring.create_error_record(
                    service_name=request.endpoint or 'unknown',
                    error_type=f'HTTP_{response.status_code}',
                    error_message=response.get_data(as_text=True),
                    endpoint=request.path,
                    http_method=request.method,
                    http_status=response.status_code
                )
                db.session.add(monitoring)
            else:
                # Create normal service status record
                monitoring = SystemMonitoring.create_service_status(
                    service_name=request.endpoint or 'unknown',
                    status=status,
                    response_time=response_time,
                    memory_usage=memory_usage,
                    cpu_usage=cpu_usage
                )
                db.session.add(monitoring)
            
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"Error saving monitoring data: {str(e)}")
            
        return response

    @app.errorhandler(Exception)
    def handle_error(error):
        # Get error details
        error_type = type(error).__name__
        error_message = str(error)
        error_stack = traceback.format_exc()
        
        # Skip Redis connection errors - they're not critical
        if 'ConnectionError' in error_type or '6379' in error_message or 'Redis' in error_type:
            app.logger.warning(f"Redis connection error ignored: {error_message}")
            # For Redis errors, try to continue without cache
            # Return a generic error instead of exposing Redis details
            return jsonify({
                'error': 'Service temporarily unavailable. Please try again.',
                'type': 'ServiceError'
            }), 503
        
        # Log error to console immediately
        print("=" * 80)
        print(f"[ERROR_HANDLER] *** UNHANDLED EXCEPTION CAUGHT ***")
        print(f"[ERROR_HANDLER] Type: {error_type}")
        print(f"[ERROR_HANDLER] Message: {error_message}")
        print(f"[ERROR_HANDLER] Path: {request.path}")
        print(f"[ERROR_HANDLER] Method: {request.method}")
        print(f"[ERROR_HANDLER] Stack trace:")
        print(error_stack)
        print("=" * 80)
        
        # Create error monitoring record
        try:
            monitoring = SystemMonitoring.create_error_record(
                service_name=request.endpoint or 'unknown',
                error_type=error_type,
                error_message=error_message,
                error_stack_trace=error_stack,
                endpoint=request.path,
                http_method=request.method,
                http_status=getattr(error, 'code', 500)
            )
            db.session.add(monitoring)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error saving error monitoring data: {str(e)}")
        
        # Return error response
        return jsonify({
            'error': error_message,
            'type': error_type
        }), getattr(error, 'code', 500)

    # Add monitoring endpoints
    @app.route('/api/monitoring/status')
    def get_system_status():
        """Get current system status"""
        services = db.session.query(SystemMonitoring).order_by(
            SystemMonitoring.timestamp.desc()
        ).limit(10).all()
        
        return jsonify({
            'services': [service.serialize() for service in services]
        })

    @app.route('/api/monitoring/metrics')
    def get_system_metrics():
        """Get system metrics"""
        # Get average response time for last hour
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        avg_response = db.session.query(
            db.func.avg(SystemMonitoring.response_time)
        ).filter(
            SystemMonitoring.timestamp >= one_hour_ago,
            SystemMonitoring.response_time.isnot(None)
        ).scalar() or 0

        # Get error count for last hour
        error_count = db.session.query(
            db.func.count(SystemMonitoring.monitoring_id)
        ).filter(
            SystemMonitoring.timestamp >= one_hour_ago,
            SystemMonitoring.status == 'error'
        ).scalar() or 0

        # Get current system metrics
        process = psutil.Process()
        memory_usage = process.memory_info().rss / 1024 / 1024
        
        # Get CPU usage with interval
        try:
            # Get CPU usage with a small interval to ensure accurate reading
            cpu_usage = process.cpu_percent(interval=0.1)
            if cpu_usage == 0:
                # If still 0, try getting system-wide CPU usage
                cpu_usage = psutil.cpu_percent(interval=0.1)
        except Exception as e:
            print(f"Error getting CPU usage: {str(e)}")
            cpu_usage = 0

        return jsonify({
            'avg_response_time': round(avg_response, 2),
            'error_count_last_hour': error_count,
            'memory_usage_mb': round(memory_usage, 2),
            'cpu_usage_percent': round(cpu_usage, 2),
            'uptime_seconds': time.time() - psutil.boot_time()
        })

    # Test Redis cache endpoint
    @app.route('/api/test-cache')
    @cached(timeout=30)
    def test_cache():
        import time
        time.sleep(2)
        return jsonify({
            'message': 'This response is cached for 30 seconds',
            'timestamp': time.time()
        })
    
    # Test endpoint for file upload debugging
    @app.route('/api/test-upload', methods=['POST', 'OPTIONS'])
    def test_upload():
        """Simple test endpoint to verify POST requests work"""
        if request.method == 'OPTIONS':
            print("[TEST_UPLOAD] OPTIONS preflight received")
            response = jsonify({})
            origin = request.headers.get('Origin')
            if origin in ALLOWED_ORIGINS:
                response.headers.add("Access-Control-Allow-Origin", origin)
            response.headers.add('Access-Control-Allow-Headers', "Content-Type, Authorization")
            response.headers.add('Access-Control-Allow-Methods', "POST, OPTIONS")
            response.headers.add('Access-Control-Allow-Credentials', 'true')
            return response
        
        print("[TEST_UPLOAD] POST request received")
        print(f"[TEST_UPLOAD] Content-Type: {request.content_type}")
        print(f"[TEST_UPLOAD] Content-Length: {request.content_length}")
        print(f"[TEST_UPLOAD] Has files: {bool(request.files)}")
        
        if request.files:
            print(f"[TEST_UPLOAD] Files: {list(request.files.keys())}")
        
        return jsonify({
            'message': 'Test upload endpoint working',
            'content_type': request.content_type,
            'content_length': request.content_length,
            'has_files': bool(request.files)
        }), 200

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {"error": "Not found"}, 404

    @app.errorhandler(500)
    def server_error(error):
        return {"error": "Internal server error"}, 500

    return app

if __name__ == "__main__":
    """
    Root Cause Analysis:
    --------------------
    Werkzeug's run_simple() has a bug where it checks WERKZEUG_SERVER_FD at line 1091:
        fd = int(os.environ["WERKZEUG_SERVER_FD"])
    
    This happens BEFORE checking use_reloader, causing:
    - KeyError if variable doesn't exist (even with use_reloader=False)
    - OSError if variable is invalid because Werkzeug tries socket.fromfd(fd)
    
    The core issue: Werkzeug checks the variable unconditionally, then tries to USE it
    if it exists, regardless of use_reloader setting.
    
    Proper Solution:
    ----------------
    Use gunicorn for development instead of Flask's dev server. Gunicorn doesn't have
    this issue and is more production-ready. This is the cleanest solution.
    """
    import os
    import sys
    
    app = create_app()
    
    print("=" * 60)
    print("Starting Flask server")
    print("=" * 60)
    print("Server will accept connections on: http://0.0.0.0:5110")
    print("Accessible from: http://127.0.0.1:5110 or http://localhost:5110")
    print("=" * 60)
    
    # Use gunicorn for development - it doesn't have the WERKZEUG_SERVER_FD issue
    # This is more reliable than patching Werkzeug's bug
    try:
        from gunicorn.app.base import BaseApplication
        
        class StandaloneApplication(BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()
            
            def load_config(self):
                for key, value in self.options.items():
                    self.cfg.set(key.lower(), value)
            
            def load(self):
                return self.application
        
        options = {
            'bind': '0.0.0.0:5110',
            'workers': 1,  # Single worker for development
            'threads': 4,  # Multiple threads for concurrent requests
            'timeout': 600,  # 10 minutes for large file uploads
            'keepalive': 5,
            'accesslog': '-',  # Log to stdout
            'errorlog': '-',   # Log to stderr
        }
        
        StandaloneApplication(app, options).run()
    except ImportError:
        # Fallback to Flask dev server if gunicorn not available
        print("⚠️  Gunicorn not available, using Flask development server")
        print("⚠️  Note: You may encounter WERKZEUG_SERVER_FD issues")
        print("💡 Install gunicorn for better reliability: pip install gunicorn")
        print()
        
        import werkzeug.serving
        werkzeug.serving.WSGIRequestHandler.timeout = 600
        
        # Remove WERKZEUG_SERVER_FD to avoid issues
        os.environ.pop('WERKZEUG_SERVER_FD', None)
        
        # Try app.run() - if it fails, provide helpful error message
        try:
            app.run(
                host='0.0.0.0',
                port=5110,
                threaded=True,
                use_reloader=False,
                debug=False
            )
        except (KeyError, OSError) as e:
            if 'WERKZEUG_SERVER_FD' in str(e) or 'Bad file descriptor' in str(e):
                print("\n" + "=" * 60)
                print("❌ ERROR: Werkzeug development server has a known bug")
                print("=" * 60)
                print("Root Cause: Werkzeug checks WERKZEUG_SERVER_FD before use_reloader")
                print("Solution: Use gunicorn instead (recommended):")
                print("  pip install gunicorn")
                print("  gunicorn -w 1 --threads 4 -b 0.0.0.0:5110 --timeout 600 app:app")
                print("=" * 60)
                sys.exit(1)
            raise
