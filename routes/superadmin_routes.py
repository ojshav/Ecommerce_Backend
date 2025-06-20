from flask import Blueprint, request, jsonify, current_app
from auth.utils import super_admin_role_required
from flask_jwt_extended import get_jwt_identity
import cloudinary
import cloudinary.uploader
from common.database import db
from marshmallow import ValidationError
from models.brand import Brand
from models.category import Category
from models.attribute import Attribute
from models.category_attribute import CategoryAttribute
from sqlalchemy.exc import IntegrityError
from http import HTTPStatus
from datetime import datetime, timezone 
import re
from flask_cors import cross_origin

from controllers.superadmin import newsletter_controller
from controllers.superadmin.category_controller import CategoryController
from controllers.superadmin.attribute_controller import AttributeController
from controllers.superadmin.brand_controller import BrandController
from controllers.superadmin.brand_request_controller import BrandRequestController
from controllers.superadmin.promotion_controller import PromotionController
from controllers.superadmin.review_controller import ReviewController
from controllers.superadmin.category_attribute_controller import CategoryAttributeController 
from controllers.superadmin.homepage_controller import HomepageController
from controllers.superadmin.product_monitoring_controller import ProductMonitoringController
from controllers.superadmin.product_controller import ProductController
from controllers.superadmin.carousel_controller import CarouselController

from controllers.superadmin.system_monitoring_controller import SystemMonitoringController

from controllers.superadmin.gst_controller import GSTManagementController
from schemas.superadmin_gst_schemas import CreateGSTRuleSchema, UpdateGSTRuleSchema 

from werkzeug.exceptions import NotFound, BadRequest



from controllers.superadmin.merchant_transaction_controller import (
    list_all_transactions, get_transaction_by_id, mark_as_paid
)


