import time
import functools
import json
from flask import request, jsonify, current_app
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from functools import wraps
from auth.models.models import User, UserRole
import jwt

from common.cache import get_redis_client

def rate_limit(limit=100, per=60, key_prefix='rl'):
    """
    Rate limiting decorator.
    
    Args:
        limit (int): Maximum number of requests allowed within time period
        per (int): Time period in seconds
        key_prefix (str): Redis key prefix for rate limit counters
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            # Get client IP or use JWT identity if available
            try:
                verify_jwt_in_request(optional=True)
                user_id = get_jwt_identity()
                if user_id:
                    key = f"{key_prefix}:user:{user_id}"
                else:
                    key = f"{key_prefix}:ip:{request.remote_addr}"
            except:
                key = f"{key_prefix}:ip:{request.remote_addr}"
            
            # Get Redis client
            redis_client = get_redis_client(current_app)
            if not redis_client:
                # If Redis is not available, skip rate limiting
                return f(*args, **kwargs)
            
            # Get current counter and timestamp
            current = time.time()
            p = redis_client.pipeline()
            p.get(key)
            p.get(f"{key}:ts")
            count, timestamp = p.execute()
            
            # Initialize counter if not exists
            if not count:
                count = 0
            else:
                count = int(count)
            
            # Initialize timestamp if not exists
            if not timestamp:
                timestamp = current
            else:
                timestamp = float(timestamp)
            
            # Reset counter if outside time window
            time_passed = current - float(timestamp)
            if time_passed > per:
                count = 0
                timestamp = current
            
            # Check if limit exceeded
            if count >= limit:
                response = {
                    "error": "Rate limit exceeded",
                    "retry_after": int(per - time_passed)
                }
                return jsonify(response), 429
            
            # Increment counter
            p = redis_client.pipeline()
            p.incr(key)
            p.setex(key, per, count + 1)
            p.setex(f"{key}:ts", per, timestamp)
            p.execute()
            
            # Continue with request
            return f(*args, **kwargs)
        return wrapped
    return decorator

def cache_response(timeout=300, key_prefix='cache'):
    """
    Cache response decorator.
    
    Args:
        timeout (int): Cache timeout in seconds
        key_prefix (str): Redis key prefix for cached responses
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            # Skip cache for non-GET requests
            if request.method != 'GET':
                return f(*args, **kwargs)
            
            # Get Redis client
            redis_client = get_redis_client(current_app)
            if not redis_client:
                # If Redis is not available, skip caching
                return f(*args, **kwargs)
            
            # Generate cache key
            path = request.path
            query = request.query_string.decode('utf-8')
            key = f"{key_prefix}:{path}:{query}"
            
            # Try to get from cache
            cached_response = redis_client.get(key)
            if cached_response:
                return jsonify(json.loads(cached_response)), 200
            
            # Get response from function
            response_obj, status_code = f(*args, **kwargs)
            
            # Cache response if status code is 200
            if status_code == 200:
                data_to_cache = response_obj.get_json()
                redis_client.setex(key, timeout, json.dumps(data_to_cache))
            
            return response_obj, status_code
        return wrapped
    return decorator

def merchant_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user or user.role != UserRole.MERCHANT:
            return jsonify({"error": "Merchant access required"}), 403
        return fn(*args, **kwargs)
    return wrapper

def super_admin_role_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({'message': 'Invalid token format'}), 401

        if not token:
            return jsonify({'message': 'Token is missing'}), 401

        try:
            data = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
            # The identity is stored in the 'sub' claim by default in JWT
            user_id = data.get('sub')
            if not user_id:
                return jsonify({'message': 'Invalid token: missing user ID'}), 401

            current_user = User.query.filter_by(id=int(user_id)).first()

            if not current_user:
                return jsonify({'message': 'User not found'}), 404

            if current_user.role != UserRole.SUPER_ADMIN:
                return jsonify({'message': 'Unauthorized access'}), 403

            # Add the current user to the request context
            request.current_user = current_user

        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token'}), 401
        except ValueError:
            return jsonify({'message': 'Invalid user ID format'}), 401

        return f(*args, **kwargs)

    return decorated_function

# Alias for consistency with the controller naming
superadmin_required = super_admin_role_required