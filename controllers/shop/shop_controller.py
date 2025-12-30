from flask import request, jsonify
from common.database import db
from models.shop.shop import Shop
from common.decorators import superadmin_required
from datetime import datetime, timezone
from sqlalchemy import desc, or_
import re
import cloudinary
import cloudinary.uploader
from http import HTTPStatus

# Allowed file extensions for image uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'svg', 'webp'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class ShopController:
    
    @staticmethod
    def get_all_shops():
        """Get all active shops"""
        try:
            shops = Shop.query.filter(
                Shop.deleted_at.is_(None),
                Shop.is_active.is_(True)
            ).order_by(Shop.name).all()
            
            return jsonify({
                'status': 'success',
                'data': [shop.serialize() for shop in shops]
            }), 200
            
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Error fetching shops: {str(e)}'
            }), 500

    @staticmethod
    def get_shop_by_id(shop_id):
        """Get a specific shop by ID"""
        try:
            shop = Shop.query.filter(
                Shop.shop_id == shop_id,
                Shop.deleted_at.is_(None)
            ).first()
            
            if not shop:
                return jsonify({
                    'status': 'error',
                    'message': 'Shop not found'
                }), 404
                
            return jsonify({
                'status': 'success',
                'data': shop.serialize()
            }), 200
            
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Error fetching shop: {str(e)}'
            }), 500

    @staticmethod
    @superadmin_required
    def create_shop():
        """Create a new shop"""
        try:
            # Handle form data
            data = {}
            data['name'] = request.form.get('name')
            data['slug'] = request.form.get('slug')
            data['description'] = request.form.get('description')
            data['is_active'] = request.form.get('is_active', 'true').lower() == 'true'
            
            # Validate required fields
            if not data['name']:
                return jsonify({
                    'status': 'error',
                    'message': 'Shop name is required'
                }), 400
            
            # Generate slug from name if not provided
            if not data['slug']:
                data['slug'] = re.sub(r'[^a-zA-Z0-9\s]', '', data['name']).replace(' ', '-').lower()
            
            # Check if shop with same name or slug exists
            existing_shop = Shop.query.filter(
                or_(Shop.name == data['name'], Shop.slug == data['slug']),
                Shop.deleted_at.is_(None)
            ).first()
            
            if existing_shop:
                return jsonify({
                    'status': 'error',
                    'message': 'Shop with this name or slug already exists'
                }), 400
            
            # Handle logo upload
            logo_url = None
            if 'logo_file' in request.files:
                file = request.files['logo_file']
                
                if file and file.filename and file.filename.strip():
                    if not allowed_file(file.filename):
                        return jsonify({
                            'status': 'error',
                            'message': f"Invalid logo file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
                        }), HTTPStatus.BAD_REQUEST
                    
                    try:
                        from services.s3_service import get_s3_service
                        from flask import current_app
                        s3_service = get_s3_service()
                        upload_result = s3_service.upload_generic_asset(file)
                        
                        logo_url = upload_result.get('url')
                        
                        if not logo_url:
                            return jsonify({
                                'status': 'error',
                                'message': 'Logo upload failed - no URL returned'
                            }), HTTPStatus.INTERNAL_SERVER_ERROR
                        
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(f"Shop logo upload failed: {str(e)}")
                        return jsonify({
                            'status': 'error',
                            'message': f"Error during logo upload: {str(e)}"
                        }), HTTPStatus.INTERNAL_SERVER_ERROR
            
            # Create new shop
            shop = Shop(
                name=data['name'],
                slug=data['slug'],
                description=data.get('description'),
                logo_url=logo_url,
                is_active=data.get('is_active', True)
            )
            
            db.session.add(shop)
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'Shop created successfully',
                'data': shop.serialize()
            }), 201
            
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Error creating shop: {str(e)}'
            }), 500

    @staticmethod
    @superadmin_required
    def update_shop(shop_id):
        """Update an existing shop"""
        try:
            shop = Shop.query.filter(
                Shop.shop_id == shop_id,
                Shop.deleted_at.is_(None)
            ).first()
            
            if not shop:
                return jsonify({
                    'status': 'error',
                    'message': 'Shop not found'
                }), 404
            
            # Handle form data
            data = {}
            if request.form.get('name'):
                data['name'] = request.form.get('name')
            if request.form.get('slug'):
                data['slug'] = request.form.get('slug')
            if request.form.get('description') is not None:
                data['description'] = request.form.get('description')
            if request.form.get('is_active') is not None:
                data['is_active'] = request.form.get('is_active', 'true').lower() == 'true'
            
            # Check if another shop with same name or slug exists
            if 'name' in data and data['name'] != shop.name:
                existing_shop = Shop.query.filter(
                    Shop.name == data['name'],
                    Shop.shop_id != shop_id,
                    Shop.deleted_at.is_(None)
                ).first()
                if existing_shop:
                    return jsonify({
                        'status': 'error',
                        'message': 'Shop with this name already exists'
                    }), 400
            
            if 'slug' in data and data['slug'] != shop.slug:
                existing_shop = Shop.query.filter(
                    Shop.slug == data['slug'],
                    Shop.shop_id != shop_id,
                    Shop.deleted_at.is_(None)
                ).first()
                if existing_shop:
                    return jsonify({
                        'status': 'error',
                        'message': 'Shop with this slug already exists'
                    }), 400
            
            # Handle logo upload
            if 'logo_file' in request.files:
                file = request.files['logo_file']
                
                if file and file.filename and file.filename.strip():
                    if not allowed_file(file.filename):
                        return jsonify({
                            'status': 'error',
                            'message': f"Invalid logo file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
                        }), HTTPStatus.BAD_REQUEST
                    
                    try:
                        from services.s3_service import get_s3_service
                        s3_service = get_s3_service()
                        upload_result = s3_service.upload_generic_asset(file)
                        
                        logo_url = upload_result.get('url')
                        
                        if not logo_url:
                            return jsonify({
                                'status': 'error',
                                'message': 'Logo upload failed - no URL returned'
                            }), HTTPStatus.INTERNAL_SERVER_ERROR
                        
                        data['logo_url'] = logo_url
                        
                    except cloudinary.exceptions.Error as e:
                        return jsonify({
                            'status': 'error',
                            'message': f"Logo upload failed: {str(e)}"
                        }), HTTPStatus.INTERNAL_SERVER_ERROR
                    except Exception as e:
                        return jsonify({
                            'status': 'error',
                            'message': f"Error during logo upload: {str(e)}"
                        }), HTTPStatus.INTERNAL_SERVER_ERROR
            
            # Update shop fields
            for field, value in data.items():
                if hasattr(shop, field):
                    setattr(shop, field, value)
                
            shop.updated_at = datetime.now(timezone.utc)
            
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'Shop updated successfully',
                'data': shop.serialize()
            }), 200
            
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Error updating shop: {str(e)}'
            }), 500

    @staticmethod
    @superadmin_required
    def delete_shop(shop_id):
        """Soft delete a shop"""
        try:
            shop = Shop.query.filter(
                Shop.shop_id == shop_id,
                Shop.deleted_at.is_(None)
            ).first()
            
            if not shop:
                return jsonify({
                    'status': 'error',
                    'message': 'Shop not found'
                }), 404
            
            # Check if shop has any active products
            if shop.products:
                active_products = [p for p in shop.products if p.deleted_at is None]
                if active_products:
                    return jsonify({
                        'status': 'error',
                        'message': 'Cannot delete shop with active products'
                    }), 400
            
            shop.deleted_at = datetime.now(timezone.utc)
            shop.is_active = False
            
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'Shop deleted successfully'
            }), 200
            
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Error deleting shop: {str(e)}'
            }), 500

    @staticmethod
    @superadmin_required
    def hard_delete_shop(shop_id):
        """Hard delete a shop (permanently remove from the database)"""
        try:
            shop = Shop.query.filter(Shop.shop_id == shop_id).first()
            if not shop:
                return jsonify({
                    'status': 'error',
                    'message': 'Shop not found'
                }), 404
            db.session.delete(shop)
            db.session.commit()
            return jsonify({
                'status': 'success',
                'message': 'Shop permanently deleted'
            }), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Error hard deleting shop: {str(e)}'
            }), 500