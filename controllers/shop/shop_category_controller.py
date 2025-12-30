from flask import request, jsonify
from common.database import db
from models.shop.shop_category import ShopCategory
from models.shop.shop import Shop
from common.decorators import superadmin_required
from datetime import datetime, timezone
from sqlalchemy import desc, or_
import re
import cloudinary.uploader
from http import HTTPStatus

class ShopCategoryController:
    
    @staticmethod
    def get_categories_by_shop(shop_id):
        """Get all categories for a specific shop"""
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
            
            categories = ShopCategory.query.filter(
                ShopCategory.shop_id == shop_id,
                ShopCategory.deleted_at.is_(None),
                ShopCategory.is_active.is_(True)
            ).order_by(ShopCategory.sort_order, ShopCategory.name).all()
            
            return jsonify({
                'status': 'success',
                'data': [category.serialize() for category in categories]
            }), 200
            
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Error fetching categories: {str(e)}'
            }), 500

    @staticmethod
    def get_category_by_id(category_id):
        """Get a specific category by ID"""
        try:
            category = ShopCategory.query.filter(
                ShopCategory.category_id == category_id,
                ShopCategory.deleted_at.is_(None)
            ).first()
            
            if not category:
                return jsonify({
                    'status': 'error',
                    'message': 'Category not found'
                }), 404
                
            return jsonify({
                'status': 'success',
                'data': category.serialize()
            }), 200
            
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Error fetching category: {str(e)}'
            }), 500

    @staticmethod
    @superadmin_required
    def create_category():
        """Create a new category for a shop"""
        try:
            # Check if request contains FormData (multipart) or JSON
            if request.content_type and 'multipart/form-data' in request.content_type:
                # Handle FormData request with file upload
                data = {}
                
                # Extract form fields
                for key in request.form:
                    value = request.form.get(key)
                    if key in ['shop_id', 'parent_id', 'sort_order']:
                        try:
                            data[key] = int(value) if value and value != 'null' else None
                        except ValueError:
                            data[key] = None
                    elif key == 'is_active':
                        data[key] = value.lower() in ['true', '1', 'yes'] if value else True
                    else:
                        data[key] = value if value and value != 'null' else None
                
                # Handle file upload
                icon_url = None
                if 'icon_file' in request.files:
                    icon_file = request.files['icon_file']
                    if icon_file and icon_file.filename:
                        # Validate file type
                        ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}
                        file_extension = icon_file.filename.rsplit('.', 1)[1].lower() if '.' in icon_file.filename else ''
                        
                        if file_extension not in ALLOWED_EXTENSIONS:
                            return jsonify({
                                'status': 'error',
                                'message': 'Invalid file type. Allowed types: PNG, JPG, JPEG, GIF, SVG, WEBP'
                            }), HTTPStatus.BAD_REQUEST
                        
                        try:
                            # Upload to S3
                            from services.s3_service import get_s3_service
                            s3_service = get_s3_service()
                            upload_result = s3_service.upload_generic_asset(icon_file)
                            icon_url = upload_result.get('url')
                            if not icon_url:
                                return jsonify({
                                    'status': 'error',
                                    'message': 'Failed to upload image - no URL returned'
                                }), HTTPStatus.INTERNAL_SERVER_ERROR
                        except Exception as upload_error:
                            from flask import current_app
                            current_app.logger.error(f"Category icon upload failed: {str(upload_error)}")
                            return jsonify({
                                'status': 'error',
                                'message': f'Failed to upload image: {str(upload_error)}'
                            }), HTTPStatus.INTERNAL_SERVER_ERROR
                
                # Set icon_url in data
                if icon_url:
                    data['icon_url'] = icon_url
                    
            else:
                # Handle JSON request (legacy support)
                data = request.get_json()
            
            # Validate required fields
            required_fields = ['shop_id', 'name']
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
            
            # Generate slug from name if not provided
            if 'slug' not in data or not data['slug']:
                data['slug'] = re.sub(r'[^a-zA-Z0-9\s]', '', data['name']).replace(' ', '-').lower()
            
            # Check if category with same name or slug exists in this shop
            existing_category = ShopCategory.query.filter(
                ShopCategory.shop_id == data['shop_id'],
                or_(ShopCategory.name == data['name'], ShopCategory.slug == data['slug']),
                ShopCategory.deleted_at.is_(None)
            ).first()
            
            if existing_category:
                return jsonify({
                    'status': 'error',
                    'message': 'Category with this name or slug already exists in this shop'
                }), HTTPStatus.BAD_REQUEST
            
            # Validate parent category if provided
            if 'parent_id' in data and data['parent_id']:
                parent_category = ShopCategory.query.filter(
                    ShopCategory.category_id == data['parent_id'],
                    ShopCategory.shop_id == data['shop_id'],
                    ShopCategory.deleted_at.is_(None)
                ).first()
                
                if not parent_category:
                    return jsonify({
                        'status': 'error',
                        'message': 'Parent category not found in this shop'
                    }), HTTPStatus.NOT_FOUND
            
            # Create new category
            category = ShopCategory(
                shop_id=data['shop_id'],
                parent_id=data.get('parent_id'),
                name=data['name'],
                slug=data['slug'],
                description=data.get('description'),
                icon_url=data.get('icon_url'),
                sort_order=data.get('sort_order', 0),
                is_active=data.get('is_active', True)
            )
            
            db.session.add(category)
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'Category created successfully',
                'data': category.serialize()
            }), HTTPStatus.CREATED
            
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Error creating category: {str(e)}'
            }), HTTPStatus.INTERNAL_SERVER_ERROR

    @staticmethod
    @superadmin_required
    def update_category(category_id):
        """Update an existing category"""
        try:
            category = ShopCategory.query.filter(
                ShopCategory.category_id == category_id,
                ShopCategory.deleted_at.is_(None)
            ).first()
            
            if not category:
                return jsonify({
                    'status': 'error',
                    'message': 'Category not found'
                }), HTTPStatus.NOT_FOUND
            
            # Check if request contains FormData (multipart) or JSON
            if request.content_type and 'multipart/form-data' in request.content_type:
                # Handle FormData request with file upload
                data = {}
                
                # Extract form fields
                for key in request.form:
                    value = request.form.get(key)
                    if key in ['parent_id', 'sort_order']:
                        try:
                            data[key] = int(value) if value and value != 'null' else None
                        except ValueError:
                            data[key] = None
                    elif key == 'is_active':
                        data[key] = value.lower() in ['true', '1', 'yes'] if value else True
                    else:
                        data[key] = value if value and value != 'null' else None
                
                # Handle file upload
                icon_url = None
                if 'icon_file' in request.files:
                    icon_file = request.files['icon_file']
                    if icon_file and icon_file.filename:
                        # Validate file type
                        ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}
                        file_extension = icon_file.filename.rsplit('.', 1)[1].lower() if '.' in icon_file.filename else ''
                        
                        if file_extension not in ALLOWED_EXTENSIONS:
                            return jsonify({
                                'status': 'error',
                                'message': 'Invalid file type. Allowed types: PNG, JPG, JPEG, GIF, SVG, WEBP'
                            }), HTTPStatus.BAD_REQUEST
                        
                        try:
                            # Upload to S3
                            from services.s3_service import get_s3_service
                            s3_service = get_s3_service()
                            upload_result = s3_service.upload_generic_asset(icon_file)
                            icon_url = upload_result.get('url')
                            data['icon_url'] = icon_url
                        except Exception as upload_error:
                            return jsonify({
                                'status': 'error',
                                'message': f'Failed to upload image: {str(upload_error)}'
                            }), HTTPStatus.INTERNAL_SERVER_ERROR
                    
            else:
                # Handle JSON request (legacy support)
                data = request.get_json()
            
            # Check if another category with same name or slug exists in the same shop
            if 'name' in data and data['name'] != category.name:
                existing_category = ShopCategory.query.filter(
                    ShopCategory.shop_id == category.shop_id,
                    ShopCategory.name == data['name'],
                    ShopCategory.category_id != category_id,
                    ShopCategory.deleted_at.is_(None)
                ).first()
                if existing_category:
                    return jsonify({
                        'status': 'error',
                        'message': 'Category with this name already exists in this shop'
                    }), HTTPStatus.BAD_REQUEST
            
            if 'slug' in data and data['slug'] != category.slug:
                existing_category = ShopCategory.query.filter(
                    ShopCategory.shop_id == category.shop_id,
                    ShopCategory.slug == data['slug'],
                    ShopCategory.category_id != category_id,
                    ShopCategory.deleted_at.is_(None)
                ).first()
                if existing_category:
                    return jsonify({
                        'status': 'error',
                        'message': 'Category with this slug already exists in this shop'
                    }), HTTPStatus.BAD_REQUEST
            
            # Validate parent category if changing
            if 'parent_id' in data and data['parent_id'] != category.parent_id:
                if data['parent_id']:
                    parent_category = ShopCategory.query.filter(
                        ShopCategory.category_id == data['parent_id'],
                        ShopCategory.shop_id == category.shop_id,
                        ShopCategory.deleted_at.is_(None)
                    ).first()
                    
                    if not parent_category:
                        return jsonify({
                            'status': 'error',
                            'message': 'Parent category not found in this shop'
                        }), HTTPStatus.NOT_FOUND
                    
                    # Check for circular reference
                    if data['parent_id'] == category_id:
                        return jsonify({
                            'status': 'error',
                            'message': 'Category cannot be its own parent'
                        }), HTTPStatus.BAD_REQUEST
            
            # Update category fields
            if 'parent_id' in data:
                category.parent_id = data['parent_id']
            if 'name' in data:
                category.name = data['name']
            if 'slug' in data:
                category.slug = data['slug']
            if 'description' in data:
                category.description = data['description']
            if 'icon_url' in data:
                category.icon_url = data['icon_url']
            if 'sort_order' in data:
                category.sort_order = data['sort_order']
            if 'is_active' in data:
                category.is_active = data['is_active']
                
            category.updated_at = datetime.now(timezone.utc)
            
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'Category updated successfully',
                'data': category.serialize()
            }), HTTPStatus.OK
            
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Error updating category: {str(e)}'
            }), HTTPStatus.INTERNAL_SERVER_ERROR

    @staticmethod
    @superadmin_required
    def delete_category(category_id):
        """Soft delete a category"""
        try:
            category = ShopCategory.query.filter(
                ShopCategory.category_id == category_id,
                ShopCategory.deleted_at.is_(None)
            ).first()
            
            if not category:
                return jsonify({
                    'status': 'error',
                    'message': 'Category not found'
                }), HTTPStatus.NOT_FOUND
            
            # Check if category has any active products
            if category.products:
                active_products = [p for p in category.products if p.deleted_at is None]
                if active_products:
                    return jsonify({
                        'status': 'error',
                        'message': 'Cannot delete category with active products'
                    }), HTTPStatus.BAD_REQUEST
            
            # Check if category has any active child categories
            if category.children:
                active_children = [c for c in category.children if c.deleted_at is None]
                if active_children:
                    return jsonify({
                        'status': 'error',
                        'message': 'Cannot delete category with active subcategories'
                    }), HTTPStatus.BAD_REQUEST
            
            category.deleted_at = datetime.now(timezone.utc)
            category.is_active = False
            
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'Category deleted successfully'
            }), HTTPStatus.OK
            
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Error deleting category: {str(e)}'
            }), HTTPStatus.INTERNAL_SERVER_ERROR
