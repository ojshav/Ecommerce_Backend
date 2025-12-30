import json
import functools
from flask_caching import Cache
import redis

# Initialize Flask-Caching extension
cache = Cache()

def get_redis_client(app=None):
    """Get Redis client based on app config or environment variables.
    
    Returns:
        redis.Redis: Redis client if connection successful, None otherwise
    """
    try:
        if app and app.config.get('REDIS_URL'):
            redis_url = app.config.get('REDIS_URL')
        else:
            # Fallback to default local Redis
            redis_url = 'redis://localhost:6379/0'
        
        # Create client with connection settings that prevent blocking
        client = redis.from_url(
            redis_url, 
            socket_connect_timeout=1,  # Very short timeout
            socket_timeout=1,
            socket_keepalive=False,
            retry_on_timeout=False,
            health_check_interval=0
        )
        # Test connection with very short timeout
        client.ping()
        return client
    except (redis.ConnectionError, redis.TimeoutError, OSError, Exception) as e:
        # Log error if app context is available, but don't raise
        if app:
            try:
                app.logger.warning(f"Redis connection failed: {str(e)}. Caching disabled.")
            except:
                pass  # Don't fail if logging fails
        return None

def cache_key_prefix(key_prefix):
    """Create a cache key prefix for differentiating cached data types."""
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def cached(timeout=300, key_prefix='default'):
    """Custom caching decorator with prefix support."""
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            # Skip caching if cache type is null or cache is not available
            try:
                from flask import current_app
                if current_app.config.get('CACHE_TYPE') == 'null':
                    # No caching - just execute the function
                    return f(*args, **kwargs)
            except:
                # If we can't check config, skip caching
                return f(*args, **kwargs)
            
            # Generate a cache key based on function name and arguments
            key_parts = [key_prefix, f.__name__]
            for arg in args:
                if isinstance(arg, (str, int, float, bool)):
                    key_parts.append(str(arg))
            
            # Add kwargs in alphabetical order
            sorted_kwargs = sorted(kwargs.items())
            for k, v in sorted_kwargs:
                if isinstance(v, (str, int, float, bool)):
                    key_parts.append(f"{k}:{v}")
            
            cache_key = ":".join(key_parts)
            
            # Try to get result from cache
            try:
                cached_result = cache.get(cache_key)
                if cached_result:
                    return json.loads(cached_result)
            except Exception:
                # If cache read fails, continue without cache
                pass
            
            # Execute function and cache result
            result = f(*args, **kwargs)
            try:
                cache.set(cache_key, json.dumps(result), timeout=timeout)
            except (TypeError, ValueError, Exception):
                # If result can't be cached, just return it
                pass
            
            return result
        return decorated_function
    return decorator