superadmin_bp = Blueprint('superadmin_bp', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}  # removed extension type .svg and .gif 

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ── CATEGORY ─────────────────────────────────────────────────────────────────────
@superadmin_bp.route('/categories', methods=['GET'])
@super_admin_role_required
def list_categories():
    """
    Get a list of all categories
    ---
    tags:
      - Categories
    security:
      - Bearer: []
    responses:
      200:
        description: List of categories retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
              name:
                type: string
              slug:
                type: string
              parent_id:
                type: integer
                nullable: true
              icon_url:
                type: string
                nullable: true
              created_at:
                type: string
                format: date-time
              updated_at:
                type: string
                format: date-time
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      500:
        description: Internal server error
    """
    try:
        cats = CategoryController.list_all()
        return jsonify([c.serialize() for c in cats]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error listing categories: {e}")
        return jsonify({'message': 'Failed to retrieve categories.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/categories', methods=['POST'])
@super_admin_role_required
def create_category():
    """
    Create a new category.
    ---
    tags:
      - Categories
    security:
      - Bearer: []
    consumes:
      - multipart/form-data
    parameters:
      - name: name
        in: formData
        type: string
        required: true
        description: "Name of the category."
      - name: slug
        in: formData
        type: string
        required: true
        description: "URL-friendly slug for the category."
      - name: parent_id
        in: formData
        type: integer
        required: false
        description: "ID of the parent category (optional)."
      - name: icon_url
        in: formData
        type: string
        required: false
        description: "URL of the category icon (optional)."
      - name: icon_file
        in: formData
        type: file
        required: false
        description: "Icon file to upload for the category (optional)."
    responses:
      201:
        description: "Category created successfully."
        schema:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
            slug:
              type: string
            parent_id:
              type: integer
              nullable: true
            icon_url:
              type: string
              nullable: true
            created_at:
              type: string
              format: date-time
            updated_at:
              type: string
              format: date-time
      400:
        description: "Bad request (missing or invalid fields)."
      401:
        description: "Unauthorized - Invalid or missing token."
      403:
        description: "Forbidden - User does not have super admin role."
      409:
        description: "Conflict - Category with this slug already exists."
      500:
        description: "Internal server error."
    """    
    name = request.form.get('name')
    slug = request.form.get('slug')

    if not name or not name.strip():
        return jsonify({'message': 'Name is required'}), HTTPStatus.BAD_REQUEST
    if not slug or not slug.strip():
        return jsonify({'message': 'Slug is required'}), HTTPStatus.BAD_REQUEST

    category_data = {
        'name': name.strip(),
        'slug': slug.strip()
    }

    
    raw_parent_id = request.form.get('parent_id')
    if raw_parent_id and raw_parent_id.strip():
        try:
            category_data['parent_id'] = int(raw_parent_id)
        except ValueError:
            return jsonify({'message': 'Invalid parent_id format. Must be an integer.'}), HTTPStatus.BAD_REQUEST
    else:
        category_data['parent_id'] = None

    
    category_data['icon_url'] = request.form.get('icon_url', None)
    if category_data['icon_url'] == '':
        category_data['icon_url'] = None


    
    icon_url_from_cloudinary = None
    if 'icon_file' in request.files:
        file = request.files['icon_file']
        
        
        if file and file.filename and file.filename.strip() != '':
            if not allowed_file(file.filename):
                return jsonify({'message': f"Invalid icon file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"}), HTTPStatus.BAD_REQUEST
            
            try:
                
                upload_result = cloudinary.uploader.upload(
                    file,
                    folder="category_icons",  
                    resource_type="image"
                )
                
                icon_url_from_cloudinary = upload_result.get('secure_url')
                
                if not icon_url_from_cloudinary:
                   
                    current_app.logger.error("Cloudinary upload succeeded but no secure_url was returned.")
                    return jsonify({'message': 'Cloudinary upload succeeded but did not return a URL.'}), HTTPStatus.INTERNAL_SERVER_ERROR
                
                
                category_data['icon_url'] = icon_url_from_cloudinary

            except cloudinary.exceptions.Error as e:
                current_app.logger.error(f"Cloudinary upload failed: {e}")
                return jsonify({'message': f"Cloudinary icon upload failed: {str(e)}"}), HTTPStatus.INTERNAL_SERVER_ERROR
            except Exception as e: 
                current_app.logger.error(f"An error occurred during icon file upload: {e}")
                return jsonify({'message': f"An error occurred during icon file upload: {str(e)}"}), HTTPStatus.INTERNAL_SERVER_ERROR
        elif file.filename == '' and 'icon_file' in request.files:
           
            pass

   
    try:
        cat = CategoryController.create(category_data) 
        return jsonify(cat.serialize()), HTTPStatus.CREATED
    except IntegrityError as e:
        db.session.rollback()
       
        current_app.logger.error(f"IntegrityError creating category: {e}")
        if "unique constraint" in str(e.orig).lower() or (hasattr(e.orig, 'pgcode') and e.orig.pgcode == '23505'):
             return jsonify({'message': 'A category with this slug already exists.'}), HTTPStatus.CONFLICT
        return jsonify({'message': 'Failed to create category due to a data conflict (e.g., duplicate slug or invalid parent_id).'}), HTTPStatus.CONFLICT
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating category: {e}")
        return jsonify({'message': f'Could not create category: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR


@superadmin_bp.route('/categories/<int:cid>', methods=['PUT'])
@super_admin_role_required
def update_category(cid):
    """
    Update an existing category.
    Supports both JSON and multipart/form-data for updating fields and icon.
    ---
    tags:
      - Categories
    security:
      - Bearer: []
    consumes:
      - application/json
      - multipart/form-data
    parameters:
      - name: cid
        in: path
        type: integer
        required: true
        description: "ID of the category to update."
      - name: name
        in: formData
        type: string
        required: false
        description: "New name for the category."
      - name: slug
        in: formData
        type: string
        required: false
        description: "New slug for the category."
      - name: parent_id
        in: formData
        type: integer
        required: false
        description: "ID of the new parent category (optional)."
      - name: icon_file
        in: formData
        type: file
        required: false
        description: "New icon file for the category (optional)."
    requestBody:
      required: false
      content:
        application/json:
          schema:
            type: object
            properties:
              name:
                type: string
                description: "New name for the category."
              slug:
                type: string
                description: "New slug for the category."
              parent_id:
                type: integer
                description: "ID of the new parent category (optional)."
    responses:
      200:
        description: "Category updated successfully."
        schema:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
            slug:
              type: string
            parent_id:
              type: integer
              nullable: true
            icon_url:
              type: string
              nullable: true
            created_at:
              type: string
              format: date-time
            updated_at:
              type: string
              format: date-time
      400:
        description: "Bad request (missing or invalid fields)."
      401:
        description: "Unauthorized - Invalid or missing token."
      403:
        description: "Forbidden - User does not have super admin role."
      404:
        description: "Category not found."
      409:
        description: "Conflict - Category with this slug already exists."
      415:
        description: "Unsupported Media Type."
      500:
        description: "Internal server error."
    """
    # Determine content type
    content_type = request.content_type or ''
    update_data = {}

    # --- 1) JSON path ---
    if content_type.startswith('application/json'):
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'message': 'No JSON body provided'}), HTTPStatus.BAD_REQUEST
        update_data = data

    # --- 2) multipart/form-data path ---
    elif content_type.startswith('multipart/form-data'):
        # text fields
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip()
        if name:
            update_data['name'] = name
        if slug:
            update_data['slug'] = slug

        # Handle parent_id
        parent_id = request.form.get('parent_id')
        if parent_id is not None:
            if parent_id == '':
                update_data['parent_id'] = None
            else:
                try:
                    update_data['parent_id'] = int(parent_id)
                except (ValueError, TypeError):
                    return jsonify({'message': 'Invalid parent_id format. Must be an integer or null.'}), HTTPStatus.BAD_REQUEST

        # file field
        file = request.files.get('icon_file')
        if file and file.filename:
            if not allowed_file(file.filename):
                return jsonify({'message': f'Invalid icon file type. Allowed: {ALLOWED_EXTENSIONS}'}), HTTPStatus.BAD_REQUEST

            try:
                upload_result = cloudinary.uploader.upload(
                    file,
                    folder="category_icons",
                    public_id=f"category_{cid}_{file.filename.rsplit('.', 1)[0]}",
                    overwrite=True,
                    resource_type="image"
                )
                new_url = upload_result.get('secure_url')
                if not new_url:
                    raise ValueError("No secure_url from Cloudinary")
                update_data['icon_url'] = new_url
            except Exception as e:
                current_app.logger.error(f"Cloudinary upload failed in update: {e}")
                return jsonify({'message': f'Icon upload failed: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR
    else:
        return jsonify({'message': 'Unsupported Content-Type. Use JSON or multipart/form-data.'}), HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    # must have at least one field to update
    if not update_data:
        return jsonify({'message': 'No updatable fields provided.'}), HTTPStatus.BAD_REQUEST

    try:
        cat = CategoryController.update(cid, update_data)
        return jsonify(cat.serialize()), HTTPStatus.OK
    except IntegrityError as e: 
        db.session.rollback()
        current_app.logger.error(f"IntegrityError updating category {cid}: {e}")
        if "unique constraint" in str(e.orig).lower() or (hasattr(e.orig, 'pgcode') and e.orig.pgcode == '23505'):
            return jsonify({'message': 'Update failed. A category with the new slug might already exist.'}), HTTPStatus.CONFLICT
        return jsonify({'message': 'Update failed due to a data conflict (e.g., duplicate slug or invalid parent_id).'}), HTTPStatus.CONFLICT
    except FileNotFoundError: 
        return jsonify({'message': 'Category not found'}), HTTPStatus.NOT_FOUND
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating category {cid}: {e}")
        return jsonify({'message': f'Could not update category: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR


@superadmin_bp.route('/categories/<int:cid>', methods=['DELETE'])
@super_admin_role_required
def delete_category(cid):
    """
    Delete a category
    ---
    tags:
      - Categories
    security:
      - Bearer: []
    parameters:
      - name: cid
        in: path
        type: integer
        required: true
        description: ID of the category to delete
    responses:
      200:
        description: Category deleted successfully
        schema:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
            slug:
              type: string
            parent_id:
              type: integer
              nullable: true
            icon_url:
              type: string
              nullable: true
            created_at:
              type: string
              format: date-time
            updated_at:
              type: string
              format: date-time
            deleted_at:
              type: string
              format: date-time
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Category not found
      500:
        description: Internal server error
    """
    try:
        cat = CategoryController.delete(cid)
        return jsonify(cat.serialize()), HTTPStatus.OK
    except FileNotFoundError: 
        return jsonify({'message': 'Category not found'}), HTTPStatus.NOT_FOUND
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting category {cid}: {e}")
        return jsonify({'message': f'Could not delete category: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR


@superadmin_bp.route('/categories/<int:cid>/upload_icon', methods=['POST'])
@super_admin_role_required
def upload_category_icon(cid):
    """
    Upload or update the icon for a specific category.
    ---
    tags:
      - Categories
    security:
      - Bearer: []
    consumes:
      - multipart/form-data
    parameters:
      - name: cid
        in: path
        type: integer
        required: true
        description: "ID of the category to upload the icon for."
      - name: file
        in: formData
        type: file
        required: true
        description: "Icon image file to upload (png, jpg, jpeg, webp)."
    responses:
      200:
        description: "Icon uploaded and category updated successfully."
        schema:
          type: object
          properties:
            message:
              type: string
            category:
              type: object
      400:
        description: "Bad request (missing file or invalid type)."
      401:
        description: "Unauthorized - Invalid or missing token."
      403:
        description: "Forbidden - User does not have super admin role."
      404:
        description: "Category not found."
      500:
        description: "Internal server error."
    """    
    try:
        
        category = Category.query.filter_by(id=cid).first()
        if not category:
            return jsonify({'message': 'Category not found or has been deleted'}), HTTPStatus.NOT_FOUND

        if 'file' not in request.files:
            return jsonify({'message': 'No file part in the request'}), HTTPStatus.BAD_REQUEST
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'message': 'No selected file'}), HTTPStatus.BAD_REQUEST

        if not allowed_file(file.filename):
            return jsonify({'message': f"Invalid file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"}), HTTPStatus.BAD_REQUEST

        public_id_for_cloudinary = f"category_icons/category_{cid}_{file.filename.rsplit('.', 1)[0]}"

        upload_result = cloudinary.uploader.upload(
            file,
            folder="category_icons",
            public_id=public_id_for_cloudinary,
            overwrite=True,
            resource_type="image"
        )
        
        icon_url = upload_result.get('secure_url')
        if not icon_url:
            current_app.logger.error(f"Cloudinary upload for category {cid} succeeded but no secure_url.")
            return jsonify({'message': 'Cloudinary did not return a URL'}), HTTPStatus.INTERNAL_SERVER_ERROR

        category.icon_url = icon_url
       
        db.session.commit()

        return jsonify({
            'message': 'Icon uploaded and category updated successfully',
            'category': category.serialize()
        }), HTTPStatus.OK

    except cloudinary.exceptions.Error as e:
        current_app.logger.error(f"Cloudinary upload failed for category {cid}: {e}")
        return jsonify({'message': f"Cloudinary upload failed: {str(e)}"}), HTTPStatus.INTERNAL_SERVER_ERROR
   
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error uploading icon for category {cid}: {e}")
        return jsonify({'message': f"An unexpected error occurred: {str(e)}"}), HTTPStatus.INTERNAL_SERVER_ERROR



# ── BRAND REQUESTS ────────────────────────────────────────────────────────────────
@superadmin_bp.route('/brand-requests', methods=['GET'])
@super_admin_role_required
def list_brand_requests():
    """
    Get a list of all pending brand requests
    ---
    tags:
      - Brand Requests
    security:
      - Bearer: []
    responses:
      200:
        description: List of pending brand requests retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
              brand_name:
                type: string
              slug:
                type: string
              description:
                type: string
              website_url:
                type: string
                nullable: true
              status:
                type: string
                enum: [pending, approved, rejected]
              requested_by:
                type: integer
              requested_at:
                type: string
                format: date-time
              approved_by:
                type: integer
                nullable: true
              approved_at:
                type: string
                format: date-time
                nullable: true
              rejection_notes:
                type: string
                nullable: true
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      500:
        description: Internal server error
    """
    try:
        requests = BrandRequestController.list_pending()
        return jsonify([r.serialize() for r in requests]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error listing brand requests: {e}")
        return jsonify({'message': 'Failed to retrieve brand requests.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/brand-requests/<int:rid>/approve', methods=['POST'])
@super_admin_role_required
def approve_brand_request(rid):
    """
    Approve a pending brand request.
    Optionally upload and set a brand icon.
    ---
    tags:
      - Brand Requests
    security:
      - Bearer: []
    consumes:
      - multipart/form-data
    parameters:
      - name: rid
        in: path
        type: integer
        required: true
        description: "ID of the brand request to approve."
      - name: brand_icon_file
        in: formData
        type: file
        required: false
        description: "Optional icon file for the brand."
    responses:
      201:
        description: "Brand request approved and brand created successfully."
        schema:
          type: object
          properties:
            id:
              type: integer
            brand_name:
              type: string
            slug:
              type: string
            description:
              type: string
            website_url:
              type: string
              nullable: true
            status:
              type: string
              enum: [approved]
            approved_by:
              type: integer
            approved_at:
              type: string
              format: date-time
            icon_url:
              type: string
              nullable: true
      400:
        description: "Bad request (invalid data or missing required fields)."
      401:
        description: "Unauthorized - Invalid or missing token."
      403:
        description: "Forbidden - User does not have super admin role."
      404:
        description: "Brand request not found."
      409:
        description: "Conflict - Brand with this name or slug already exists."
      500:
        description: "Internal server error."
    """    
    user_id = get_jwt_identity()
    icon_url_from_cloudinary = None

    if 'brand_icon_file' in request.files:
        file = request.files['brand_icon_file']
        if file and file.filename and file.filename.strip() != '':
            if not allowed_file(file.filename):
                return jsonify({'message': f"Invalid brand icon file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"}), HTTPStatus.BAD_REQUEST
            try:
                upload_result = cloudinary.uploader.upload(
                    file,
                    folder="brand_icons",
                    resource_type="image"
                )
                icon_url_from_cloudinary = upload_result.get('secure_url')
                if not icon_url_from_cloudinary:
                    current_app.logger.error(f"Cloudinary upload for brand request {rid} succeeded but no secure_url.")
                    return jsonify({'message': 'Cloudinary upload succeeded but did not return a URL.'}), HTTPStatus.INTERNAL_SERVER_ERROR
            except cloudinary.exceptions.Error as e:
                current_app.logger.error(f"Cloudinary upload failed for brand request {rid}: {e}")
                return jsonify({'message': f"Cloudinary icon upload failed: {str(e)}"}), HTTPStatus.INTERNAL_SERVER_ERROR
            except Exception as e:
                current_app.logger.error(f"Error during brand icon file upload for request {rid}: {e}")
                return jsonify({'message': f"An error occurred during brand icon file upload: {str(e)}"}), HTTPStatus.INTERNAL_SERVER_ERROR

    try:
        brand = BrandRequestController.approve(rid, user_id, icon_url=icon_url_from_cloudinary)
        return jsonify(brand.serialize()), HTTPStatus.CREATED
    except FileNotFoundError as e:
        return jsonify({'message': str(e)}), HTTPStatus.NOT_FOUND
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except IntegrityError as e:
        db.session.rollback()
        current_app.logger.error(f"Data conflict approving brand request {rid}: {e}")
        return jsonify({'message': 'A brand with this name or slug already exists.'}), HTTPStatus.CONFLICT
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving brand request {rid}: {e}")
        return jsonify({'message': f'Could not approve brand request: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/brand-requests/<int:rid>/reject', methods=['POST'])
@super_admin_role_required
def reject_brand_request(rid):
    """
    Reject a brand request
    ---
    tags:
      - Brand Requests
    security:
      - Bearer: []
    parameters:
      - name: rid
        in: path
        type: integer
        required: true
        description: ID of the brand request to reject
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - notes
            properties:
              notes:
                type: string
                description: Reason for rejecting the brand request
    responses:
      200:
        description: Brand request rejected successfully
        schema:
          type: object
          properties:
            id:
              type: integer
            brand_name:
              type: string
            slug:
              type: string
            description:
              type: string
            website_url:
              type: string
              nullable: true
            status:
              type: string
              enum: [rejected]
            requested_by:
              type: integer
            requested_at:
              type: string
              format: date-time
            rejected_by:
              type: integer
            rejected_at:
              type: string
              format: date-time
            rejection_notes:
              type: string
      400:
        description: Bad request - Missing rejection notes
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Brand request not found
      500:
        description: Internal server error
    """
    user_id = get_jwt_identity()
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Rejection notes are required in JSON body.'}), HTTPStatus.BAD_REQUEST
    
    notes = data.get('notes')
    if notes is None:
        return jsonify({'message': 'Rejection notes (`notes` field) are required.'}), HTTPStatus.BAD_REQUEST

    try:
        request = BrandRequestController.reject(rid, user_id, notes)
        return jsonify(request.serialize()), HTTPStatus.OK
    except FileNotFoundError as e:
        return jsonify({'message': str(e)}), HTTPStatus.NOT_FOUND
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error rejecting brand request {rid}: {e}")
        return jsonify({'message': f'Could not reject brand request: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR

# ── BRANDS ────────────────────────────────────────────────────────────────────────
@superadmin_bp.route('/brands', methods=['GET'])
@super_admin_role_required
def list_brands():
    """
    Get a list of all brands
    ---
    tags:
      - Brands
    security:
      - Bearer: []
    responses:
      200:
        description: List of brands retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              brand_id:
                type: integer
              name:
                type: string
              slug:
                type: string
              description:
                type: string
              website_url:
                type: string
                nullable: true
              icon_url:
                type: string
                nullable: true
              status:
                type: string
                enum: [active, inactive]
              approved_by:
                type: integer
              approved_at:
                type: string
                format: date-time
              created_at:
                type: string
                format: date-time
              updated_at:
                type: string
                format: date-time
              deleted_at:
                type: string
                format: date-time
                nullable: true
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      500:
        description: Internal server error
    """
    try:
        brands_list = BrandController.list_all()
        
        return jsonify([b.serialize() for b in brands_list]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error listing brands: {e}")
        return jsonify({'message': 'Failed to retrieve brands.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/brands', methods=['POST'])
@super_admin_role_required
def create_brand_directly():
    """
    Create a new brand directly (without a brand request).
    ---
    tags:
      - Brands
    security:
      - Bearer: []
    consumes:
      - multipart/form-data
    parameters:
      - name: name
        in: formData
        type: string
        required: true
        description: "Name of the brand."
      - name: slug
        in: formData
        type: string
        required: false
        description: "URL-friendly slug for the brand (optional, auto-generated if not provided)."
      - name: icon_url
        in: formData
        type: string
        required: false
        description: "URL of the brand icon (optional)."
      - name: icon_file
        in: formData
        type: file
        required: false
        description: "Icon file to upload for the brand (optional)."
    responses:
      201:
        description: "Brand created successfully."
        schema:
          type: object
          properties:
            brand_id:
              type: integer
            name:
              type: string
            slug:
              type: string
            icon_url:
              type: string
              nullable: true
            approved_by:
              type: integer
            approved_at:
              type: string
              format: date-time
      400:
        description: "Bad request (missing or invalid fields)."
      401:
        description: "Unauthorized - Invalid or missing token."
      403:
        description: "Forbidden - User does not have super admin role."
      409:
        description: "Conflict - Brand with this name or slug already exists."
      500:
        description: "Internal server error."
    """
    name = request.form.get('name', '').strip()
    slug_provided = request.form.get('slug', '').strip()

    if not name:
        return jsonify({'message': 'Brand name is required'}), HTTPStatus.BAD_REQUEST

    slug = ""
    if slug_provided:
        slug = slug_provided
        if Brand.query.filter_by(slug=slug, deleted_at=None).first():
            return jsonify({'message': f"A brand with the provided slug '{slug}' already exists."}), HTTPStatus.CONFLICT
    else:
        base_slug = name.lower()
        base_slug = re.sub(r'\s+', '-', base_slug)
        base_slug = re.sub(r'[^a-z0-9-]', '', base_slug)
        base_slug = re.sub(r'-+', '-', base_slug).strip('-')
        if not base_slug:
            temp_brand_check = Brand.query.order_by(Brand.brand_id.desc()).first()
            next_id = (temp_brand_check.brand_id + 1) if temp_brand_check else 1
            base_slug = f"brand-{next_id}"

        temp_slug = base_slug
        counter = 1
        while Brand.query.filter_by(slug=temp_slug, deleted_at=None).first():
            temp_slug = f"{base_slug}-{counter}"
            counter += 1
            if counter > 100:
                 current_app.logger.error(f"Could not generate a unique slug for direct brand creation: {name}")
                 return jsonify({'message': f"Could not generate a unique slug for brand: {name}. Try providing a unique slug manually."}), HTTPStatus.INTERNAL_SERVER_ERROR
        slug = temp_slug
    
    brand_data = {
        'name': name,
        'slug': slug,
        'approved_by': get_jwt_identity(),
        'approved_at': datetime.now(timezone.utc),
        'icon_url': None 
    }

    icon_url_from_text = request.form.get('icon_url', None)
    if icon_url_from_text and icon_url_from_text.strip():
        brand_data['icon_url'] = icon_url_from_text.strip()

    if 'icon_file' in request.files:
        file = request.files['icon_file']
        if file and file.filename and file.filename.strip() != '':
            if not allowed_file(file.filename):
                return jsonify({'message': f"Invalid icon file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"}), HTTPStatus.BAD_REQUEST
            try:
                upload_result = cloudinary.uploader.upload(file, folder="brand_icons", resource_type="image")
                icon_url_from_cloudinary = upload_result.get('secure_url')
                if not icon_url_from_cloudinary:
                    current_app.logger.error("Cloudinary brand icon upload (direct create) succeeded but no secure_url.")
                    return jsonify({'message': 'Cloudinary upload did not return a URL.'}), HTTPStatus.INTERNAL_SERVER_ERROR
                brand_data['icon_url'] = icon_url_from_cloudinary 
            except cloudinary.exceptions.Error as e:
                current_app.logger.error(f"Cloudinary icon upload failed (direct brand create): {e}")
                return jsonify({'message': f"Cloudinary icon upload failed: {str(e)}"}), HTTPStatus.INTERNAL_SERVER_ERROR
            except Exception as e:
                current_app.logger.error(f"An error occurred during icon file upload (direct brand create): {e}")
                return jsonify({'message': f"An error occurred during icon file upload: {str(e)}"}), HTTPStatus.INTERNAL_SERVER_ERROR
    
    try:
        new_brand = BrandController.create(brand_data)
        return jsonify(new_brand.serialize()), HTTPStatus.CREATED
    except IntegrityError as e:
        db.session.rollback()
        current_app.logger.error(f"IntegrityError creating brand directly: {e}")
        if "unique constraint" in str(e.orig).lower() or (hasattr(e.orig, 'pgcode') and e.orig.pgcode == '23505'):
             return jsonify({'message': f"A brand with this name or slug already exists: {name} / {slug}"}), HTTPStatus.CONFLICT
        return jsonify({'message': 'Failed to create brand due to a data conflict.'}), HTTPStatus.CONFLICT
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating brand directly: {e}")
        return jsonify({'message': f'Could not create brand: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/brands/<int:bid>/upload_icon', methods=['POST'])
@super_admin_role_required
def upload_brand_icon(bid):
    """
    Upload or update the icon for a specific brand.
    ---
    tags:
      - Brands
    security:
      - Bearer: []
    consumes:
      - multipart/form-data
    parameters:
      - name: bid
        in: path
        type: integer
        required: true
        description: "ID of the brand to upload the icon for."
      - name: file
        in: formData
        type: file
        required: true
        description: "Icon image file to upload (png, jpg, jpeg, webp)."
    responses:
      200:
        description: "Brand icon uploaded and updated successfully."
        schema:
          type: object
          properties:
            message:
              type: string
            brand:
              type: object
      400:
        description: "Bad request (missing file or invalid type)."
      401:
        description: "Unauthorized - Invalid or missing token."
      403:
        description: "Forbidden - User does not have super admin role."
      404:
        description: "Brand not found."
      500:
        description: "Internal server error."
    """    
    try:
        
        brand = Brand.query.filter_by(brand_id=bid).first()
        if not brand:
            return jsonify({'message': 'Brand not found or has been deleted'}), HTTPStatus.NOT_FOUND

        if 'file' not in request.files:
            return jsonify({'message': 'No file part in the request'}), HTTPStatus.BAD_REQUEST
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'message': 'No selected file'}), HTTPStatus.BAD_REQUEST

        if not allowed_file(file.filename):
            return jsonify({'message': f"Invalid file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"}), HTTPStatus.BAD_REQUEST

        public_id_for_cloudinary = f"brand_icons/brand_{bid}_{file.filename.rsplit('.', 1)[0]}"

        upload_result = cloudinary.uploader.upload(
            file,
            folder="brand_icons",
            public_id=public_id_for_cloudinary,
            overwrite=True,
            resource_type="image"
        )
        
        icon_url = upload_result.get('secure_url')
        if not icon_url:
            current_app.logger.error(f"Cloudinary upload for brand {bid} succeeded but no secure_url.")
            return jsonify({'message': 'Cloudinary did not return a URL'}), HTTPStatus.INTERNAL_SERVER_ERROR

        brand.icon_url = icon_url
        db.session.add(brand)
        db.session.commit()

        return jsonify({
            'message': 'Brand icon uploaded and updated successfully',
            'brand': brand.serialize()
        }), HTTPStatus.OK

    except cloudinary.exceptions.Error as e:
        current_app.logger.error(f"Cloudinary upload failed for brand {bid}: {e}")
        return jsonify({'message': f"Cloudinary upload failed: {str(e)}"}), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error uploading icon for brand {bid}: {e}")
        return jsonify({'message': f"An unexpected error occurred: {str(e)}"}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/brands/<int:bid>', methods=['PUT'])
@super_admin_role_required
def update_brand(bid):
    """
    Update an existing brand.
    Supports both JSON and multipart/form-data for updating fields and icon.
    ---
    tags:
      - Brands
    security:
      - Bearer: []
    consumes:
      - application/json
      - multipart/form-data
    parameters:
      - name: bid
        in: path
        type: integer
        required: true
        description: "ID of the brand to update."
      - name: name
        in: formData
        type: string
        required: false
        description: "New name for the brand."
      - name: slug
        in: formData
        type: string
        required: false
        description: "New slug for the brand."
      - name: icon_file
        in: formData
        type: file
        required: false
        description: "New icon file for the brand (optional)."
    requestBody:
      required: false
      content:
        application/json:
          schema:
            type: object
            properties:
              name:
                type: string
                description: "New name for the brand."
              slug:
                type: string
                description: "New slug for the brand."
    responses:
      200:
        description: "Brand updated successfully."
        schema:
          type: object
          properties:
            brand_id:
              type: integer
            name:
              type: string
            slug:
              type: string
            icon_url:
              type: string
              nullable: true
            approved_by:
              type: integer
            approved_at:
              type: string
              format: date-time
      400:
        description: "Bad request (missing or invalid fields)."
      401:
        description: "Unauthorized - Invalid or missing token."
      403:
        description: "Forbidden - User does not have super admin role."
      404:
        description: "Brand not found."
      409:
        description: "Conflict - Brand with this name or slug already exists."
      415:
        description: "Unsupported Media Type."
      500:
        description: "Internal server error."
    """
    # Determine content type
    content_type = request.content_type or ''
    update_data = {}

    # --- 1) JSON path ---
    if content_type.startswith('application/json'):
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'message': 'No JSON body provided'}), HTTPStatus.BAD_REQUEST
        if 'name' in data and data['name'].strip():
            update_data['name'] = data['name'].strip()
        if 'slug' in data and data['slug'].strip():
            update_data['slug'] = data['slug'].strip()

    # --- 2) multipart/form-data path ---
    elif content_type.startswith('multipart/form-data'):
        # text fields
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip()
        if name:
            update_data['name'] = name
        if slug:
            update_data['slug'] = slug

        # file field
        file = request.files.get('icon_file')
        if file and file.filename:
            if not allowed_file(file.filename):
                return jsonify({'message': f'Invalid icon file type. Allowed: {ALLOWED_EXTENSIONS}'}), HTTPStatus.BAD_REQUEST

            try:
                upload_result = cloudinary.uploader.upload(
                    file,
                    folder="brand_icons",
                    public_id=f"brand_{bid}_{file.filename.rsplit('.', 1)[0]}",
                    overwrite=True,
                    resource_type="image"
                )
                new_url = upload_result.get('secure_url')
                if not new_url:
                    raise ValueError("No secure_url from Cloudinary")
                update_data['icon_url'] = new_url
            except Exception as e:
                current_app.logger.error(f"Cloudinary upload failed in update: {e}")
                return jsonify({'message': f'Icon upload failed: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR
    else:
        return jsonify({'message': 'Unsupported Content-Type. Use JSON or multipart/form-data.'}), HTTPStatus.UNSUPPORTED_MEDIA_TYPE

    # must have at least one field to update
    if not update_data:
        return jsonify({'message': 'No updatable fields provided.'}), HTTPStatus.BAD_REQUEST

    # Perform update
    try:
        updated_brand = BrandController.update(bid, update_data)
        return jsonify(updated_brand.serialize()), HTTPStatus.OK

    except IntegrityError as e:
        db.session.rollback()
        current_app.logger.error(f"IntegrityError updating brand {bid}: {e}")
        return jsonify({'message': 'A brand with that name or slug already exists.'}), HTTPStatus.CONFLICT

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating brand {bid}: {e}")
        return jsonify({'message': f'Could not update brand: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR


@superadmin_bp.route('/brands/<int:bid>', methods=['DELETE'])
@super_admin_role_required
def delete_brand(bid):
    """
    Delete a brand
    ---
    tags:
      - Brands
    security:
      - Bearer: []
    parameters:
      - name: bid
        in: path
        type: integer
        required: true
        description: ID of the brand to delete
    responses:
      204:
        description: Brand deleted successfully
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Brand not found
      500:
        description: Internal server error
    """
    try:
        BrandController.delete(bid)
        return '', HTTPStatus.NO_CONTENT
    except Exception as e:
        current_app.logger.error(f"Error hard-deleting brand {bid}: {e}")
        return jsonify({'message': f'Could not delete brand: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR


@superadmin_bp.route('/brands/<int:bid>/restore', methods=['POST']) # Or PUT
@super_admin_role_required
def restore_brand(bid):
    """
    Restore a previously deleted brand
    ---
    tags:
      - Brands
    security:
      - Bearer: []
    parameters:
      - name: bid
        in: path
        type: integer
        required: true
        description: ID of the brand to restore
    responses:
      200:
        description: Brand restored successfully
        schema:
          type: object
          properties:
            brand_id:
              type: integer
            name:
              type: string
            slug:
              type: string
            description:
              type: string
            website_url:
              type: string
              nullable: true
            icon_url:
              type: string
              nullable: true
            status:
              type: string
              enum: [active, inactive]
            approved_by:
              type: integer
            approved_at:
              type: string
              format: date-time
            created_at:
              type: string
              format: date-time
            updated_at:
              type: string
              format: date-time
            deleted_at:
              type: string
              format: date-time
              nullable: true
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Brand not found
      500:
        description: Internal server error
    """
    try:
        restored_brand = BrandController.undelete(bid)
        return jsonify(restored_brand.serialize()), HTTPStatus.OK
    except FileNotFoundError: 
        return jsonify({'message': 'Brand not found, cannot restore.'}), HTTPStatus.NOT_FOUND
    except Exception as e:
        db.session.rollback() 
        current_app.logger.error(f"Error restoring brand {bid}: {e}")
        return jsonify({'message': f'Could not restore brand: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR


# ── PROMOTIONS ────────────────────────────────────────────────────────────────────
@superadmin_bp.route('/promotions', methods=['GET'])
@super_admin_role_required
def list_promotions():
    """
    Get a list of all promotions
    ---
    tags:
      - Promotions
    security:
      - Bearer: []
    responses:
      200:
        description: List of promotions retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              promotion_id:
                type: integer
              name:
                type: string
              description:
                type: string
              discount_type:
                type: string
                enum: [percentage, fixed_amount]
              discount_value:
                type: number
              start_date:
                type: string
                format: date-time
              end_date:
                type: string
                format: date-time
              is_active:
                type: boolean
              created_at:
                type: string
                format: date-time
              updated_at:
                type: string
                format: date-time
              deleted_at:
                type: string
                format: date-time
                nullable: true
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      500:
        description: Internal server error
    """
    ps = PromotionController.list_all()
    return jsonify([p.serialize() for p in ps]), 200

@superadmin_bp.route('/promotions', methods=['POST'])
@super_admin_role_required
def create_promotion():
    """
    Create a new promotion
    ---
    tags:
      - Promotions
    security:
      - Bearer: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - name
              - discount_type
              - discount_value
              - start_date
              - end_date
            properties:
              name:
                type: string
                description: Name of the promotion
              description:
                type: string
                description: Description of the promotion
              discount_type:
                type: string
                enum: [percentage, fixed_amount]
                description: Type of discount to apply
              discount_value:
                type: number
                description: Value of the discount (percentage or fixed amount)
              start_date:
                type: string
                format: date-time
                description: Start date and time of the promotion
              end_date:
                type: string
                format: date-time
                description: End date and time of the promotion
              is_active:
                type: boolean
                description: Whether the promotion is active
                default: true
    responses:
      201:
        description: Promotion created successfully
        schema:
          type: object
          properties:
            promotion_id:
              type: integer
            name:
              type: string
            description:
              type: string
            discount_type:
              type: string
              enum: [percentage, fixed_amount]
            discount_value:
              type: number
            start_date:
              type: string
              format: date-time
            end_date:
              type: string
              format: date-time
            is_active:
              type: boolean
            created_at:
              type: string
              format: date-time
            updated_at:
              type: string
              format: date-time
      400:
        description: Bad request - Missing required fields or invalid data
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      500:
        description: Internal server error
    """
    data = request.get_json()
    p = PromotionController.create(data)
    return jsonify(p.serialize()), 201

@superadmin_bp.route('/promotions/<int:pid>', methods=['PUT'])
@super_admin_role_required
def update_promotion(pid):
    """
    Update an existing promotion
    ---
    tags:
      - Promotions
    security:
      - Bearer: []
    parameters:
      - name: pid
        in: path
        type: integer
        required: true
        description: ID of the promotion to update
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              name:
                type: string
                description: New name for the promotion
              description:
                type: string
                description: New description for the promotion
              discount_type:
                type: string
                enum: [percentage, fixed_amount]
                description: New type of discount to apply
              discount_value:
                type: number
                description: New value of the discount (percentage or fixed amount)
              start_date:
                type: string
                format: date-time
                description: New start date and time of the promotion
              end_date:
                type: string
                format: date-time
                description: New end date and time of the promotion
              is_active:
                type: boolean
                description: Whether the promotion is active
    responses:
      200:
        description: Promotion updated successfully
        schema:
          type: object
          properties:
            promotion_id:
              type: integer
            name:
              type: string
            description:
              type: string
            discount_type:
              type: string
              enum: [percentage, fixed_amount]
            discount_value:
              type: number
            start_date:
              type: string
              format: date-time
            end_date:
              type: string
              format: date-time
            is_active:
              type: boolean
            created_at:
              type: string
              format: date-time
            updated_at:
              type: string
              format: date-time
      400:
        description: Bad request - Invalid data
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Promotion not found
      500:
        description: Internal server error
    """
    data = request.get_json()
    p = PromotionController.update(pid, data)
    return jsonify(p.serialize()), 200

@superadmin_bp.route('/promotions/<int:pid>', methods=['DELETE'])
@super_admin_role_required
def delete_promotion(pid):
    """
    Soft delete a promotion
    ---
    tags:
      - Promotions
    security:
      - Bearer: []
    parameters:
      - name: pid
        in: path
        type: integer
        required: true
        description: ID of the promotion to delete
    responses:
      200:
        description: Promotion deleted successfully
        schema:
          type: object
          properties:
            promotion_id:
              type: integer
            name:
              type: string
            description:
              type: string
            discount_type:
              type: string
              enum: [percentage, fixed_amount]
            discount_value:
              type: number
            start_date:
              type: string
              format: date-time
            end_date:
              type: string
              format: date-time
            is_active:
              type: boolean
            created_at:
              type: string
              format: date-time
            updated_at:
              type: string
              format: date-time
            deleted_at:
              type: string
              format: date-time
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Promotion not found
      500:
        description: Internal server error
    """
    p = PromotionController.soft_delete(pid)
    return jsonify(p.serialize()), 200

# ── REVIEWS ──────────────────────────────────────────────────────────────────────
@superadmin_bp.route('/reviews', methods=['GET'])
@super_admin_role_required
def list_reviews():
    """
    Get a list of recent reviews
    ---
    tags:
      - Reviews
    security:
      - Bearer: []
    responses:
      200:
        description: List of recent reviews retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              review_id:
                type: integer
              product_id:
                type: integer
              user_id:
                type: integer
              rating:
                type: integer
                minimum: 1
                maximum: 5
              title:
                type: string
              content:
                type: string
              is_verified:
                type: boolean
              created_at:
                type: string
                format: date-time
              updated_at:
                type: string
                format: date-time
              deleted_at:
                type: string
                format: date-time
                nullable: true
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      500:
        description: Internal server error
    """
    rs = ReviewController.list_recent()
    return jsonify([r.serialize() for r in rs]), 200

@superadmin_bp.route('/reviews/<int:rid>', methods=['DELETE'])
@super_admin_role_required
def delete_review(rid):
    """
    Delete a review
    ---
    tags:
      - Reviews
    security:
      - Bearer: []
    parameters:
      - name: rid
        in: path
        type: integer
        required: true
        description: ID of the review to delete
    responses:
      200:
        description: Review deleted successfully
        schema:
          type: object
          properties:
            review_id:
              type: integer
            product_id:
              type: integer
            user_id:
              type: integer
            rating:
              type: integer
              minimum: 1
              maximum: 5
            title:
              type: string
            content:
              type: string
            is_verified:
              type: boolean
            created_at:
              type: string
              format: date-time
            updated_at:
              type: string
              format: date-time
            deleted_at:
              type: string
              format: date-time
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Review not found
      500:
        description: Internal server error
    """
    r = ReviewController.delete(rid)
    return jsonify(r.serialize()), 200


# ── ATTRIBUTE VALUES ─────────────────────────────────────────────────────────────
from controllers.superadmin.attribute_value_controller import AttributeValueController

@superadmin_bp.route('/attribute-values', methods=['GET'])
@super_admin_role_required
def list_attribute_values():
    """
    Get a list of all attribute values
    ---
    tags:
      - Attribute Values
    security:
      - Bearer: []
    responses:
      200:
        description: List of attribute values retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              attribute_id:
                type: integer
                description: ID of the attribute this value belongs to
              value_code:
                type: string
                description: Unique code for the attribute value
              value_label:
                type: string
                description: Human-readable label for the attribute value
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      500:
        description: Internal server error
    """
    avs = AttributeValueController.list_all()
    return jsonify([ {
        'attribute_id': av.attribute_id,
        'value_code': av.value_code,
        'value_label': av.value_label
    } for av in avs]), 200

@superadmin_bp.route('/attribute-values/<int:aid>', methods=['GET'])
@super_admin_role_required
def list_values_for_attribute(aid):
    """
    Get a list of values for a specific attribute
    ---
    tags:
      - Attribute Values
    security:
      - Bearer: []
    parameters:
      - name: aid
        in: path
        type: integer
        required: true
        description: ID of the attribute to get values for
    responses:
      200:
        description: List of attribute values retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              attribute_id:
                type: integer
                description: ID of the attribute these values belong to
              value_code:
                type: string
                description: Unique code for the attribute value
              value_label:
                type: string
                description: Human-readable label for the attribute value
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Attribute not found
      500:
        description: Internal server error
    """
    avs = AttributeValueController.list_for_attribute(aid)
    return jsonify([ {
        'attribute_id': av.attribute_id,
        'value_code': av.value_code,
        'value_label': av.value_label
    } for av in avs]), 200

@superadmin_bp.route('/attribute-values', methods=['POST'])
@super_admin_role_required
def create_attribute_value():
    """
    Create a new attribute value
    ---
    tags:
      - Attribute Values
    security:
      - Bearer: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - attribute_id
              - value_code
              - value_label
            properties:
              attribute_id:
                type: integer
                description: ID of the attribute this value belongs to
              value_code:
                type: string
                description: Unique code for the attribute value
              value_label:
                type: string
                description: Human-readable label for the attribute value
    responses:
      201:
        description: Attribute value created successfully
        schema:
          type: object
          properties:
            attribute_id:
              type: integer
              description: ID of the attribute this value belongs to
            value_code:
              type: string
              description: Unique code for the attribute value
            value_label:
              type: string
              description: Human-readable label for the attribute value
      400:
        description: Bad request - Missing required fields or invalid data
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Attribute not found
      409:
        description: Conflict - Attribute value with this code already exists
      500:
        description: Internal server error
    """
    data = request.get_json()
    av = AttributeValueController.create(data)
    return jsonify({
        'attribute_id': av.attribute_id,
        'value_code': av.value_code,
        'value_label': av.value_label
    }), 201

@superadmin_bp.route('/attribute-values/<int:aid>/<value_code>', methods=['PUT'])
@super_admin_role_required
def update_attribute_value(aid, value_code):
    """
    Update an existing attribute value
    ---
    tags:
      - Attribute Values
    security:
      - Bearer: []
    parameters:
      - name: aid
        in: path
        type: integer
        required: true
        description: ID of the attribute this value belongs to
      - name: value_code
        in: path
        type: string
        required: true
        description: Code of the attribute value to update
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - value_label
            properties:
              value_label:
                type: string
                description: New human-readable label for the attribute value
    responses:
      200:
        description: Attribute value updated successfully
        schema:
          type: object
          properties:
            attribute_id:
              type: integer
              description: ID of the attribute this value belongs to
            value_code:
              type: string
              description: Code of the attribute value
            value_label:
              type: string
              description: Updated human-readable label for the attribute value
      400:
        description: Bad request - Missing required fields or invalid data
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Attribute value not found
      500:
        description: Internal server error
    """
    data = request.get_json()
    av = AttributeValueController.update(aid, value_code, data)
    return jsonify({
        'attribute_id': av.attribute_id,
        'value_code': av.value_code,
        'value_label': av.value_label
    }), 200

@superadmin_bp.route('/attribute-values/<int:aid>/<value_code>', methods=['DELETE'])
@super_admin_role_required
def delete_attribute_value(aid, value_code):
    """
    Delete an attribute value
    ---
    tags:
      - Attribute Values
    security:
      - Bearer: []
    parameters:
      - name: aid
        in: path
        type: integer
        required: true
        description: ID of the attribute this value belongs to
      - name: value_code
        in: path
        type: string
        required: true
        description: Code of the attribute value to delete
    responses:
      204:
        description: Attribute value deleted successfully
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Attribute value not found
      409:
        description: Conflict - Attribute value is in use and cannot be deleted
      500:
        description: Internal server error
    """
    AttributeValueController.delete(aid, value_code)


# ── ATTRIBUTES ───────────────────────────────────────────────────────────────────
@superadmin_bp.route('/attributes', methods=['GET'])
@super_admin_role_required
def list_attributes():
    """
    Get a list of all attributes
    ---
    tags:
      - Attributes
    security:
      - Bearer: []
    responses:
      200:
        description: List of attributes retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              attribute_id:
                type: integer
                description: Unique identifier for the attribute
              code:
                type: string
                description: Unique code for the attribute
              name:
                type: string
                description: Human-readable name of the attribute
              input_type:
                type: string
                enum: [text, number, select, multiselect, boolean]
                description: Type of input field for this attribute
              created_at:
                type: string
                format: date-time
                description: When the attribute was created
              updated_at:
                type: string
                format: date-time
                description: When the attribute was last updated
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      500:
        description: Internal server error
    """
    try:
        attrs = AttributeController.list_all()
        return jsonify([a.serialize() for a in attrs]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error listing attributes: {e}")
        return jsonify({'message': 'Failed to retrieve attributes.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/attributes', methods=['POST'])
@super_admin_role_required
def create_attribute():
    """
    Create a new attribute
    ---
    tags:
      - Attributes
    security:
      - Bearer: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - code
              - name
              - input_type
            properties:
              code:
                type: string
                description: Unique code for the attribute
              name:
                type: string
                description: Human-readable name of the attribute
              input_type:
                type: string
                enum: [text, number, select, multiselect, boolean]
                description: Type of input field for this attribute
    responses:
      201:
        description: Attribute created successfully
        schema:
          type: object
          properties:
            attribute_id:
              type: integer
              description: Unique identifier for the attribute
            code:
              type: string
              description: Unique code for the attribute
            name:
              type: string
              description: Human-readable name of the attribute
            input_type:
              type: string
              enum: [text, number, select, multiselect, boolean]
              description: Type of input field for this attribute
            created_at:
              type: string
              format: date-time
              description: When the attribute was created
            updated_at:
              type: string
              format: date-time
              description: When the attribute was last updated
      400:
        description: Bad request - Missing required fields or invalid input type
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      409:
        description: Conflict - Attribute with this code already exists
      500:
        description: Internal server error
    """
    data = request.get_json()
    if not data:
        return jsonify({'message': 'No input data provided'}), HTTPStatus.BAD_REQUEST

    # Validate required fields
    required_fields = ['code', 'name', 'input_type']
    missing_fields = [field for field in required_fields if field not in data or not data[field]]
    if missing_fields:
        return jsonify({
            'message': f'Missing required fields: {", ".join(missing_fields)}'
        }), HTTPStatus.BAD_REQUEST

    # Validate input_type
    valid_input_types = ['text', 'number', 'select', 'multiselect', 'boolean']
    if data['input_type'] not in valid_input_types:
        return jsonify({
            'message': f'Invalid input type. Must be one of: {", ".join(valid_input_types)}'
        }), HTTPStatus.BAD_REQUEST

    try:
        attr = AttributeController.create(data)
        return jsonify(attr.serialize()), HTTPStatus.CREATED

    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST

    except IntegrityError as e:
        db.session.rollback()
        current_app.logger.error(f"IntegrityError creating attribute: {e}")
        if "unique constraint" in str(e.orig).lower() or \
           (hasattr(e.orig, 'pgcode') and e.orig.pgcode == '23505'):
            return jsonify({'message': 'An attribute with this code already exists.'}), HTTPStatus.CONFLICT
       

        return jsonify({'message': 'Failed to create attribute due to a data conflict.'}), HTTPStatus.CONFLICT
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating attribute: {e}")
        return jsonify({'message': f'Could not create attribute: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR
@superadmin_bp.route('/attributes/<int:attribute_id>', methods=['GET'])
@super_admin_role_required
def get_attribute(attribute_id):
    """
    Get details of a specific attribute
    ---
    tags:
      - Attributes
    security:
      - Bearer: []
    parameters:
      - name: attribute_id
        in: path
        type: integer
        required: true
        description: ID of the attribute to retrieve
    responses:
      200:
        description: Attribute details retrieved successfully
        schema:
          type: object
          properties:
            attribute_id:
              type: integer
              description: Unique identifier for the attribute
            code:
              type: string
              description: Unique code for the attribute
            name:
              type: string
              description: Human-readable name of the attribute
            input_type:
              type: string
              enum: [text, number, select, multiselect, boolean]
              description: Type of input field for this attribute
            created_at:
              type: string
              format: date-time
              description: When the attribute was created
            updated_at:
              type: string
              format: date-time
              description: When the attribute was last updated
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Attribute not found
      500:
        description: Internal server error
    """
    try:
        from models.attribute import Attribute
        attr = Attribute.query.get_or_404(attribute_id)
        return jsonify(attr.serialize()), HTTPStatus.OK
    except FileNotFoundError: 
        return jsonify({'message': 'Attribute not found'}), HTTPStatus.NOT_FOUND
    except Exception as e:
        current_app.logger.error(f"Error fetching attribute {attribute_id}: {e}")
        return jsonify({'message': 'Could not retrieve attribute.'}), HTTPStatus.INTERNAL_SERVER_ERROR


@superadmin_bp.route('/attributes/<int:attribute_id>', methods=['PUT'])
@super_admin_role_required
def update_attribute(attribute_id):
    """
    Update an existing attribute
    ---
    tags:
      - Attributes
    security:
      - Bearer: []
    parameters:
      - name: attribute_id
        in: path
        type: integer
        required: true
        description: ID of the attribute to update
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              name:
                type: string
                description: New human-readable name of the attribute
              input_type:
                type: string
                enum: [text, number, select, multiselect, boolean]
                description: New type of input field for this attribute
    responses:
      200:
        description: Attribute updated successfully
        schema:
          type: object
          properties:
            attribute_id:
              type: integer
              description: Unique identifier for the attribute
            code:
              type: string
              description: Unique code for the attribute
            name:
              type: string
              description: Updated human-readable name of the attribute
            input_type:
              type: string
              enum: [text, number, select, multiselect, boolean]
              description: Updated type of input field for this attribute
            created_at:
              type: string
              format: date-time
              description: When the attribute was created
            updated_at:
              type: string
              format: date-time
              description: When the attribute was last updated
      400:
        description: Bad request - No fields to update provided
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Attribute not found
      500:
        description: Internal server error
    """
    data = request.get_json()
    if not data:
        return jsonify({'message': 'No input data provided for update'}), HTTPStatus.BAD_REQUEST

    if not data.get('name') and not data.get('input_type'):
        return jsonify({'message': 'No fields to update provided (name, input_type).'}), HTTPStatus.BAD_REQUEST

    try:
        attribute = AttributeController.update(attribute_id, data)
        return jsonify(attribute.serialize()), HTTPStatus.OK
    except FileNotFoundError: 
        return jsonify({'message': 'Attribute not found'}), HTTPStatus.NOT_FOUND
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating attribute {attribute_id}: {e}")
        return jsonify({'message': f'Could not update attribute: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR


@superadmin_bp.route('/attributes/<int:attribute_id>', methods=['DELETE'])
@super_admin_role_required
def delete_attribute(attribute_id):
    """
    Delete an attribute
    ---
    tags:
      - Attributes
    security:
      - Bearer: []
    parameters:
      - name: attribute_id
        in: path
        type: integer
        required: true
        description: ID of the attribute to delete
    responses:
      200:
        description: Attribute deleted successfully
        schema:
          type: object
          properties:
            message:
              type: string
              description: Success message with the deleted attribute ID
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Attribute not found
      409:
        description: Conflict - Attribute is in use by other records and cannot be deleted
      500:
        description: Internal server error
    """
    try:
        AttributeController.delete(attribute_id)
        return jsonify({'message': f'Attribute with ID {attribute_id} deleted successfully.'}), HTTPStatus.OK
    except FileNotFoundError: 
        return jsonify({'message': 'Attribute not found'}), HTTPStatus.NOT_FOUND
    except IntegrityError as e:
        db.session.rollback()
        current_app.logger.warning(f"IntegrityError deleting attribute {attribute_id}: {e}")
        if "foreign key constraint" in str(e.orig).lower():
            return jsonify({'message': 'Cannot delete attribute. It is currently in use by other records.'}), HTTPStatus.CONFLICT
        return jsonify({'message': f'Database conflict: {str(e)}'}), HTTPStatus.CONFLICT
    except Exception as e: 
        db.session.rollback()
        current_app.logger.error(f"Error deleting attribute {attribute_id}: {e}")
        return jsonify({'message': f'Could not delete attribute: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR

# ── CATEGORY ATTRIBUTES (Associations) ───────────────────────────────────────────
@superadmin_bp.route('/categories/<int:cid>/attributes', methods=['GET'])
@super_admin_role_required
def list_category_attributes_for_category(cid):
    """
    Get a list of attributes associated with a specific category
    ---
    tags:
      - Category Attributes
    security:
      - Bearer: []
    parameters:
      - name: cid
        in: path
        type: integer
        required: true
        description: ID of the category to get attributes for
    responses:
      200:
        description: List of category attributes retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              category_id:
                type: integer
                description: ID of the category
              attribute_id:
                type: integer
                description: ID of the attribute
              required_flag:
                type: boolean
                description: Whether this attribute is required for products in this category
              attribute:
                type: object
                description: Details of the associated attribute
                properties:
                  attribute_id:
                    type: integer
                    description: Unique identifier for the attribute
                  code:
                    type: string
                    description: Unique code for the attribute
                  name:
                    type: string
                    description: Human-readable name of the attribute
                  input_type:
                    type: string
                    enum: [text, number, select, multiselect, boolean]
                    description: Type of input field for this attribute
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Category not found
      500:
        description: Internal server error
    """
    try:
        associations = CategoryAttributeController.list_attributes_for_category(cid)
        return jsonify(associations), HTTPStatus.OK
    except FileNotFoundError as e:
        return jsonify({'message': str(e)}), HTTPStatus.NOT_FOUND
    except Exception as e:
        current_app.logger.error(f"Error listing attributes for category {cid}: {e}")
        return jsonify({'message': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@superadmin_bp.route('/categories/<int:cid>/attributes', methods=['POST'])
@super_admin_role_required
def add_attribute_to_category(cid):
    """
    Add an attribute to a category
    ---
    tags:
      - Category Attributes
    security:
      - Bearer: []
    parameters:
      - name: cid
        in: path
        type: integer
        required: true
        description: ID of the category to add the attribute to
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - attribute_id
            properties:
              attribute_id:
                type: integer
                description: ID of the attribute to add to the category
              required_flag:
                type: boolean
                description: Whether this attribute should be required for products in this category
                default: false
    responses:
      201:
        description: Attribute added to category successfully
        schema:
          type: object
          properties:
            category_id:
              type: integer
              description: ID of the category
            attribute_id:
              type: integer
              description: ID of the attribute
            required_flag:
              type: boolean
              description: Whether this attribute is required for products in this category
            attribute_details:
              type: object
              description: Details of the associated attribute
              properties:
                attribute_id:
                  type: integer
                  description: Unique identifier for the attribute
                name:
                  type: string
                  description: Human-readable name of the attribute
                code:
                  type: string
                  description: Unique code for the attribute
      400:
        description: Bad request - Missing required fields or invalid data
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Category or attribute not found
      409:
        description: Conflict - Attribute is already associated with this category
      500:
        description: Internal server error
    """
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Request body is missing or not JSON.'}), HTTPStatus.BAD_REQUEST
    
    try:
        association = CategoryAttributeController.add_attribute_to_category(cid, data)
        
        attribute_data = None
        if association.attribute:
             attribute_data = {
                 'attribute_id': association.attribute.attribute_id,
                 'name': association.attribute.name,
                 'code': association.attribute.code
             }
        return jsonify({
            'category_id': association.category_id,
            'attribute_id': association.attribute_id,
            'required_flag': association.required_flag,
            'attribute_details': attribute_data
        }), HTTPStatus.CREATED
    except FileNotFoundError as e: 
        return jsonify({'message': str(e)}), HTTPStatus.NOT_FOUND
    except ValueError as e: 
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except IntegrityError as e: 
        db.session.rollback()
       
        msg = e.args[0] if e.args and isinstance(e.args[0], str) else str(e.orig) if hasattr(e, 'orig') else "Data integrity conflict (e.g., association already exists)."
        return jsonify({'message': msg}), HTTPStatus.CONFLICT
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding attribute to category {cid}: {e}")
        return jsonify({'message': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@superadmin_bp.route('/categories/<int:cid>/attributes/<int:aid>', methods=['PUT'])
@super_admin_role_required
def update_attribute_for_category(cid, aid):
    """
    Update an attribute's settings for a specific category
    ---
    tags:
      - Category Attributes
    security:
      - Bearer: []
    parameters:
      - name: cid
        in: path
        type: integer
        required: true
        description: ID of the category
      - name: aid
        in: path
        type: integer
        required: true
        description: ID of the attribute to update
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              required_flag:
                type: boolean
                description: Whether this attribute should be required for products in this category
    responses:
      200:
        description: Category attribute updated successfully
        schema:
          type: object
          properties:
            category_id:
              type: integer
              description: ID of the category
            attribute_id:
              type: integer
              description: ID of the attribute
            required_flag:
              type: boolean
              description: Whether this attribute is required for products in this category
            attribute:
              type: object
              description: Details of the associated attribute
              properties:
                attribute_id:
                  type: integer
                  description: Unique identifier for the attribute
                code:
                  type: string
                  description: Unique code for the attribute
                name:
                  type: string
                  description: Human-readable name of the attribute
                input_type:
                  type: string
                  enum: [text, number, select, multiselect, boolean]
                  description: Type of input field for this attribute
      400:
        description: Bad request - Invalid data
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Category or attribute not found
      500:
        description: Internal server error
    """
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Request body is missing or not JSON.'}), HTTPStatus.BAD_REQUEST
    
    try:
        association = CategoryAttributeController.update_attribute_for_category(cid, aid, data)
        return jsonify(association.serialize()), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error updating attribute for category: {e}")
        return jsonify({'message': 'Failed to update attribute for category.'}), HTTPStatus.INTERNAL_SERVER_ERROR


@superadmin_bp.route('/categories/<int:cid>/attributes/<int:aid>', methods=['DELETE'])
@super_admin_role_required
def remove_attribute_from_category(cid, aid):
    """
    Remove an attribute from a category
    ---
    tags:
      - Category Attributes
    security:
      - Bearer: []
    parameters:
      - name: cid
        in: path
        type: integer
        required: true
        description: ID of the category
      - name: aid
        in: path
        type: integer
        required: true
        description: ID of the attribute to remove
    responses:
      204:
        description: Attribute removed from category successfully
      400:
        description: Bad request - Invalid category or attribute ID
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Category or attribute not found
      500:
        description: Internal server error
    """
    try:
        CategoryAttributeController.remove_attribute_from_category(cid, aid)
        return '', HTTPStatus.NO_CONTENT
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error removing attribute from category: {e}")
        return jsonify({'message': 'Failed to remove attribute from category.'}), HTTPStatus.INTERNAL_SERVER_ERROR

# ── CATEGORY ATTRIBUTES ─────────────────────────────────────────────────────────
@superadmin_bp.route('/categories/<int:cid>/assign-attribute', methods=['POST'])
@super_admin_role_required
def assign_attribute_to_category(cid):
    """
    Assign an attribute to a category
    ---
    tags:
      - Category Attributes
    security:
      - Bearer: []
    parameters:
      - name: cid
        in: path
        type: integer
        required: true
        description: ID of the category to assign the attribute to
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - attribute_id
            properties:
              attribute_id:
                type: integer
                description: ID of the attribute to assign to the category
              required_flag:
                type: boolean
                description: Whether this attribute should be required for products in this category
                default: false
    responses:
      201:
        description: Attribute assigned to category successfully
        schema:
          type: object
          properties:
            category_id:
              type: integer
              description: ID of the category
            attribute_id:
              type: integer
              description: ID of the attribute
            required_flag:
              type: boolean
              description: Whether this attribute is required for products in this category
            attribute:
              type: object
              description: Details of the associated attribute
              properties:
                attribute_id:
                  type: integer
                  description: Unique identifier for the attribute
                code:
                  type: string
                  description: Unique code for the attribute
                name:
                  type: string
                  description: Human-readable name of the attribute
                input_type:
                  type: string
                  enum: [text, number, select, multiselect, boolean]
                  description: Type of input field for this attribute
      400:
        description: Bad request - Missing required fields or invalid data
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Category or attribute not found
      409:
        description: Conflict - Attribute is already assigned to this category
      500:
        description: Internal server error
    """
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Request body is missing or not JSON.'}), HTTPStatus.BAD_REQUEST
    
    try:
        association = CategoryAttributeController.add_attribute_to_category(cid, data)
        return jsonify(association.serialize()), HTTPStatus.CREATED
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error assigning attribute to category: {e}")
        return jsonify({'message': 'Failed to assign attribute to category.'}), HTTPStatus.INTERNAL_SERVER_ERROR

# ── BRAND CATEGORIES ────────────────────────────────────────────────────────────
@superadmin_bp.route('/brands/<int:bid>/categories/<int:cid>', methods=['POST'])
@super_admin_role_required
def add_category_to_brand(bid, cid):
    """
    Add a category to a brand
    ---
    tags:
      - Brand Categories
    security:
      - Bearer: []
    parameters:
      - name: bid
        in: path
        type: integer
        required: true
        description: ID of the brand
      - name: cid
        in: path
        type: integer
        required: true
        description: ID of the category to add to the brand
    responses:
      200:
        description: Category added to brand successfully
        schema:
          type: object
          properties:
            brand_id:
              type: integer
              description: ID of the brand
            name:
              type: string
              description: Name of the brand
            slug:
              type: string
              description: URL-friendly slug for the brand
            description:
              type: string
              description: Description of the brand
            website_url:
              type: string
              nullable: true
              description: Website URL of the brand
            icon_url:
              type: string
              nullable: true
              description: URL of the brand's icon
            status:
              type: string
              enum: [active, inactive]
              description: Current status of the brand
            categories:
              type: array
              description: List of categories associated with the brand
              items:
                type: object
                properties:
                  id:
                    type: integer
                    description: ID of the category
                  name:
                    type: string
                    description: Name of the category
                  slug:
                    type: string
                    description: URL-friendly slug for the category
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Brand or category not found
      409:
        description: Conflict - Category is already associated with this brand
      500:
        description: Internal server error
    """
    try:
        brand = BrandController.add_category(bid, cid)
        return jsonify(brand.serialize()), 200
    except Exception as e:
        current_app.logger.error(f"Error adding category to brand: {str(e)}")
        return jsonify({"error": str(e)}), 500

@superadmin_bp.route('/brands/<int:bid>/categories/<int:cid>', methods=['DELETE'])
@super_admin_role_required
def remove_category_from_brand(bid, cid):
    """
    Remove a category from a brand
    ---
    tags:
      - Brand Categories
    security:
      - Bearer: []
    parameters:
      - name: bid
        in: path
        type: integer
        required: true
        description: ID of the brand
      - name: cid
        in: path
        type: integer
        required: true
        description: ID of the category to remove from the brand
    responses:
      200:
        description: Category removed from brand successfully
        schema:
          type: object
          properties:
            brand_id:
              type: integer
              description: ID of the brand
            name:
              type: string
              description: Name of the brand
            slug:
              type: string
              description: URL-friendly slug for the brand
            description:
              type: string
              description: Description of the brand
            website_url:
              type: string
              nullable: true
              description: Website URL of the brand
            icon_url:
              type: string
              nullable: true
              description: URL of the brand's icon
            status:
              type: string
              enum: [active, inactive]
              description: Current status of the brand
            categories:
              type: array
              description: Updated list of categories associated with the brand
              items:
                type: object
                properties:
                  id:
                    type: integer
                    description: ID of the category
                  name:
                    type: string
                    description: Name of the category
                  slug:
                    type: string
                    description: URL-friendly slug for the category
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Brand or category not found
      500:
        description: Internal server error
    """
    try:
        brand = BrandController.remove_category(bid, cid)
        return jsonify(brand.serialize()), 200
    except Exception as e:
        current_app.logger.error(f"Error removing category from brand: {str(e)}")
        return jsonify({"error": str(e)}), 500

@superadmin_bp.route('/brands/<int:bid>/categories', methods=['GET'])
@super_admin_role_required
def get_brand_categories(bid):
    """
    Get all categories associated with a brand
    ---
    tags:
      - Brand Categories
    security:
      - Bearer: []
    parameters:
      - name: bid
        in: path
        type: integer
        required: true
        description: ID of the brand to get categories for
    responses:
      200:
        description: List of categories retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                description: ID of the category
              name:
                type: string
                description: Name of the category
              slug:
                type: string
                description: URL-friendly slug for the category
              parent_id:
                type: integer
                nullable: true
                description: ID of the parent category, if any
              icon_url:
                type: string
                nullable: true
                description: URL of the category's icon
              created_at:
                type: string
                format: date-time
                description: When the category was created
              updated_at:
                type: string
                format: date-time
                description: When the category was last updated
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: Brand not found
      500:
        description: Internal server error
    """
    try:
        categories = BrandCategoryController.get_categories_for_brand(bid)
        return jsonify([c.serialize() for c in categories]), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error getting categories for brand: {e}")
        return jsonify({'message': 'Failed to get categories for brand.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/categories/main', methods=['GET'])
@super_admin_role_required
def list_main_categories():
    """
    Get all main categories (categories without a parent)
    ---
    tags:
      - Categories
    security:
      - Bearer: []
    responses:
      200:
        description: List of main categories retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                description: ID of the category
              name:
                type: string
                description: Name of the category
              slug:
                type: string
                description: URL-friendly slug for the category
              icon_url:
                type: string
                nullable: true
                description: URL of the category's icon
              status:
                type: string
                enum: [active, inactive]
                description: Current status of the category
              created_at:
                type: string
                format: date-time
                description: When the category was created
              updated_at:
                type: string
                format: date-time
                description: When the category was last updated
              subcategories:
                type: array
                description: List of subcategories under this main category
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                      description: ID of the subcategory
                    name:
                      type: string
                      description: Name of the subcategory
                    slug:
                      type: string
                      description: URL-friendly slug for the subcategory
                    icon_url:
                      type: string
                      nullable: true
                      description: URL of the subcategory's icon
                    status:
                      type: string
                      enum: [active, inactive]
                      description: Current status of the subcategory
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      500:
        description: Internal server error
    """
    try:
        categories = CategoryController.get_main_categories()
        return jsonify([category.serialize() for category in categories]), 200
    except Exception as e:
        current_app.logger.error(f"Error listing main categories: {e}")
        return jsonify({'message': 'Failed to retrieve main categories.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/homepage/categories', methods=['GET'])
@super_admin_role_required
def get_featured_categories():
    """
    Get all categories that are featured on the homepage
    ---
    tags:
      - Categories
    security:
      - Bearer: []
    responses:
      200:
        description: List of featured categories retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                description: ID of the category
              name:
                type: string
                description: Name of the category
              slug:
                type: string
                description: URL-friendly slug for the category
              icon_url:
                type: string
                nullable: true
                description: URL of the category's icon
              status:
                type: string
                enum: [active, inactive]
                description: Current status of the category
              featured_order:
                type: integer
                description: Order in which this category appears on the homepage
              created_at:
                type: string
                format: date-time
                description: When the category was created
              updated_at:
                type: string
                format: date-time
                description: When the category was last updated
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      500:
        description: Internal server error
    """
    try:
        categories = HomepageController.get_featured_categories()
        return jsonify([c.serialize() for c in categories]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting featured categories: {e}")
        return jsonify({'message': 'Failed to retrieve featured categories.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/homepage/categories', methods=['POST'])
@super_admin_role_required
def update_featured_categories():
    """
    Update the list of categories featured on the homepage
    ---
    tags:
      - Categories
    security:
      - Bearer: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - category_ids
            properties:
              category_ids:
                type: array
                description: List of category IDs in the order they should appear on the homepage
                items:
                  type: integer
                  description: ID of a category to feature
    responses:
      200:
        description: Featured categories updated successfully
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                description: ID of the category
              name:
                type: string
                description: Name of the category
              slug:
                type: string
                description: URL-friendly slug for the category
              icon_url:
                type: string
                nullable: true
                description: URL of the category's icon
              status:
                type: string
                enum: [active, inactive]
                description: Current status of the category
              featured_order:
                type: integer
                description: Order in which this category appears on the homepage
      400:
        description: Bad request - Invalid category IDs or missing required fields
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      404:
        description: One or more categories not found
      500:
        description: Internal server error
    """
    try:
        data = request.get_json()
        if not data or 'category_ids' not in data:
            return jsonify({'message': 'Missing category_ids in request body'}), HTTPStatus.BAD_REQUEST
        
        categories = HomepageController.update_featured_categories(data['category_ids'])
        return jsonify([c.serialize() for c in categories]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error updating featured categories: {e}")
        return jsonify({'message': 'Failed to update featured categories.'}), HTTPStatus.INTERNAL_SERVER_ERROR

# ── PRODUCT MONITORING ───────────────────────────────────────────────────────────
@superadmin_bp.route('/products/pending', methods=['GET'])
@super_admin_role_required
def list_pending_products():
    """
    Get all products that are pending approval
    ---
    tags:
      - Products
    security:
      - Bearer: []
    parameters:
      - name: page
        in: query
        type: integer
        description: Page number for pagination
        default: 1
      - name: per_page
        in: query
        type: integer
        description: Number of items per page
        default: 10
    responses:
      200:
        description: List of pending products retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              product_id:
                type: integer
                description: ID of the product
              product_name:
                type: string
                description: Name of the product
              sku:
                type: string
                description: Stock Keeping Unit of the product
              status:
                type: string
                enum: [pending, approved, rejected]
                description: Current approval status of the product
              cost_price:
                type: number
                description: Cost price of the product
              selling_price:
                type: number
                description: Selling price of the product
              media:
                type: array
                description: List of media associated with the product
                items:
                  type: object
                  description: Media object
              meta:
                type: object
                nullable: true
                description: Additional metadata for the product
              brand:
                type: object
                nullable: true
                description: Brand information
              category:
                type: object
                nullable: true
                description: Category information
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      500:
        description: Internal server error
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        products = ProductMonitoringController.get_pending_products()
        return jsonify([{
            'product_id': p.product_id,
            'product_name': p.product_name,
            'sku': p.sku,
            'status': p.approval_status,
            'cost_price': float(p.cost_price),
            'selling_price': float(p.selling_price),
            'media': [m.serialize() for m in p.media] if p.media else [],
            'meta': p.meta.serialize() if p.meta else None,
            'brand': p.brand.serialize() if p.brand else None,
            'category': p.category.serialize() if p.category else None
        } for p in products]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error listing pending products: {e}")
        return jsonify({'message': 'Failed to retrieve pending products.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/products/approved', methods=['GET'])
@super_admin_role_required
def list_approved_products():
    """
    Get all products that have been approved
    ---
    tags:
      - Products
    security:
      - Bearer: []
    parameters:
      - name: page
        in: query
        type: integer
        description: Page number for pagination
        default: 1
      - name: per_page
        in: query
        type: integer
        description: Number of items per page
        default: 10
    responses:
      200:
        description: List of approved products retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              product_id:
                type: integer
                description: ID of the product
              product_name:
                type: string
                description: Name of the product
              sku:
                type: string
                description: Stock Keeping Unit of the product
              status:
                type: string
                enum: [pending, approved, rejected]
                description: Current approval status of the product
              cost_price:
                type: number
                description: Cost price of the product
              selling_price:
                type: number
                description: Selling price of the product
              media:
                type: array
                description: List of media associated with the product
                items:
                  type: object
                  description: Media object
              meta:
                type: object
                nullable: true
                description: Additional metadata for the product
              brand:
                type: object
                nullable: true
                description: Brand information
              category:
                type: object
                nullable: true
                description: Category information
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      500:
        description: Internal server error
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        products = ProductMonitoringController.get_approved_products()
        return jsonify([{
            'product_id': p.product_id,
            'product_name': p.product_name,
            'sku': p.sku,
            'status': p.approval_status,
            'cost_price': float(p.cost_price),
            'selling_price': float(p.selling_price),
            'media': [m.serialize() for m in p.media] if p.media else [],
            'meta': p.meta.serialize() if p.meta else None,
            'brand': p.brand.serialize() if p.brand else None,
            'category': p.category.serialize() if p.category else None
        } for p in products]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error listing approved products: {e}")
        return jsonify({'message': 'Failed to retrieve approved products.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/products/rejected', methods=['GET'])
@super_admin_role_required
def list_rejected_products():
    """
    Get all products that have been rejected
    ---
    tags:
      - Products
    security:
      - Bearer: []
    parameters:
      - name: page
        in: query
        type: integer
        description: Page number for pagination
        default: 1
      - name: per_page
        in: query
        type: integer
        description: Number of items per page
        default: 10
    responses:
      200:
        description: List of rejected products retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              product_id:
                type: integer
                description: ID of the product
              product_name:
                type: string
                description: Name of the product
              sku:
                type: string
                description: Stock Keeping Unit of the product
              status:
                type: string
                enum: [pending, approved, rejected]
                description: Current approval status of the product
              cost_price:
                type: number
                description: Cost price of the product
              selling_price:
                type: number
                description: Selling price of the product
              media:
                type: array
                description: List of media associated with the product
                items:
                  type: object
                  description: Media object
              meta:
                type: object
                nullable: true
                description: Additional metadata for the product
              brand:
                type: object
                nullable: true
                description: Brand information
              category:
                type: object
                nullable: true
                description: Category information
              rejection_reason:
                type: string
                description: Reason why the product was rejected
      401:
        description: Unauthorized - Invalid or missing token
      403:
        description: Forbidden - User does not have super admin role
      500:
        description: Internal server error
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        products = ProductMonitoringController.get_rejected_products()
        return jsonify([{
            'product_id': p.product_id,
            'product_name': p.product_name,
            'sku': p.sku,
            'status': p.approval_status,
            'cost_price': float(p.cost_price),
            'selling_price': float(p.selling_price),
            'rejection_reason': p.rejection_reason,
            'media': [m.serialize() for m in p.media] if p.media else [],
            'meta': p.meta.serialize() if p.meta else None,
            'brand': p.brand.serialize() if p.brand else None,
            'category': p.category.serialize() if p.category else None
        } for p in products]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error listing rejected products: {e}")
        return jsonify({'message': 'Failed to retrieve rejected products.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/products/<int:product_id>/approve', methods=['POST'])
@super_admin_role_required
def approve_product(product_id):
    """
    Approve a product by product ID
    ---
    tags:
      - Product Monitoring
    parameters:
      - in: path
        name: product_id
        type: integer
        required: true
        description: ID of the product to approve
    responses:
      200:
        description: Product approved successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            product_name:
              type: string
            status:
              type: string
            approved_at:
              type: string
              format: date-time
            approved_by:
              type: integer
      400:
        description: Bad request (e.g. invalid product ID or already approved)
      500:
        description: Internal server error
    """

    try:
        admin_id = get_jwt_identity()
        product = ProductMonitoringController.approve_product(product_id, admin_id)
        return jsonify({
            'product_id': product.product_id,
            'product_name': product.product_name,
            'status': product.approval_status,
            'approved_at': product.approved_at.isoformat(),
            'approved_by': product.approved_by
        }), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error approving product {product_id}: {e}")
        return jsonify({'message': 'Failed to approve product.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/products/<int:product_id>/reject', methods=['POST'])
@super_admin_role_required
def reject_product(product_id):
    """
    Reject a product by product ID
    ---
    tags:
      - Product Monitoring
    parameters:
      - in: path
        name: product_id
        type: integer
        required: true
        description: ID of the product to reject
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - reason
          properties:
            reason:
              type: string
              description: Reason for rejecting the product
    responses:
      200:
        description: Product rejected successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            product_name:
              type: string
            status:
              type: string
            rejection_reason:
              type: string
            approved_at:
              type: string
              format: date-time
            approved_by:
              type: integer
      400:
        description: Bad request (e.g. missing rejection reason)
      500:
        description: Internal server error
    """

    try:
        data = request.get_json()
        if not data or 'reason' not in data:
            return jsonify({'message': 'Rejection reason is required'}), HTTPStatus.BAD_REQUEST

        admin_id = get_jwt_identity()
        product = ProductMonitoringController.reject_product(product_id, admin_id, data['reason'])
        return jsonify({
            'product_id': product.product_id,
            'product_name': product.product_name,
            'status': product.approval_status,
            'rejection_reason': product.rejection_reason,
            'approved_at': product.approved_at.isoformat(),
            'approved_by': product.approved_by
        }), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error rejecting product {product_id}: {e}")
        return jsonify({'message': 'Failed to reject product.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/products/<int:product_id>', methods=['GET'])
@super_admin_role_required
def get_product_details(product_id):
    """
    Get product details by product ID
    ---
    tags:
      - Product Monitoring
    parameters:
      - in: path
        name: product_id
        type: integer
        required: true
        description: ID of the product to retrieve
    responses:
      200:
        description: Product details retrieved successfully
        schema:
          type: object
          additionalProperties: true
      500:
        description: Internal server error
    """
    
    try:
        product_details = ProductMonitoringController.get_product_details(product_id)
        return jsonify(product_details), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting product details for {product_id}: {e}")
        return jsonify({'message': 'Failed to retrieve product details.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/products', methods=['GET', 'OPTIONS'])
@cross_origin()
@super_admin_role_required
def list_products():
    """
    List all products
    ---
    tags:
      - Product Monitoring
    responses:
      200:
        description: List of products retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              product_id:
                type: integer
              product_name:
                type: string
      500:
        description: Internal server error
    """
    
    if request.method == 'OPTIONS':
        return '', HTTPStatus.OK
        
    try:
        products = ProductController.list_all()
        return jsonify([{
            'product_id': p.product_id,
            'product_name': p.product_name
        } for p in products]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error listing products: {e}")
        return jsonify({'message': 'Failed to retrieve products.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/carousels', methods=['GET', 'POST', 'OPTIONS'])
@cross_origin()
@super_admin_role_required
def carousels_handler():
    """
    Get all carousels or create a new carousel
    ---
    tags:
      - Carousels
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: type
        type: string
        required: true
        description: Type of the carousel (e.g., product, banner)
      - in: formData
        name: target_id
        type: integer
        required: true
        description: Target ID the carousel refers to
      - in: formData
        name: image
        type: file
        required: true
        description: Image file for the carousel
      - in: formData
        name: display_order
        type: integer
        required: false
        description: Order in which the carousel should be displayed
      - in: formData
        name: is_active
        type: boolean
        required: false
        description: Whether the carousel is active
      - in: formData
        name: shareable_link
        type: string
        required: false
        description: Optional shareable link for the carousel
    responses:
      200:
        description: List of carousels retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
              type:
                type: string
              image_url:
                type: string
              target_id:
                type: integer
              display_order:
                type: integer
              is_active:
                type: boolean
              shareable_link:
                type: string
      201:
        description: Carousel created successfully
        schema:
          type: object
          properties:
            id:
              type: integer
            type:
              type: string
            image_url:
              type: string
            target_id:
              type: integer
            display_order:
              type: integer
            is_active:
              type: boolean
            shareable_link:
              type: string
      400:
        description: Missing required fields
      500:
        description: Internal server error
    """

    from controllers.superadmin.carousel_controller import CarouselController
    from flask import request, jsonify, current_app
    from http import HTTPStatus
    if request.method == 'OPTIONS':
        return '', HTTPStatus.OK
    if request.method == 'GET':
        try:
            carousels = CarouselController.list_all()
            return jsonify([
                {
                    'id': c.id,
                    'type': c.type,
                    'image_url': c.image_url,
                    'target_id': c.target_id,
                    'display_order': c.display_order,
                    'is_active': c.is_active,
                    'shareable_link': c.shareable_link
                } for c in carousels
            ]), HTTPStatus.OK
        except Exception as e:
            current_app.logger.error(f"Error listing carousels: {e}")
            return jsonify({'message': 'Failed to retrieve carousels.'}), HTTPStatus.INTERNAL_SERVER_ERROR
    if request.method == 'POST':
        try:
            # Accept multipart/form-data
            type_ = request.form.get('type')
            target_id = request.form.get('target_id')
            shareable_link = request.form.get('shareable_link')
            display_order = request.form.get('display_order', 0)
            is_active = request.form.get('is_active', 'true').lower() == 'true'
            image_file = request.files.get('image')
            if not type_ or not target_id or not image_file:
                return jsonify({'message': 'type, target_id, and image are required.'}), HTTPStatus.BAD_REQUEST
            data = {
                'type': type_,
                'target_id': int(target_id),
                'display_order': int(display_order),
                'is_active': is_active,
                'shareable_link': shareable_link
            }
            carousel = CarouselController.create(data, image_file=image_file)
            return jsonify(carousel.serialize()), HTTPStatus.CREATED
        except Exception as e:
            current_app.logger.error(f"Error creating carousel: {e}")
            return jsonify({'message': f'Failed to create carousel: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/carousels/<int:carousel_id>', methods=['DELETE'])
@cross_origin()
@super_admin_role_required
def delete_carousel(carousel_id):
    """
    Delete a carousel item by ID
    ---
    tags:
      - Carousels
    parameters:
      - in: path
        name: carousel_id
        type: integer
        required: true
        description: ID of the carousel item to delete
    responses:
      200:
        description: Carousel item deleted successfully
        schema:
          type: object
          properties:
            message:
              type: string
            id:
              type: integer
      500:
        description: Internal server error
    """

    from controllers.superadmin.carousel_controller import CarouselController
    from flask import jsonify, current_app
    from http import HTTPStatus
    try:
        carousel = CarouselController.delete(carousel_id)
        return jsonify({'message': 'Carousel deleted successfully', 'id': carousel.id}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error deleting carousel {carousel_id}: {e}")
        return jsonify({'message': f'Failed to delete carousel: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/carousels/order', methods=['PUT'])
@cross_origin()
@super_admin_role_required
def update_carousel_order():
    """
    Update display order of carousel items
    ---
    tags:
      - Carousels
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - order
          properties:
            order:
              type: array
              description: List of carousel IDs in the new display order
              items:
                type: integer
    responses:
      200:
        description: Carousel order updated successfully
        schema:
          type: object
          properties:
            message:
              type: string
      400:
        description: Bad request (e.g. missing order data)
      500:
        description: Internal server error
    """

    from controllers.superadmin.carousel_controller import CarouselController
    from flask import request, jsonify, current_app
    from http import HTTPStatus
    try:
        data = request.get_json()
        if not data or 'order' not in data:
            return jsonify({'message': 'Missing order data'}), HTTPStatus.BAD_REQUEST
        updated = CarouselController.update_display_orders(data['order'])
        return jsonify({'message': f'Updated {updated} carousel items'}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error updating carousel order: {e}")
        return jsonify({'message': f'Failed to update carousel order: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR

# ── PERFORMANCE ANALYTICS ───────────────────────────────────────────────────────
@superadmin_bp.route('/analytics/revenue', methods=['GET'])
@super_admin_role_required
def get_total_revenue():
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        result = PerformanceAnalyticsController.get_total_revenue()
        return jsonify(result), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting total revenue: {e}")
        return jsonify({'message': 'Failed to retrieve revenue data.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/analytics/active-users', methods=['GET'])
@super_admin_role_required
def get_active_users():
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        result = PerformanceAnalyticsController.get_active_users()
        return jsonify(result), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting active users: {e}")
        return jsonify({'message': 'Failed to retrieve active users data.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/analytics/total-merchants', methods=['GET'])
@super_admin_role_required
def get_total_merchants():
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        result = PerformanceAnalyticsController.get_total_merchants()
        return jsonify(result), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting total merchants: {e}")
        return jsonify({'message': 'Failed to retrieve merchants data.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/analytics/monthly-orders', methods=['GET'])
@super_admin_role_required
def get_monthly_orders():
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        result = PerformanceAnalyticsController.get_orders_this_month()
        return jsonify(result), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting monthly orders: {e}")
        return jsonify({'message': 'Failed to retrieve monthly orders data.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/analytics/dashboard', methods=['GET'])
@super_admin_role_required
def get_all_metrics():
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        result = PerformanceAnalyticsController.get_all_metrics()
        return jsonify(result), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting all metrics: {e}")
        return jsonify({'message': 'Failed to retrieve dashboard metrics.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/analytics/revenue-orders-trend', methods=['GET'])
@super_admin_role_required
def get_revenue_orders_trend():
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        months = request.args.get('months', default=12, type=int)
        result = PerformanceAnalyticsController.get_revenue_orders_trend(months)
        return jsonify(result), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting revenue and orders trend: {e}")
        return jsonify({'message': 'Failed to retrieve revenue and orders trend data.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/analytics/merchant-performance', methods=['GET'])
@super_admin_role_required
def get_merchant_performance():
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        months = request.args.get('months', default=12, type=int)
        result = PerformanceAnalyticsController.get_merchant_performance(months)
        return jsonify(result), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting merchant performance: {e}")
        return jsonify({'message': 'Failed to retrieve merchant performance data.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/analytics/user-growth-trend', methods=['GET'])
@super_admin_role_required
def get_user_growth_trend():
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        months = request.args.get('months', default=12, type=int)
        result = PerformanceAnalyticsController.get_user_growth_trend(months)
        return jsonify(result), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting user growth trend: {e}")
        return jsonify({'message': 'Failed to retrieve user growth trend data.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/analytics/average-order-value', methods=['GET'])
@super_admin_role_required
def get_average_order_value():
    """Get average order value analytics"""
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        months = request.args.get('months', default=1, type=int)
        result = PerformanceAnalyticsController.get_average_order_value()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in get_average_order_value: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Failed to fetch average order value data"
        }), 500

@superadmin_bp.route('/analytics/total-products', methods=['GET'])
@super_admin_role_required
def get_total_products():
    """Get total products analytics"""
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        months = request.args.get('months', default=1, type=int)
        result = PerformanceAnalyticsController.get_total_products()
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error in get_total_products: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Failed to fetch total products data"
        }), 500

@superadmin_bp.route('/analytics/category-distribution', methods=['GET'])
@super_admin_role_required
def get_category_distribution():
    """Get product category distribution analytics"""
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        result = PerformanceAnalyticsController.get_category_distribution()
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error in get_category_distribution: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Failed to fetch category distribution data"
        }), 500

@superadmin_bp.route('/analytics/top-merchants', methods=['GET'])
@super_admin_role_required
def get_top_merchants():
    """Get top performing merchants based on revenue"""
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        result = PerformanceAnalyticsController.get_top_merchants()
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error in get_top_merchants: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Failed to fetch top merchants data"
        }), 500

@superadmin_bp.route('/analytics/merchant-performance-details', methods=['GET'])
@super_admin_role_required
def get_merchant_performance_details():
    """Get detailed merchant performance metrics including revenue, orders, ratings, and product metrics"""
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        months = request.args.get('months', default=12, type=int)
        result = PerformanceAnalyticsController.get_merchant_performance_details(months)
        return jsonify(result), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting merchant performance details: {e}")
        return jsonify({
            "status": "error",
            "message": "Failed to retrieve merchant performance details"
        }), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/analytics/conversion-rate', methods=['GET'])
@super_admin_role_required
def get_conversion_rate():
    """Get conversion rate analytics (visits to orders)"""
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        months = request.args.get('months', default=12, type=int)
        result = PerformanceAnalyticsController.get_conversion_rate(months)
        return jsonify(result), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting conversion rate: {e}")
        return jsonify({
            "status": "error",
            "message": "Failed to retrieve conversion rate data"
        }), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/analytics/hourly', methods=['GET'])
@super_admin_role_required
def get_hourly_analytics():
    try:
        from controllers.superadmin.performance_analytics import PerformanceAnalyticsController
        return PerformanceAnalyticsController.get_hourly_analytics()
    except Exception as e:
        current_app.logger.error(f"Error getting hourly analytics: {e}")
        return jsonify({
            "status": "error",
            "message": "Failed to retrieve hourly analytics data"
        }), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/monitoring/system/status', methods=['GET'])
@super_admin_role_required
def system_status_route():
    """Get current system status and uptime"""
    result = SystemMonitoringController.get_system_status()
    return jsonify(result), 200 if result['status'] == 'success' else 500

@superadmin_bp.route('/monitoring/system/response-times', methods=['GET'])
@super_admin_role_required
def response_times_route():
    """Get response time trends and averages"""
    hours = int(request.args.get('hours', 24))
    result = SystemMonitoringController.get_response_times(hours)
    return jsonify(result), 200 if result['status'] == 'success' else 500

@superadmin_bp.route('/monitoring/system/errors', methods=['GET'])
@super_admin_role_required
def error_distribution_route():
    """Get error distribution and details"""
    hours = int(request.args.get('hours', 24))
    result = SystemMonitoringController.get_error_distribution(hours)
    return jsonify(result), 200 if result['status'] == 'success' else 500

@superadmin_bp.route('/monitoring/system/service/<service_name>', methods=['GET'])
@super_admin_role_required
def service_status_route(service_name):
    """Get detailed status for a specific service"""
    hours = request.args.get('hours', default=24, type=int)
    return jsonify(SystemMonitoringController.get_service_status(service_name, hours))

@superadmin_bp.route('/monitoring/system/health', methods=['GET'])
@super_admin_role_required
def system_health_route():
    """Get overall system health status"""
    hours = int(request.args.get('hours', 1))
    result = SystemMonitoringController.get_system_health(hours)
    return jsonify(result), 200 if result['status'] == 'success' else 500

@superadmin_bp.route('/users', methods=['GET', 'OPTIONS'])
@cross_origin()
@super_admin_role_required
def list_users():
    try:
        from controllers.superadmin.user_management_controller import get_all_users
        return get_all_users()
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@superadmin_bp.route('/users/<int:user_id>/status', methods=['PUT', 'OPTIONS'])
@cross_origin()
@super_admin_role_required
def update_user_status_route(user_id):
    try:
        from controllers.superadmin.user_management_controller import update_user_status
        return update_user_status(user_id)
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@superadmin_bp.route('/users/<int:user_id>/profile', methods=['GET', 'OPTIONS'])
@cross_origin()
@super_admin_role_required
def get_user_profile_route(user_id):
    try:
        from controllers.superadmin.user_management_controller import get_user_profile
        return get_user_profile(user_id)
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

    


# --- GST Rule Management Routes ---
@superadmin_bp.route('/gst-rules', methods=['GET'])
@super_admin_role_required
def list_gst_rules_route():
    try:
        rules = GSTManagementController.list_all_rules()
        return jsonify(rules), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"API Error listing GST rules: {e}")
        return jsonify({"message": "Failed to retrieve GST rules."}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/gst-rules/<int:rule_id>', methods=['GET'])
@super_admin_role_required
def get_gst_rule_route(rule_id):
    try:
        rule = GSTManagementController.get_rule(rule_id)
        return jsonify(rule), HTTPStatus.OK
    except NotFound as e:
        return jsonify({"message": str(e)}), HTTPStatus.NOT_FOUND
    except Exception as e:
        current_app.logger.error(f"API Error getting GST rule {rule_id}: {e}")
        return jsonify({"message": "Failed to retrieve GST rule."}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/gst-rules', methods=['POST'])
@super_admin_role_required
def create_gst_rule_route():
    admin_id = get_jwt_identity()
    json_data = request.get_json()
    if not json_data:
        return jsonify({"message": "No input data provided"}), HTTPStatus.BAD_REQUEST
    
    schema = CreateGSTRuleSchema()
    try:
        validated_data = schema.load(json_data)
        created_rule = GSTManagementController.create_rule(validated_data, admin_id)
        return jsonify(created_rule), HTTPStatus.CREATED
    except ValidationError as err:
        return jsonify({"message": "Validation failed", "errors": err.messages}), HTTPStatus.BAD_REQUEST
    except BadRequest as e:
        return jsonify({"message": str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"API Error creating GST rule: {e}")
        return jsonify({"message": "Failed to create GST rule."}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/gst-rules/<int:rule_id>', methods=['PUT'])
@super_admin_role_required
def update_gst_rule_route(rule_id):
    admin_id = get_jwt_identity()
    json_data = request.get_json()
    if not json_data:
        return jsonify({"message": "No input data provided"}), HTTPStatus.BAD_REQUEST

    schema = UpdateGSTRuleSchema() # Use Update schema
    try:
        validated_data = schema.load(json_data)
        if not validated_data: # If validated_data is empty, nothing to update
             return jsonify({"message": "No valid fields provided for update."}), HTTPStatus.BAD_REQUEST
        updated_rule = GSTManagementController.update_rule(rule_id, validated_data, admin_id)
        return jsonify(updated_rule), HTTPStatus.OK
    except ValidationError as err:
        return jsonify({"message": "Validation failed", "errors": err.messages}), HTTPStatus.BAD_REQUEST
    except NotFound as e:
        return jsonify({"message": str(e)}), HTTPStatus.NOT_FOUND
    except BadRequest as e:
        return jsonify({"message": str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"API Error updating GST rule {rule_id}: {e}")
        return jsonify({"message": "Failed to update GST rule."}), HTTPStatus.INTERNAL_SERVER_ERROR

@superadmin_bp.route('/gst-rules/<int:rule_id>', methods=['DELETE'])
@super_admin_role_required
def delete_gst_rule_route(rule_id):
    try:
        GSTManagementController.delete_rule(rule_id)
        return '', HTTPStatus.NO_CONTENT # Or jsonify({"message": "Rule deleted"})
    except NotFound as e:
        return jsonify({"message": str(e)}), HTTPStatus.NOT_FOUND
    except BadRequest as e: # If controller raises BadRequest for FK constraint
        return jsonify({"message": str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"API Error deleting GST rule {rule_id}: {e}")
        return jsonify({"message": "Failed to delete GST rule."}), HTTPStatus.INTERNAL_SERVER_ERROR


#---Newletter------    
@superadmin_bp.route('/newsletter/subscribe', methods=['POST', 'OPTIONS'])
@cross_origin()
def subscribe_newsletter():
    return newsletter_controller.subscribe_email()

@superadmin_bp.route('/newsletter/subscribers', methods=['GET'])
@super_admin_role_required
def get_all_subscribers():
    return newsletter_controller.list_subscribers()

#--- Merchant Transaction Related ----
@superadmin_bp.route('/merchant-transactions', methods=['GET'])
@super_admin_role_required
def get_all_merchant_transactions():
    filters = {
        "status": request.args.get("status"),
        "merchant_id": request.args.get("merchant_id"),
        "from_date": request.args.get("from"),
        "to_date": request.args.get("to")
    }
    txns = list_all_transactions(filters)
    return jsonify([txn.serialize() for txn in txns]), 200

@superadmin_bp.route('/merchant-transactions/<int:txn_id>', methods=['GET'])
@super_admin_role_required
def get_merchant_transaction(txn_id):
    txn = get_transaction_by_id(txn_id)
    return jsonify(txn.serialize()), 200

@superadmin_bp.route('/merchant-transactions/<int:txn_id>', methods=['PUT'])
@super_admin_role_required
def mark_merchant_transaction_paid(txn_id):
    txn = mark_as_paid(txn_id)
    if txn is None:
        return jsonify({"message": "Already paid."}), 400
    return jsonify({"message": "Marked as paid", "transaction": txn.serialize()}), 200

