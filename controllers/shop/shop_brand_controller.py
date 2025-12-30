from flask import request, jsonify, current_app
from common.database import db
from models.shop.shop_brand import ShopBrand
from models.shop.shop import Shop
from models.shop.shop_category import ShopCategory
from common.decorators import superadmin_required
from datetime import datetime, timezone
from sqlalchemy import desc, or_
import re
from services.s3_service import get_s3_service
from http import HTTPStatus

class ShopBrandController:
    
    @staticmethod
    def get_brands_by_shop_category(shop_id, category_id=None):
        """Get all brands for a specific shop and optionally category"""
        try:
            # Verify shop exists
            shop = Shop.query.filter(
                Shop.shop_id == shop_id,
                Shop.deleted_at.is_(None)
            ).first()
            
            if not shop:
                return jsonify({
                    'status': 'error',
                    'message': 'Shop not found'
                }), 404
            
            query = ShopBrand.query.filter(
                ShopBrand.shop_id == shop_id,
                ShopBrand.deleted_at.is_(None),
                ShopBrand.is_active.is_(True)
            )
            
            if category_id:
                # Verify category exists and belongs to the shop
                category = ShopCategory.query.filter(
                    ShopCategory.category_id == category_id,
                    ShopCategory.shop_id == shop_id,
                    ShopCategory.deleted_at.is_(None)
                ).first()
                
                if not category:
                    return jsonify({
                        'status': 'error',
                        'message': 'Category not found in this shop'
                    }), 404
                    
                query = query.filter(ShopBrand.category_id == category_id)
            
            brands = query.order_by(ShopBrand.name).all()
            
            return jsonify({
                'status': 'success',
                'data': [brand.serialize() for brand in brands]
            }), 200
            
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Error fetching brands: {str(e)}'
            }), 500

    @staticmethod
    def get_brand_by_id(brand_id):
        """Get a specific brand by ID"""
        try:
            brand = ShopBrand.query.filter(
                ShopBrand.brand_id == brand_id,
                ShopBrand.deleted_at.is_(None)
            ).first()
            
            if not brand:
                return jsonify({
                    'status': 'error',
                    'message': 'Brand not found'
                }), 404
                
            return jsonify({
                'status': 'success',
                'data': brand.serialize()
            }), 200
            
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Error fetching brand: {str(e)}'
            }), 500

    @staticmethod
    @superadmin_required
    def create_brand():
        """Create a new brand for a shop category"""
        try:
            # Check if request contains FormData (multipart) or JSON
            if request.content_type and 'multipart/form-data' in request.content_type:
                # Handle FormData request with file upload
                data = {}
                
                # Extract form fields
                for key in request.form:
                    value = request.form.get(key)
                    if key in ['shop_id', 'category_id']:
                        try:
                            data[key] = int(value) if value and value != 'null' else None
                        except ValueError:
                            data[key] = None
                    elif key == 'is_active':
                        data[key] = value.lower() in ['true', '1', 'yes'] if value else True
                    else:
                        data[key] = value if value and value != 'null' else None
                
                # Handle file upload
                logo_url = None
                if 'logo_file' in request.files:
                    logo_file = request.files['logo_file']
                    if logo_file and logo_file.filename:
                        # Validate file type
                        ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}
                        file_extension = logo_file.filename.rsplit('.', 1)[1].lower() if '.' in logo_file.filename else ''
                        
                        if file_extension not in ALLOWED_EXTENSIONS:
                            return jsonify({
                                'status': 'error',
                                'message': 'Invalid file type. Allowed types: PNG, JPG, JPEG, GIF, SVG, WEBP'
                            }), HTTPStatus.BAD_REQUEST
                        
                        try:
                            # Upload to S3
                            s3_service = get_s3_service()
                            upload_result = s3_service.upload_generic_asset(logo_file)
                            logo_url = upload_result.get('url')
                            if not logo_url:
                                return jsonify({
                                    'status': 'error',
                                    'message': 'Failed to upload image - no URL returned'
                                }), HTTPStatus.INTERNAL_SERVER_ERROR
                        except Exception as upload_error:
                            current_app.logger.error(f"Brand logo upload failed: {str(upload_error)}")
                            return jsonify({
                                'status': 'error',
                                'message': f'Failed to upload image: {str(upload_error)}'
                            }), HTTPStatus.INTERNAL_SERVER_ERROR
                
                # Set logo_url in data
                if logo_url:
                    data['logo_url'] = logo_url
                    
            else:
                # Handle JSON request (legacy support)
                data = request.get_json()
            
            # Validate required fields
            required_fields = ['shop_id', 'category_id', 'name']
            for field in required_fields:
                if field not in data or not data[field]:
                    return jsonify({
                        'status': 'error',
                        'message': f'{field} is required'
                    }), HTTPStatus.BAD_REQUEST
            
            # Verify shop exists
            shop = Shop.query.filter(
                Shop.shop_id == data['shop_id'],
                Shop.deleted_at.is_(None)
            ).first()
            
            if not shop:
                return jsonify({
                    'status': 'error',
                    'message': 'Shop not found'
                }), HTTPStatus.NOT_FOUND
            
            # Verify category exists and belongs to the shop
            category = ShopCategory.query.filter(
                ShopCategory.category_id == data['category_id'],
                ShopCategory.shop_id == data['shop_id'],
                ShopCategory.deleted_at.is_(None)
            ).first()
            
            if not category:
                return jsonify({
                    'status': 'error',
                    'message': 'Category not found in this shop'
                }), HTTPStatus.NOT_FOUND
            
            # Generate slug from name if not provided
            if 'slug' not in data or not data['slug']:
                data['slug'] = re.sub(r'[^a-zA-Z0-9\s]', '', data['name']).replace(' ', '-').lower()
            
            # Check if brand with same name or slug exists in this shop-category
            existing_brand = ShopBrand.query.filter(
                ShopBrand.shop_id == data['shop_id'],
                ShopBrand.category_id == data['category_id'],
                or_(ShopBrand.name == data['name'], ShopBrand.slug == data['slug']),
                ShopBrand.deleted_at.is_(None)
            ).first()
            
            if existing_brand:
                return jsonify({
                    'status': 'error',
                    'message': 'Brand with this name or slug already exists in this shop-category'
                }), HTTPStatus.BAD_REQUEST
            
            # Create new brand
            brand = ShopBrand(
                shop_id=data['shop_id'],
                category_id=data['category_id'],
                name=data['name'],
                slug=data['slug'],
                description=data.get('description'),
                logo_url=data.get('logo_url'),
                is_active=data.get('is_active', True)
            )
            
            db.session.add(brand)
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'Brand created successfully',
                'data': brand.serialize()
            }), HTTPStatus.CREATED
            
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Error creating brand: {str(e)}'
            }), HTTPStatus.INTERNAL_SERVER_ERROR

    @staticmethod
    @superadmin_required
    def update_brand(brand_id):
        """Update an existing brand"""
        try:
            brand = ShopBrand.query.filter(
                ShopBrand.brand_id == brand_id,
                ShopBrand.deleted_at.is_(None)
            ).first()
            
            if not brand:
                return jsonify({
                    'status': 'error',
                    'message': 'Brand not found'
                }), HTTPStatus.NOT_FOUND
            
            # Check if request contains FormData (multipart) or JSON
            if request.content_type and 'multipart/form-data' in request.content_type:
                # Handle FormData request with file upload
                data = {}
                
                # Extract form fields
                for key in request.form:
                    value = request.form.get(key)
                    if key in ['category_id']:
                        try:
                            data[key] = int(value) if value and value != 'null' else None
                        except ValueError:
                            data[key] = None
                    elif key == 'is_active':
                        data[key] = value.lower() in ['true', '1', 'yes'] if value else True
                    else:
                        data[key] = value if value and value != 'null' else None
                
                # Handle file upload
                logo_url = None
                if 'logo_file' in request.files:
                    logo_file = request.files['logo_file']
                    if logo_file and logo_file.filename:
                        # Validate file type
                        ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}
                        file_extension = logo_file.filename.rsplit('.', 1)[1].lower() if '.' in logo_file.filename else ''
                        
                        if file_extension not in ALLOWED_EXTENSIONS:
                            return jsonify({
                                'status': 'error',
                                'message': 'Invalid file type. Allowed types: PNG, JPG, JPEG, GIF, SVG, WEBP'
                            }), HTTPStatus.BAD_REQUEST
                        
                        try:
                            # Upload to S3
                            from services.s3_service import get_s3_service
                            s3_service = get_s3_service()
                            upload_result = s3_service.upload_generic_asset(logo_file)
                            logo_url = upload_result.get('url')
                            data['logo_url'] = logo_url
                        except Exception as upload_error:
                            return jsonify({
                                'status': 'error',
                                'message': f'Failed to upload image: {str(upload_error)}'
                            }), HTTPStatus.INTERNAL_SERVER_ERROR
                    
            else:
                # Handle JSON request (legacy support)
                data = request.get_json()
            
            # Validate category change if provided
            if 'category_id' in data and data['category_id'] != brand.category_id:
                category = ShopCategory.query.filter(
                    ShopCategory.category_id == data['category_id'],
                    ShopCategory.shop_id == brand.shop_id,
                    ShopCategory.deleted_at.is_(None)
                ).first()
                
                if not category:
                    return jsonify({
                        'status': 'error',
                        'message': 'Category not found in this shop'
                    }), HTTPStatus.NOT_FOUND
            
            # Check if another brand with same name or slug exists in the same shop-category
            category_id = data.get('category_id', brand.category_id)
            
            if 'name' in data and data['name'] != brand.name:
                existing_brand = ShopBrand.query.filter(
                    ShopBrand.shop_id == brand.shop_id,
                    ShopBrand.category_id == category_id,
                    ShopBrand.name == data['name'],
                    ShopBrand.brand_id != brand_id,
                    ShopBrand.deleted_at.is_(None)
                ).first()
                if existing_brand:
                    return jsonify({
                        'status': 'error',
                        'message': 'Brand with this name already exists in this shop-category'
                    }), HTTPStatus.BAD_REQUEST
            
            if 'slug' in data and data['slug'] != brand.slug:
                existing_brand = ShopBrand.query.filter(
                    ShopBrand.shop_id == brand.shop_id,
                    ShopBrand.category_id == category_id,
                    ShopBrand.slug == data['slug'],
                    ShopBrand.brand_id != brand_id,
                    ShopBrand.deleted_at.is_(None)
                ).first()
                if existing_brand:
                    return jsonify({
                        'status': 'error',
                        'message': 'Brand with this slug already exists in this shop-category'
                    }), HTTPStatus.BAD_REQUEST
            
            # Update brand fields
            if 'category_id' in data:
                brand.category_id = data['category_id']
            if 'name' in data:
                brand.name = data['name']
            if 'slug' in data:
                brand.slug = data['slug']
            if 'description' in data:
                brand.description = data['description']
            if 'logo_url' in data:
                brand.logo_url = data['logo_url']
            if 'is_active' in data:
                brand.is_active = data['is_active']
                
            brand.updated_at = datetime.now(timezone.utc)
            
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'Brand updated successfully',
                'data': brand.serialize()
            }), HTTPStatus.OK
            
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Error updating brand: {str(e)}'
            }), HTTPStatus.INTERNAL_SERVER_ERROR

    @staticmethod
    @superadmin_required
    def delete_brand(brand_id):
        """Soft delete a brand"""
        try:
            brand = ShopBrand.query.filter(
                ShopBrand.brand_id == brand_id,
                ShopBrand.deleted_at.is_(None)
            ).first()
            
            if not brand:
                return jsonify({
                    'status': 'error',
                    'message': 'Brand not found'
                }), HTTPStatus.NOT_FOUND
            
            # Check if brand has any active products
            if brand.products:
                active_products = [p for p in brand.products if p.deleted_at is None]
                if active_products:
                    return jsonify({
                        'status': 'error',
                        'message': 'Cannot delete brand with active products'
                    }), HTTPStatus.BAD_REQUEST
            
            brand.deleted_at = datetime.now(timezone.utc)
            brand.is_active = False
            
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'Brand deleted successfully'
            }), HTTPStatus.OK
            
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Error deleting brand: {str(e)}'
            }), HTTPStatus.INTERNAL_SERVER_ERROR
