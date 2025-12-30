import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from auth.models import User, UserRole, RefreshToken
import cloudinary.uploader
import cloudinary.api
from werkzeug.utils import secure_filename



def generate_email_verification_link(token, base_url):
    """Generate email verification link."""
    return f"{base_url}/verify-email/{token}"

def upload_to_cloudinary(file, folder, public_id=None):
    """Upload a file to Cloudinary."""
    try:
        # Validate file type
        if not file:
            return None, "No file provided"
        
        # Get file extension
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        if file_ext not in current_app.config['ALLOWED_IMAGE_EXTENSIONS']:
            return None, f"Invalid file type. Allowed types: {', '.join(current_app.config['ALLOWED_IMAGE_EXTENSIONS'])}"
        
        # Upload to Cloudinary
        upload_result = cloudinary.uploader.upload(
            file,
            folder=folder,
            public_id=public_id,
            resource_type="auto",
            unique_filename=True,
            overwrite=True
        )
        
        return upload_result, None
    except Exception as e:
        current_app.logger.error(f"Cloudinary upload error: {str(e)}")
        return None, str(e)

def delete_from_cloudinary(public_id):
    """Delete a file from Cloudinary."""
    try:
        result = cloudinary.uploader.destroy(public_id)
        return result, None
    except Exception as e:
        current_app.logger.error(f"Cloudinary delete error: {str(e)}")
        return None, str(e)

def role_required(required_roles):
    """Decorator to check if user has required role."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Add logging for media uploads
            if '/products/' in request.path and '/media' in request.path:
                print(f"[ROLE_CHECK] Starting role check for {request.method} {request.path}")
            
            try:
                # Verify JWT token
                verify_jwt_in_request()
                if '/products/' in request.path and '/media' in request.path:
                    print(f"[ROLE_CHECK] JWT verified")
                
                # Get current user identity
                current_user_id = get_jwt_identity()
                if '/products/' in request.path and '/media' in request.path:
                    print(f"[ROLE_CHECK] User ID: {current_user_id}")
                
                # Get user from database
                user = User.get_by_id(current_user_id)
                if not user:
                    if '/products/' in request.path and '/media' in request.path:
                        print(f"[ROLE_CHECK] User not found")
                    return jsonify({"error": "User not found"}), 404
                
                # Check if user has required role
                if user.role.value not in required_roles:
                    if '/products/' in request.path and '/media' in request.path:
                        print(f"[ROLE_CHECK] Insufficient permissions. User role: {user.role.value}, Required: {required_roles}")
                    return jsonify({"error": "Insufficient permissions"}), 403
                
                if '/products/' in request.path and '/media' in request.path:
                    print(f"[ROLE_CHECK] Role check passed, calling function")
                
                return fn(*args, **kwargs)
            except Exception as e:
                if '/products/' in request.path and '/media' in request.path:
                    print(f"[ROLE_CHECK] Error in role check: {e}")
                raise
        return wrapper
    return decorator

def user_role_required(fn):
    """Decorator for endpoints that require user role."""
    return role_required([UserRole.USER.value])(fn)

def merchant_role_required(fn):
    """Decorator for endpoints that require merchant role."""
    decorated_fn = role_required([UserRole.MERCHANT.value])(fn)
    
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # Add logging to see if decorator is being called
        if '/products/' in request.path and '/media' in request.path:
            print(f"[DECORATOR] merchant_role_required called for {request.method} {request.path}")
        # Call the decorated function
        return decorated_fn(*args, **kwargs)
    return wrapper

def admin_role_required(fn):
    """Decorator for endpoints that require admin role."""
    return role_required([UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value])(fn)

def super_admin_role_required(fn):
    """Decorator for endpoints that require super admin role."""
    return role_required([UserRole.SUPER_ADMIN.value])(fn)

def get_google_provider_cfg():
    """Get Google OAuth provider configuration."""
    import requests
    try:
        return requests.get(current_app.config['GOOGLE_DISCOVERY_URL']).json()
    except Exception as e:
        current_app.logger.error(f"Error fetching Google provider config: {str(e)}")
        return None

def validate_google_token(token):
    """Validate Google OAuth token."""
    try:
        idinfo = jwt.decode(
            token, 
            options={"verify_signature": False},
            algorithms=["RS256"]
        )
        
        # Verify token is issued by Google
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            return None
        
        # Verify audience is our app
        if idinfo['aud'] != current_app.config['GOOGLE_CLIENT_ID']:
            return None
        
        # Check token expiry
        if datetime.fromtimestamp(idinfo['exp']) < datetime.utcnow():
            return None
        
        return idinfo
    except Exception as e:
        current_app.logger.error(f"Error validating Google token: {str(e)}")
        return None
def get_super_admin_emails():
    """Get email addresses of all active super admins."""
    super_admins = User.query.filter_by(role=UserRole.SUPER_ADMIN, is_active=True).all()
    return [admin.email for admin in super_admins if admin.email]    