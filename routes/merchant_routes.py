# routes/merchant_routes.py
from flask import Blueprint, request, jsonify, current_app
from controllers.merchant.merchant_settings_controller import MerchantSettingsController
from http import HTTPStatus
from auth.utils import merchant_role_required, super_admin_role_required
from common.database import db
import cloudinary
import cloudinary.uploader
from werkzeug.exceptions import NotFound, ClientDisconnected
from services.s3_service import get_s3_service
from models.product import Product
from models.product_stock import ProductStock
from controllers.merchant.brand_request_controller import MerchantBrandRequestController
from controllers.merchant.brand_controller         import MerchantBrandController
from controllers.merchant.category_controller      import MerchantCategoryController
from controllers.merchant.category_attribute_controller import MerchantCategoryAttributeController
from controllers.merchant.product_controller       import MerchantProductController
from controllers.merchant.product_meta_controller  import MerchantProductMetaController
from controllers.merchant.product_tax_controller   import MerchantProductTaxController
from controllers.merchant.product_shipping_controller import MerchantProductShippingController
from controllers.merchant.product_media_controller import MerchantProductMediaController
from controllers.merchant.dimension_preset_controller import MerchantDimensionPresetController
from controllers.merchant.product_attribute_controller import MerchantProductAttributeController
from controllers.merchant.product_placement_controller import MerchantProductPlacementController
from controllers.merchant.tax_category_controller  import MerchantTaxCategoryController
from controllers.merchant.product_stock_controller import MerchantProductStockController
from controllers.merchant.merchant_profile_controller import MerchantProfileController
from flask_jwt_extended import get_jwt_identity, jwt_required
from controllers.merchant.order_controller import MerchantOrderController
from auth.models.models import MerchantProfile
from datetime import datetime
from controllers.merchant.dashboard_controller import MerchantDashboardController
from controllers.merchant.report_controller import MerchantReportController
from controllers.merchant.report_export_controller import MerchantReportExportController
from controllers.merchant.inventory_export_controller import MerchantInventoryExportController
from controllers.merchant.merchant_settings_controller import MerchantSettingsController
from controllers.merchant.live_stream_controller import MerchantLiveStreamController
import logging
from models.enums import MediaType


# Only allow images - videos removed for now
ALLOWED_MEDIA_EXTENSIONS = {'png', 'jpg', 'jpeg', 'svg', 'gif', 'webp'}

# File size limits (in bytes)
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB for images

def allowed_media_file(filename):
    """
    Check if the given filename has an allowed media file extension
    ---
    tags:
      - Merchant - Media
    security:
      - Bearer: []
    parameters:
      - in: path  
        name: filename
        type: string
        required: true
        description: Name of the file to check
    responses:
      type: boolean
      description: True if the file extension is allowed, False otherwise
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_MEDIA_EXTENSIONS

def calculate_discount_percentage(cost_price, selling_price):
    """Calculate discount percentage based on cost and selling price."""
    if not cost_price or not selling_price or cost_price <= 0:
        return 0
    return round(((cost_price - selling_price) / cost_price) * 100, 2)

merchant_dashboard_bp = Blueprint('merchant_dashboard_bp', __name__)

# General OPTIONS handler for CORS preflight requests
@merchant_dashboard_bp.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@merchant_dashboard_bp.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    """Handle OPTIONS request for CORS preflight"""
    response = jsonify({})
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response, 200

# ── BRAND REQUESTS ───────────────────────────────────────────────────────────────
@merchant_dashboard_bp.route('/brand-requests', methods=['GET'])
@merchant_role_required
def list_brand_requests():
    """
    Get all brand requests made by the merchant
    ---
    tags:
      - Merchant - Brand Requests
    security:
      - Bearer: []
    responses:
      200:
        description: List of brand requests retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              request_id:
                type: integer
              brand_name:
                type: string
              status:
                type: string
                enum: [PENDING, APPROVED, REJECTED]
              created_at:
                type: string
                format: date-time
              updated_at:
                type: string
                format: date-time
      500:
        description: Internal server error
    """
    items = MerchantBrandRequestController.list_all()
    return jsonify([i.serialize() for i in items]), 200

@merchant_dashboard_bp.route('/brand-requests', methods=['POST'])
@merchant_role_required
def create_brand_request():
    """
    Create a new brand request
    ---
    tags:
      - Merchant - Brand Requests
    security:
      - Bearer: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - brand_name
            properties:
              brand_name:
                type: string
                description: Name of the brand to request
              description:
                type: string
                description: Optional description of the brand
              website:
                type: string
                format: uri
                description: Optional website URL of the brand
    responses:
      201:
        description: Brand request created successfully
        schema:
          type: object
          properties:
            request_id:
              type: integer
            brand_name:
              type: string
            status:
              type: string
              enum: [PENDING]
            created_at:
              type: string
              format: date-time
            updated_at:
              type: string
              format: date-time
      400:
        description: Invalid request data
      500:
        description: Internal server error
    """
    data = request.get_json()
    br = MerchantBrandRequestController.create(data)
    return jsonify(br.serialize()), 201

# ── BRANDS ────────────────────────────────────────────────────────────────────────
@merchant_dashboard_bp.route('/brands', methods=['GET'])
@merchant_role_required
def list_brands():
    """
    Get all brands available to the merchant
    ---
    tags:
      - Merchant - Brands
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
              icon_url:
                type: string
                nullable: true
              description:
                type: string
                nullable: true
              website:
                type: string
                format: uri
                nullable: true
              status:
                type: string
                enum: [ACTIVE, INACTIVE]
      500:
        description: Internal server error
    """
    items = MerchantBrandController.list_all()
    return jsonify([i.serialize() for i in items]), 200

# ── CATEGORIES ───────────────────────────────────────────────────────────────────

@merchant_dashboard_bp.route('/categories', methods=['GET'])
@merchant_role_required
def list_merchant_categories():
    """
    Get all categories available to the merchant
    ---
    tags:
      - Merchant - Categories
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
              category_id:
                type: integer
              name:
                type: string
              slug:
                type: string
              parent_id:
                type: integer
                nullable: true
              description:
                type: string
                nullable: true
              image_url:
                type: string
                nullable: true
              status:
                type: string
                enum: [ACTIVE, INACTIVE]
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        cats = MerchantCategoryController.list_all()
       
        return jsonify([c.serialize() for c in cats]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error listing categories: {e}")
        return jsonify({'message': 'Failed to retrieve categories.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/attributes/<int:aid>/values', methods=['GET'])
@merchant_role_required
def list_attribute_values(aid):
    """
    Get all values for a specific attribute
    ---
    tags:
      - Merchant - Attributes
    security:
      - Bearer: []
    parameters:
      - in: path
        name: aid
        type: integer
        required: true
        description: Attribute ID
    responses:
      200:
        description: List of attribute values retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              value_code:
                type: string
              value_label:
                type: string
      404:
        description: Attribute not found
      500:
        description: Internal server error
    """
    try:
        from controllers.merchant.attribute_controller import MerchantAttributeController
        values = MerchantAttributeController.get_values(aid)
        return jsonify([v.serialize() for v in values]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error fetching values for attribute {aid}: {e}")
        if hasattr(e, 'code') and isinstance(e.code, int):
            return jsonify({'message': getattr(e, 'description', str(e))}), e.code
        return jsonify({'message': 'An error occurred while retrieving attribute values.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/categories/<int:cid>/attributes', methods=['GET'])
@merchant_role_required
def list_attributes_for_merchant_category_view(cid):
    """
    Get all attributes associated with a specific category
    ---
    tags:
      - Merchant - Categories
    security:
      - Bearer: []
    parameters:
      - in: path
        name: cid
        type: integer
        required: true
        description: Category ID
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
              name:
                type: string
              type:
                type: string
              options:
                type: array
                items:
                  type: string
              help_text:
                type: string
              required:
                type: boolean
      404:
        description: Category not found
      500:
        description: Internal server error
    """
    try:
        attributes = MerchantCategoryAttributeController.get_attributes_for_category(cid)
        return jsonify(attributes), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error fetching attributes for category {cid}: {e}")
        if hasattr(e, 'code') and isinstance(e.code, int):
            return jsonify({'message': getattr(e, 'description', str(e))}), e.code
        return jsonify({'message': 'An error occurred while retrieving category attributes.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/categories/<int:cid>', methods=['GET'])
@merchant_role_required
def get_category(cid):
    """
    Get category details by ID
    ---
    tags:
      - Merchant - Categories
    security:
      - Bearer: []
    parameters:
      - in: path
        name: cid
        type: integer
        required: true
        description: Category ID
    responses:
      200:
        description: Category details retrieved successfully
        schema:
          type: object
          properties:
            category_id:
              type: integer
            name:
              type: string
            slug:
              type: string
            parent_id:
              type: integer
              nullable: true
      404:
        description: Category not found
      500:
        description: Internal server error
    """
    try:
        category = MerchantCategoryController.get(cid)
        return jsonify(category), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error getting category {cid}: {e}")
        if hasattr(e, 'code') and isinstance(e.code, int):
            return jsonify({'message': getattr(e, 'description', str(e))}), e.code
        return jsonify({'message': 'Failed to retrieve category details.'}), HTTPStatus.INTERNAL_SERVER_ERROR

# ── PRODUCTS ─────────────────────────────────────────────────────────────────────
@merchant_dashboard_bp.route('/products', methods=['GET'])
@merchant_role_required
def list_products():
    """
    Get all products for the merchant
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - name: page
        in: query
        type: integer
        default: 1
        description: Page number for pagination
      - name: per_page
        in: query
        type: integer
        default: 50
        description: Number of items per page
      - name: search
        in: query
        type: string
        description: Search term for product name or SKU
      - name: category
        in: query
        type: string
        description: Filter by category (ID or slug)
      - name: brand
        in: query
        type: string
        description: Filter by brand (ID or slug)
      - name: status
        in: query
        type: string
        enum: [DRAFT, PENDING, APPROVED, REJECTED]
        description: Filter by product status
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
              sku:
                type: string
              selling_price:
                type: number
                format: float
              cost_price:
                type: number
                format: float
              stock_qty:
                type: integer
              status:
                type: string
                enum: [DRAFT, PENDING, APPROVED, REJECTED]
              category:
                type: object
                properties:
                  category_id:
                    type: integer
                  name:
                    type: string
              brand:
                type: object
                properties:
                  brand_id:
                    type: integer
                  name:
                    type: string
      500:
        description: Internal server error
    """
    ps = MerchantProductController.list_all()
    return jsonify([p.serialize() for p in ps]), 200

@merchant_dashboard_bp.route('/products', methods=['POST'])
@merchant_role_required
def create_product():
    """
    Create a new product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - product_name
              - sku
              - selling_price
              - category_id
              - brand_id
            properties:
              product_name:
                type: string
                description: Name of the product
              sku:
                type: string
                description: Unique SKU for the product
              description:
                type: string
                description: Product description
              selling_price:
                type: number
                format: float
                minimum: 0
                description: Product selling price
              cost_price:
                type: number
                format: float
                minimum: 0
                description: Product cost price
              category_id:
                type: integer
                description: ID of the product category
              brand_id:
                type: integer
                description: ID of the product brand
              stock_qty:
                type: integer
                minimum: 0
                default: 0
                description: Initial stock quantity
              low_stock_threshold:
                type: integer
                minimum: 0
                default: 5
                description: Threshold for low stock alerts
    responses:
      201:
        description: Product created successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            product_name:
              type: string
            sku:
              type: string
            selling_price:
              type: number
              format: float
            cost_price:
              type: number
              format: float
            stock_qty:
              type: integer
            status:
              type: string
              enum: [DRAFT]
            category_id:
              type: integer
            brand_id:
              type: integer
      400:
        description: Invalid request data
        schema:
          type: object
          properties:
            message:
              type: string
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'message': 'No data provided'}), HTTPStatus.BAD_REQUEST
        
        # Calculate discount percentage if cost_price and selling_price are provided
        if 'cost_price' in data and 'selling_price' in data:
            cost_price = float(data['cost_price'])
            selling_price = float(data['selling_price'])
            data['discount_pct'] = calculate_discount_percentage(cost_price, selling_price)
        
        p = MerchantProductController.create(data)
        return jsonify(p.serialize()), HTTPStatus.CREATED
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error creating product: {e}")
        return jsonify({'message': 'Failed to create product'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/<int:pid>/variants', methods=['POST'])
@merchant_role_required
def create_product_variant(pid):
    """
    Create a variant for a parent product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Parent product ID
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - sku
              - stock_qty
              - selling_price
            properties:
              sku:
                type: string
                description: Unique SKU for the variant
              stock_qty:
                type: integer
                minimum: 0
                description: Initial stock quantity
              selling_price:
                type: number
                minimum: 0
                description: Variant's selling price
              cost_price:
                type: number
                minimum: 0
                description: Optional variant's cost price (defaults to parent's cost price)
              attributes:
                type: object
                description: Dictionary of attribute values for the variant
                additionalProperties:
                  type: string
    responses:
      201:
        description: Variant created successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            parent_product_id:
              type: integer
            sku:
              type: string
            stock_qty:
              type: integer
            selling_price:
              type: number
            attributes:
              type: object
      400:
        description: Invalid request data
      404:
        description: Parent product not found
      500:
        description: Internal server error
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'message': 'No data provided'}), HTTPStatus.BAD_REQUEST

        # Validate required fields
        required_fields = ['sku', 'stock_qty', 'selling_price']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                'message': f'Missing required fields: {", ".join(missing_fields)}',
                'error': 'MISSING_FIELDS'
            }), HTTPStatus.BAD_REQUEST

        # Validate numeric fields
        try:
            data['stock_qty'] = int(data['stock_qty'])
            data['selling_price'] = float(data['selling_price'])
            if 'cost_price' in data:
                data['cost_price'] = float(data['cost_price'])
        except ValueError as e:
            return jsonify({
                'message': f'Invalid numeric value: {str(e)}',
                'error': 'INVALID_NUMERIC'
            }), HTTPStatus.BAD_REQUEST

        # Validate minimum values
        if data['stock_qty'] < 0:
            return jsonify({
                'message': 'Stock quantity cannot be negative',
                'error': 'INVALID_STOCK'
            }), HTTPStatus.BAD_REQUEST
        if data['selling_price'] < 0:
            return jsonify({
                'message': 'Selling price cannot be negative',
                'error': 'INVALID_PRICE'
            }), HTTPStatus.BAD_REQUEST

        # Validate attributes if provided
        if 'attributes' in data:
            if not isinstance(data['attributes'], dict):
                return jsonify({
                    'message': 'Attributes must be a dictionary',
                    'error': 'INVALID_ATTRIBUTES'
                }), HTTPStatus.BAD_REQUEST

        variant = MerchantProductController.create_variant(pid, data)
        return jsonify(variant.serialize()), HTTPStatus.CREATED

    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error creating variant for product {pid}: {e}")
        return jsonify({'message': 'Failed to create product variant'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/<int:pid>', methods=['GET'])
@merchant_role_required
def get_product(pid):
    """
    Get detailed information about a specific product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    responses:
      200:
        description: Product details retrieved successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            product_name:
              type: string
            sku:
              type: string
            description:
              type: string
            selling_price:
              type: number
              format: float
            cost_price:
              type: number
              format: float
            stock_qty:
              type: integer
            status:
              type: string
              enum: [DRAFT, PENDING, APPROVED, REJECTED]
            category:
              type: object
              properties:
                category_id:
                  type: integer
                name:
                  type: string
                slug:
                  type: string
            brand:
              type: object
              properties:
                brand_id:
                  type: integer
                name:
                  type: string
                slug:
                  type: string
            variants:
              type: array
              items:
                type: object
                properties:
                  variant_id:
                    type: integer
                  sku:
                    type: string
                  attributes:
                    type: object
                  stock_qty:
                    type: integer
                  selling_price:
                    type: number
                    format: float
      404:
        description: Product not found
      500:
        description: Internal server error
    """
    p = MerchantProductController.get(pid)
    return jsonify(p.serialize()), 200

@merchant_dashboard_bp.route('/products/<int:pid>', methods=['PUT'])
@merchant_role_required
def update_product(pid):
    """
    Update an existing product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              product_name:
                type: string
                description: Updated product name
              description:
                type: string
                description: Updated product description
              selling_price:
                type: number
                format: float
                minimum: 0
                description: Updated selling price
              cost_price:
                type: number
                format: float
                minimum: 0
                description: Updated cost price
              category_id:
                type: integer
                description: Updated category ID
              brand_id:
                type: integer
                description: Updated brand ID
              status:
                type: string
                enum: [DRAFT, PENDING]
                description: Updated product status
    responses:
      200:
        description: Product updated successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            product_name:
              type: string
            sku:
              type: string
            selling_price:
              type: number
              format: float
            cost_price:
              type: number
              format: float
            status:
              type: string
              enum: [DRAFT, PENDING]
            category_id:
              type: integer
            brand_id:
              type: integer
      400:
        description: Invalid request data
        schema:
          type: object
          properties:
            message:
              type: string
      404:
        description: Product not found
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'message': 'No data provided'}), HTTPStatus.BAD_REQUEST
        
        # Calculate discount percentage if cost_price and selling_price are provided
        if 'cost_price' in data and 'selling_price' in data:
            cost_price = float(data['cost_price'])
            selling_price = float(data['selling_price'])
            data['discount_pct'] = calculate_discount_percentage(cost_price, selling_price)
        
        p = MerchantProductController.update(pid, data)
        return jsonify(p.serialize()), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error updating product {pid}: {e}")
        return jsonify({'message': 'Failed to update product'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/<int:pid>', methods=['DELETE'])
@merchant_role_required
def delete_product(pid):
    """
    Delete a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID to delete
    responses:
      200:
        description: Product deleted successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            product_name:
              type: string
            sku:
              type: string
            status:
              type: string
              enum: [DELETED]
      404:
        description: Product not found
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    p = MerchantProductController.delete(pid)
    return jsonify(p.serialize()), 200



# PRODUCT META
@merchant_dashboard_bp.route('/products/<int:pid>/meta', methods=['GET'])
@merchant_role_required
def get_product_meta(pid):
    """
    Get meta information for a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    responses:
      200:
        description: Product meta information retrieved successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            short_desc:
              type: string
              description: Short description of the product
            full_desc:
              type: string
              description: Full detailed description of the product
            meta_title:
              type: string
              description: SEO meta title
            meta_description:
              type: string
              description: SEO meta description
            meta_keywords:
              type: string
              description: SEO meta keywords
      404:
        description: Product not found
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    pm = MerchantProductMetaController.get(pid)
    return jsonify(pm.serialize()), 200

@merchant_dashboard_bp.route('/products/<int:pid>/meta', methods=['POST','PUT'])
@merchant_role_required
def upsert_product_meta(pid):
    """
    Create or update product meta information
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - short_desc
              - full_desc
            properties:
              short_desc:
                type: string
                description: Short description of the product
              full_desc:
                type: string
                description: Full detailed description of the product
              meta_title:
                type: string
                description: SEO meta title
              meta_description:
                type: string
                description: SEO meta description
              meta_keywords:
                type: string
                description: SEO meta keywords
    responses:
      200:
        description: Product meta information updated successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            short_desc:
              type: string
            full_desc:
              type: string
            meta_title:
              type: string
            meta_description:
              type: string
            meta_keywords:
              type: string
      400:
        description: Invalid request data
        schema:
          type: object
          properties:
            message:
              type: string
            error:
              type: string
              enum: [MISSING_FIELDS, EMPTY_FIELD]
      404:
        description: Product not found
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
            error:
              type: string
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'message': 'No data provided'}), HTTPStatus.BAD_REQUEST

        # Validate required fields
        required_fields = ['short_desc', 'full_desc']
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({
                'message': f'Missing required fields: {", ".join(missing_fields)}',
                'error': 'MISSING_FIELDS'
            }), HTTPStatus.BAD_REQUEST

        # Ensure fields are not empty strings
        for field in required_fields:
            if not data[field].strip():
                return jsonify({
                    'message': f'{field} cannot be empty',
                    'error': 'EMPTY_FIELD'
                }), HTTPStatus.BAD_REQUEST

        pm = MerchantProductMetaController.upsert(pid, data)
        return jsonify(pm.serialize()), 200
    except Exception as e:
        current_app.logger.error(f"Error updating product meta for product {pid}: {e}")
        return jsonify({
            'message': 'Failed to update product meta data',
            'error': str(e)
        }), HTTPStatus.INTERNAL_SERVER_ERROR

# PRODUCT TAX
@merchant_dashboard_bp.route('/products/<int:pid>/tax', methods=['GET'])
@merchant_role_required
def get_product_tax(pid):
    """
    Get tax information for a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    responses:
      200:
        description: Product tax information retrieved successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            tax_rate:
              type: string
              description: Tax rate as a decimal string (e.g., "0.20" for 20%)
      404:
        description: Product not found
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    t = MerchantProductTaxController.get(pid)
    return jsonify({'product_id': t.product_id, 'tax_rate': str(t.tax_rate)}), 200

@merchant_dashboard_bp.route('/products/<int:pid>/tax', methods=['POST','PUT'])
@merchant_role_required
def upsert_product_tax(pid):
    """
    Create or update tax information for a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - tax_rate
            properties:
              tax_rate:
                type: number
                format: float
                minimum: 0
                maximum: 1
                description: Tax rate as a decimal (e.g., 0.20 for 20%)
    responses:
      200:
        description: Product tax information updated successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            tax_rate:
              type: string
              description: Tax rate as a decimal string
      400:
        description: Invalid request data
        schema:
          type: object
          properties:
            message:
              type: string
      404:
        description: Product not found
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    data = request.get_json()
    t = MerchantProductTaxController.upsert(pid, data)
    return jsonify({'product_id': t.product_id, 'tax_rate': str(t.tax_rate)}), 200

# PRODUCT SHIPPING
@merchant_dashboard_bp.route('/products/<int:pid>/shipping', methods=['GET'])
@merchant_role_required
def get_product_shipping(pid):
    """
    Get shipping information for a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    responses:
      200:
        description: Product shipping information retrieved successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            weight:
              type: number
              format: float
              description: Product weight in kilograms
            length:
              type: number
              format: float
              description: Product length in centimeters
            width:
              type: number
              format: float
              description: Product width in centimeters
            height:
              type: number
              format: float
              description: Product height in centimeters
            shipping_class:
              type: string
              description: Shipping class/category
            free_shipping:
              type: boolean
              description: Whether the product qualifies for free shipping
      404:
        description: Product not found
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    s = MerchantProductShippingController.get(pid)
    return jsonify(s.serialize()), 200

@merchant_dashboard_bp.route('/products/<int:pid>/shipping', methods=['POST','PUT'])
@merchant_role_required
def upsert_product_shipping(pid):
    """
    Create or update shipping information for a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - weight
              - length
              - width
              - height
            properties:
              weight:
                type: number
                format: float
                minimum: 0
                description: Product weight in kilograms
              length:
                type: number
                format: float
                minimum: 0
                description: Product length in centimeters
              width:
                type: number
                format: float
                minimum: 0
                description: Product width in centimeters
              height:
                type: number
                format: float
                minimum: 0
                description: Product height in centimeters
              shipping_class:
                type: string
                description: Shipping class/category
              free_shipping:
                type: boolean
                description: Whether the product qualifies for free shipping
    responses:
      200:
        description: Product shipping information updated successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            weight:
              type: number
              format: float
            length:
              type: number
              format: float
            width:
              type: number
              format: float
            height:
              type: number
              format: float
            shipping_class:
              type: string
            free_shipping:
              type: boolean
      400:
        description: Invalid request data
        schema:
          type: object
          properties:
            message:
              type: string
      404:
        description: Product not found
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    data = request.get_json()
    s = MerchantProductShippingController.upsert(pid, data)
    return jsonify(s.serialize()), 200

# DIMENSION PRESETS
@merchant_dashboard_bp.route('/dimension-presets', methods=['GET'])
@merchant_role_required
@jwt_required()
def list_dimension_presets():
    """
    Get all dimension presets for the current merchant
    ---
    tags:
      - Merchant - Dimension Presets
    security:
      - Bearer: []
    responses:
      200:
        description: List of dimension presets retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              preset_id:
                type: integer
              merchant_id:
                type: integer
              name:
                type: string
              length_cm:
                type: number
              width_cm:
                type: number
              height_cm:
                type: number
              weight_kg:
                type: number
              shipping_class:
                type: string
              description:
                type: string
              created_at:
                type: string
              updated_at:
                type: string
      500:
        description: Internal server error
    """
    presets = MerchantDimensionPresetController.list_all()
    return jsonify([preset.serialize() for preset in presets]), 200

@merchant_dashboard_bp.route('/dimension-presets/<int:preset_id>', methods=['GET'])
@merchant_role_required
@jwt_required()
def get_dimension_preset(preset_id):
    """
    Get a specific dimension preset by ID
    ---
    tags:
      - Merchant - Dimension Presets
    security:
      - Bearer: []
    parameters:
      - in: path
        name: preset_id
        type: integer
        required: true
        description: Dimension preset ID
    responses:
      200:
        description: Dimension preset retrieved successfully
      404:
        description: Preset not found
      500:
        description: Internal server error
    """
    preset = MerchantDimensionPresetController.get(preset_id)
    return jsonify(preset.serialize()), 200

@merchant_dashboard_bp.route('/dimension-presets', methods=['POST'])
@merchant_role_required
@jwt_required()
def create_dimension_preset():
    """
    Create a new dimension preset
    ---
    tags:
      - Merchant - Dimension Presets
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
              - length_cm
              - width_cm
              - height_cm
              - weight_kg
            properties:
              name:
                type: string
                description: Name of the dimension preset
              length_cm:
                type: number
                description: Length in centimeters
              width_cm:
                type: number
                description: Width in centimeters
              height_cm:
                type: number
                description: Height in centimeters
              weight_kg:
                type: number
                description: Weight in kilograms
              shipping_class:
                type: string
                description: Shipping class (optional)
              description:
                type: string
                description: Optional description
    responses:
      201:
        description: Dimension preset created successfully
      400:
        description: Invalid request data
      500:
        description: Internal server error
    """
    data = request.get_json()
    preset = MerchantDimensionPresetController.create(data)
    return jsonify(preset.serialize()), 201

@merchant_dashboard_bp.route('/dimension-presets/<int:preset_id>', methods=['PUT'])
@merchant_role_required
@jwt_required()
def update_dimension_preset(preset_id):
    """
    Update an existing dimension preset
    ---
    tags:
      - Merchant - Dimension Presets
    security:
      - Bearer: []
    parameters:
      - in: path
        name: preset_id
        type: integer
        required: true
        description: Dimension preset ID
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              name:
                type: string
              length_cm:
                type: number
              width_cm:
                type: number
              height_cm:
                type: number
              weight_kg:
                type: number
              shipping_class:
                type: string
              description:
                type: string
    responses:
      200:
        description: Dimension preset updated successfully
      400:
        description: Invalid request data
      404:
        description: Preset not found
      500:
        description: Internal server error
    """
    data = request.get_json()
    preset = MerchantDimensionPresetController.update(preset_id, data)
    return jsonify(preset.serialize()), 200

@merchant_dashboard_bp.route('/dimension-presets/<int:preset_id>', methods=['DELETE'])
@merchant_role_required
@jwt_required()
def delete_dimension_preset(preset_id):
    """
    Delete a dimension preset (soft delete)
    ---
    tags:
      - Merchant - Dimension Presets
    security:
      - Bearer: []
    parameters:
      - in: path
        name: preset_id
        type: integer
        required: true
        description: Dimension preset ID
    responses:
      200:
        description: Dimension preset deleted successfully
      404:
        description: Preset not found
      500:
        description: Internal server error
    """
    preset = MerchantDimensionPresetController.delete(preset_id)
    return jsonify({'message': 'Dimension preset deleted successfully', 'preset': preset.serialize()}), 200

# PRODUCT MEDIA
@merchant_dashboard_bp.route('/products/<int:pid>/media', methods=['GET'])
@merchant_role_required
def list_product_media(pid):
    """
    Get all media files associated with a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    responses:
      200:
        description: List of media files retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              media_id:
                type: integer
              product_id:
                type: integer
              url:
                type: string
                format: uri
              type:
                type: string
                enum: [IMAGE, VIDEO]
              sort_order:
                type: integer
              created_at:
                type: string
                format: date-time
      404:
        description: Product not found
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        m = MerchantProductMediaController.list(pid)
        return jsonify([x.serialize() for x in m]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error listing media for product {pid}: {e}")
        if hasattr(e, 'code') and isinstance(e.code, int):
            return jsonify({'message': getattr(e, 'description', str(e))}), e.code
        return jsonify({'message': "Failed to retrieve product media."}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/<int:pid>/media/stats', methods=['GET'])
@merchant_role_required
def get_product_media_stats(pid):
    """
    Get statistics about media files associated with a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    responses:
      200:
        description: Media statistics retrieved successfully
        schema:
          type: object
          properties:
            total_count:
              type: integer
              description: Total number of media files
            image_count:
              type: integer
              description: Number of image files
            video_count:
              type: integer
              description: Number of video files
            max_allowed:
              type: integer
              description: Maximum number of media files allowed
            remaining_slots:
              type: integer
              description: Number of remaining media slots available
      404:
        description: Product not found
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        media_list = MerchantProductMediaController.list(pid)
        stats = {
            'total_count': len(media_list),
            'image_count': len([m for m in media_list if m.type == 'IMAGE']),
            'video_count': len([m for m in media_list if m.type == 'VIDEO']),
            'max_allowed': 5,  # This should match the frontend maxFiles
            'remaining_slots': 5 - len(media_list)
        }
        return jsonify(stats), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error getting media stats for product {pid}: {e}")
        return jsonify({'message': "Failed to retrieve product media statistics."}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/<int:pid>/media', methods=['POST'])
@merchant_role_required
def create_product_media(pid):
    """
    Upload and create a new media file for a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    requestBody:
      required: true
      content:
        multipart/form-data:
          schema:
            type: object
            required:
              - media_file
            properties:
              media_file:
                type: string
                format: binary
                description: Media file to upload (image or video)
              type:
                type: string
                enum: [IMAGE, VIDEO]
                description: Type of media (defaults to IMAGE for images, VIDEO for videos)
              sort_order:
                type: integer
                default: 0
                description: Order in which the media should appear
    responses:
      201:
        description: Media file uploaded and created successfully
        schema:
          type: object
          properties:
            media_id:
              type: integer
            product_id:
              type: integer
            url:
              type: string
              format: uri
            type:
              type: string
              enum: [IMAGE, VIDEO]
            sort_order:
              type: integer
            created_at:
              type: string
              format: date-time
      400:
        description: Invalid request data
        schema:
          type: object
          properties:
            message:
              type: string
              description: Error message explaining what went wrong
      404:
        description: Product not found
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        # ========== STAGE 1: REQUEST RECEIVED ==========
        print("=" * 80)
        print(f"[STAGE 1] ========== MEDIA UPLOAD REQUEST RECEIVED ==========")
        print(f"[STAGE 1] POST /products/{pid}/media: Request received")
        print(f"[STAGE 1] Content-Type: {request.content_type}")
        print(f"[STAGE 1] Content-Length: {request.content_length}")
        print(f"[STAGE 1] Request method: {request.method}")
        print(f"[STAGE 1] Request path: {request.path}")
        print(f"[STAGE 1] Remote address: {request.remote_addr}")
        print(f"[STAGE 1] Headers: {dict(request.headers)}")
        print("=" * 80)
        current_app.logger.info(f"[STAGE 1] Request received for product {pid}")
        
        # STEP 1: Validate file size BEFORE parsing (to avoid ClientDisconnected and provide clear errors)
        # Check Content-Length header first - this doesn't trigger multipart parsing
        content_length = request.content_length
        if content_length is None:
            print(f"[STAGE 1] ERROR: No Content-Length header")
            current_app.logger.warning(f"POST /products/{pid}/media: No Content-Length header")
            return jsonify({
                'message': 'File size could not be determined. Please ensure the file is being sent correctly.',
                'error_type': 'MissingContentLength'
            }), HTTPStatus.BAD_REQUEST
        
        # Convert to MB for user-friendly messages
        file_size_mb = content_length / (1024 * 1024)
        print(f"[STAGE 1] File size validated: {file_size_mb:.2f} MB ({content_length} bytes)")
        current_app.logger.info(f"[STAGE 1] File size: {file_size_mb:.2f} MB")
        
        # Initial check: reject if larger than image limit (only images are supported)
        if content_length > MAX_IMAGE_SIZE:
            print(f"[STAGE 1] ERROR: File too large")
            current_app.logger.error(f"POST /products/{pid}/media: File too large: {file_size_mb:.2f} MB (max: {MAX_IMAGE_SIZE / (1024 * 1024):.0f} MB)")
            return jsonify({
                'message': f'File is too large ({file_size_mb:.2f} MB). Maximum allowed size is {MAX_IMAGE_SIZE / (1024 * 1024):.0f} MB for images.',
                'error_type': 'FileTooLarge',
                'file_size_mb': round(file_size_mb, 2),
                'max_size_mb': MAX_IMAGE_SIZE / (1024 * 1024)
            }), HTTPStatus.BAD_REQUEST
        
        print(f"[STAGE 1] File size check PASSED - proceeding to parse multipart data")
        
        # ========== STAGE 2: PARSE MULTIPART FORM DATA ==========
        print(f"[STAGE 2] Starting multipart form data parsing...")
        current_app.logger.info(f"[STAGE 2] Attempting to parse multipart form data")
        
        # IMPORTANT: Accessing request.files triggers multipart parsing which can cause ClientDisconnected
        # if the client closes the connection during parsing. We need to handle this gracefully.
        # NOTE: Cloudinary uses the same approach (request.files['image']) and it works fine,
        # so the issue might be timing or how we access it. Let's try direct access like Cloudinary.
        try:
            print(f"[STAGE 2] Accessing request.files - this will trigger parsing...")
            print(f"[STAGE 2] Using direct access like Cloudinary does (request.files['media_file'])...")
            
            # Try direct access first (like Cloudinary does) - this is more efficient
            if 'media_file' not in request.files:
                print(f"[STAGE 2] ERROR: 'media_file' not in request.files")
                available_keys = list(request.files.keys()) if request.files else []
                print(f"[STAGE 2] Available keys: {available_keys}")
                current_app.logger.error(f"POST /products/{pid}/media: No media_file in request. Available keys: {available_keys}")
                return jsonify({
                    'message': 'No media_file in the request',
                    'available_keys': available_keys
                }), HTTPStatus.BAD_REQUEST
            
            # Direct access like Cloudinary (more efficient than .get())
            print(f"[STAGE 2] Getting file with direct access: request.files['media_file']...")
            file = request.files['media_file']
            print(f"[STAGE 2] Direct access completed. File object: {file}")
            
            if not file:
                # Check what files are available for debugging
                available_keys = list(request.files.keys()) if request.files else []
                current_app.logger.error(f"POST /products/{pid}/media: No media_file in request. Available keys: {available_keys}")
                return jsonify({
                    'message': 'No media_file in the request',
                    'available_keys': available_keys
                }), HTTPStatus.BAD_REQUEST
            
            print(f"[DEBUG] Successfully got file: {file.filename}")
            
        except ClientDisconnected as e:
            current_app.logger.error(f"Client disconnected while parsing form data: {e}")
            return jsonify({
                'message': 'Upload failed: Connection was closed during file upload. This may be due to network issues, timeout, or the file being too large. Please try again with a smaller file or check your network connection.',
                'error_type': 'ClientDisconnected',
                'error_details': 'The client disconnected while the server was reading the file. This usually indicates a network issue or timeout.'
            }), HTTPStatus.BAD_REQUEST
        except Exception as parse_error:
            # Catch any other parsing errors
            error_type = type(parse_error).__name__
            current_app.logger.error(f"Error parsing form data: {error_type}: {parse_error}", exc_info=True)
            if 'ClientDisconnected' in error_type or 'Disconnected' in error_type:
                return jsonify({
                    'message': 'Upload failed: Connection was closed during file upload.',
                    'error_type': error_type,
                    'error_details': str(parse_error)
                }), HTTPStatus.BAD_REQUEST
            raise

        if file.filename == '':
            current_app.logger.error(f"POST /products/{pid}/media: Empty filename")
            return jsonify({'message': 'No selected file'}), HTTPStatus.BAD_REQUEST
        
        # STEP 3: Validate file type - only images are allowed
        file_mimetype = file.mimetype.lower() if file.mimetype else ''
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        # Reject videos explicitly
        if file_mimetype.startswith('video/') or file_ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']:
            current_app.logger.error(f"POST /products/{pid}/media: Video files are not supported. File: {file.filename}")
            return jsonify({
                'message': 'Video files are not supported. Please upload only images (PNG, JPG, JPEG, GIF, WebP, SVG).',
                'error_type': 'InvalidFileType',
                'file_type': 'video',
                'filename': file.filename
            }), HTTPStatus.BAD_REQUEST
        
        # Validate file size for images
        content_length = request.content_length
        file_size_mb = content_length / (1024 * 1024) if content_length else 0
        
        if content_length and content_length > MAX_IMAGE_SIZE:
            current_app.logger.error(f"POST /products/{pid}/media: Image file too large: {file_size_mb:.2f} MB (max: {MAX_IMAGE_SIZE / (1024 * 1024):.0f} MB)")
            return jsonify({
                'message': f'Image file is too large ({file_size_mb:.2f} MB). Maximum allowed size is {MAX_IMAGE_SIZE / (1024 * 1024):.0f} MB.',
                'error_type': 'FileTooLarge',
                'file_type': 'image',
                'file_size_mb': round(file_size_mb, 2),
                'max_size_mb': MAX_IMAGE_SIZE / (1024 * 1024),
                'filename': file.filename
            }), HTTPStatus.BAD_REQUEST
        
        current_app.logger.info(f"POST /products/{pid}/media: Processing image file: {file.filename}, size: {file_size_mb:.2f} MB, mimetype: {file.mimetype}")

        
        if not allowed_media_file(file.filename):
            file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'no extension'
            current_app.logger.error(f"POST /products/{pid}/media: Invalid file extension '{file_ext}' for file: {file.filename}. Allowed: {ALLOWED_MEDIA_EXTENSIONS}")
            return jsonify({
                'message': f"Invalid file type. Allowed types: {', '.join(sorted(ALLOWED_MEDIA_EXTENSIONS))}",
                'received_extension': file_ext,
                'filename': file.filename
            }), HTTPStatus.BAD_REQUEST

        # Only images are supported - set media type to IMAGE
        media_type_str = "IMAGE"
        
        # Ensure mimetype is set correctly for images
        if not file_mimetype.startswith('image/'):
            file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            if file_ext in ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg']:
                # Set appropriate mimetype based on extension
                if file_ext == 'png':
                    file.mimetype = 'image/png'
                elif file_ext in ['jpg', 'jpeg']:
                    file.mimetype = 'image/jpeg'
                elif file_ext == 'gif':
                    file.mimetype = 'image/gif'
                elif file_ext == 'webp':
                    file.mimetype = 'image/webp'
                elif file_ext == 'svg':
                    file.mimetype = 'image/svg+xml'
            else:
                current_app.logger.error(f"Unsupported file content type: {file.mimetype} for file: {file.filename}")
                return jsonify({'message': f"Unsupported file type. Only images are allowed (PNG, JPG, JPEG, GIF, WebP, SVG). File: {file.filename}"}), HTTPStatus.BAD_REQUEST

       
        # Ensure media type is always IMAGE (videos are not supported)
        media_type_from_form = request.form.get('type', media_type_str).upper()
        if media_type_from_form != 'IMAGE':
            # Force to IMAGE if somehow VIDEO was passed
            media_type_from_form = 'IMAGE'


        sort_order_str = request.form.get('sort_order', '0')
        try:
            sort_order = int(sort_order_str)
        except ValueError:
            return jsonify({'message': 'Invalid sort_order format, must be an integer.'}), HTTPStatus.BAD_REQUEST
        
       
       
        # ========== STAGE 3: PREPARE FOR S3 UPLOAD ==========
        print(f"[STAGE 3] Preparing for S3 upload...")
        current_app.logger.info(f"[STAGE 3] Starting S3 upload preparation")
        
        # Use S3 for product images
        s3_upload_result = None
        media_url = None
        s3_key = None 
        
        # Upload images to S3
        try:
            print(f"[STAGE 3] Getting S3 service...")
            s3_service = get_s3_service()
            print(f"[STAGE 3] S3 service obtained. Bucket: {s3_service.bucket_name if hasattr(s3_service, 'bucket_name') else 'N/A'}")
            current_app.logger.info(f"[STAGE 3] S3 service initialized")
            
            print(f"[STAGE 3] Calling s3_service.upload_product_media()...")
            print(f"[STAGE 3] File object before upload: filename={file.filename}, type={type(file)}")
            current_app.logger.info(f"[STAGE 3] Starting S3 upload for file: {file.filename}")
            
            s3_upload_result = s3_service.upload_product_media(file, pid)
            
            print(f"[STAGE 3] S3 upload completed. Result: {s3_upload_result}")
            current_app.logger.info(f"[STAGE 3] S3 upload successful")
            
            print(f"[STAGE 3] S3 upload result received: {s3_upload_result}")
            
            if not s3_upload_result or not s3_upload_result.get('url'):
                print(f"[STAGE 3] ERROR: S3 upload succeeded but no URL returned")
                current_app.logger.error(f"S3 upload for product {media_type_from_form.lower()} succeeded but no URL was returned.")
                return jsonify({'message': 'S3 upload succeeded but did not return a URL.'}), HTTPStatus.INTERNAL_SERVER_ERROR
            
            # Store S3 key in public_id field for deletion later
            s3_key = s3_upload_result.get('s3_key')
            media_url = s3_upload_result.get('url')
            print(f"[STAGE 3] S3 key: {s3_key}")
            print(f"[STAGE 3] Media URL: {media_url}")
            current_app.logger.info(f"[STAGE 3] S3 upload successful. Key: {s3_key}, URL: {media_url}")
            
        except Exception as e:
            error_message = str(e)
            current_app.logger.error(f"S3 upload failed for product {media_type_from_form.lower()} (product {pid}): {error_message}", exc_info=True)
            # Return detailed error message to help with debugging
            return jsonify({
                'message': f"S3 {media_type_from_form.lower()} upload failed: {error_message}",
                'error_details': error_message,
                'file_name': file.filename if file else 'unknown'
            }), HTTPStatus.INTERNAL_SERVER_ERROR

        # ========== STAGE 4: SAVE TO DATABASE ==========
        print(f"[STAGE 4] Saving media to database...")
        current_app.logger.info(f"[STAGE 4] Preparing to save media to database")
       
        media_data = {
            'url': media_url,
            'type': media_type_from_form, 
            'sort_order': sort_order,
                'public_id': s3_key  # Store S3 key for images
        }
        print(f"[STAGE 4] Media data: {media_data}")

       
        try:
            print(f"[STAGE 4] Calling MerchantProductMediaController.create()...")
            new_media = MerchantProductMediaController.create(pid, media_data)
            print(f"[STAGE 4] SUCCESS: Media saved to database. Media ID: {new_media.id if hasattr(new_media, 'id') else 'N/A'}")
            current_app.logger.info(f"[STAGE 4] Media successfully saved to database")
            
            print(f"[STAGE 4] Returning success response...")
            return jsonify(new_media.serialize()), HTTPStatus.CREATED
        except ValueError as e: 
            # If DB save fails, delete uploaded file from S3
            if s3_upload_result:
                try:
                    get_s3_service().delete_product_media(s3_upload_result.get('s3_key'))
                except Exception:
                    pass  # Logged in delete function
            return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
        except RuntimeError as e: 
            # If DB save fails, delete uploaded file from S3
            if s3_upload_result:
                try:
                    get_s3_service().delete_product_media(s3_upload_result.get('s3_key'))
                except Exception:
                    pass  # Logged in delete function
            return jsonify({'message': str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
        except Exception as e:
            db.session.rollback() 
            current_app.logger.error(f"Error saving product media to DB for product {pid}: {e}")
            # If DB save fails, delete uploaded file from S3
            if s3_upload_result:
                try:
                    get_s3_service().delete_product_media(s3_upload_result.get('s3_key'))
                except Exception:
                    pass  # Logged in delete function
            return jsonify({'message': 'Failed to save product media information.'}), HTTPStatus.INTERNAL_SERVER_ERROR
    
    except Exception as e:
        # Catch any unexpected errors that weren't handled above
        error_message = str(e)
        error_type = type(e).__name__
        import traceback
        error_trace = traceback.format_exc()
        
        print(f"[ERROR] Unexpected error in create_product_media: {error_type}: {error_message}")
        print(f"[ERROR] Traceback:\n{error_trace}")
        
        current_app.logger.error(f"Unexpected error in create_product_media for product {pid}: {error_type}: {error_message}", exc_info=True)
        
        # Handle ClientDisconnected specially - this usually means the client closed the connection
        if error_type == 'ClientDisconnected':
            return jsonify({
                'message': 'Upload failed: Connection was closed before the file could be uploaded. Please try again with a smaller file or check your network connection.',
                'error_type': error_type,
                'error_details': 'The client disconnected during file upload. This may be due to network issues, file size, or timeout.'
            }), HTTPStatus.BAD_REQUEST
        
        return jsonify({
            'message': f'An unexpected error occurred: {error_message}',
            'error_type': error_type,
            'error_details': error_message
        }), HTTPStatus.INTERNAL_SERVER_ERROR


@merchant_dashboard_bp.route('/products/media/<int:mid>', methods=['DELETE'])
@merchant_role_required
def delete_product_media(mid):
    """
    Delete a media file associated with a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: mid
        type: integer
        required: true
        description: Media ID to delete
    responses:
      200:
        description: Media file deleted successfully
        schema:
          type: object
          properties:
            media_id:
              type: integer
            product_id:
              type: integer
            url:
              type: string
              format: uri
            type:
              type: string
              enum: [IMAGE, VIDEO]
            sort_order:
              type: integer
            created_at:
              type: string
              format: date-time
      404:
        description: Media file not found
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        m = MerchantProductMediaController.delete(mid)
        return jsonify(m.serialize()), HTTPStatus.OK 
    except Exception as e:
        current_app.logger.error(f"Merchant: Error deleting media {mid}: {e}")
        if hasattr(e, 'code') and isinstance(e.code, int):
            return jsonify({'message': getattr(e, 'description', str(e))}), e.code
        return jsonify({'message': "Failed to delete product media."}), HTTPStatus.INTERNAL_SERVER_ERROR


@merchant_dashboard_bp.route('/products/<int:pid>/media/<int:mid>/set-thumbnail', methods=['POST'])
@merchant_role_required
def set_product_media_thumbnail(pid, mid):
    """
    Set a media file as the thumbnail for a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
      - in: path
        name: mid
        type: integer
        required: true
        description: Media ID to set as thumbnail
    responses:
      200:
        description: Thumbnail set successfully
        schema:
          type: object
          properties:
            message:
              type: string
            media_id:
              type: integer
            is_thumbnail:
              type: boolean
      404:
        description: Product or media not found
      400:
        description: Invalid request (e.g., media is not an image)
      500:
        description: Internal server error
    """
    try:
        # Verify the media belongs to the product and is an image
        media = MerchantProductMediaController.get_by_id(mid)
        if not media or media.product_id != pid:
            return jsonify({'message': 'Media not found or does not belong to this product'}), HTTPStatus.NOT_FOUND
        
        # media.type is an enum (MediaType). Compare against MediaType.IMAGE
        if getattr(media, 'type', None) != MediaType.IMAGE:
            return jsonify({'message': 'Only images can be set as thumbnails'}), HTTPStatus.BAD_REQUEST
        
        # Set this media as thumbnail (unset others)
        result = MerchantProductMediaController.set_thumbnail(pid, mid)
        return jsonify({
            'message': 'Thumbnail set successfully',
            'media_id': mid,
            'is_thumbnail': True
        }), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Error setting thumbnail for product {pid}, media {mid}: {e}")
        return jsonify({'message': 'Failed to set thumbnail'}), HTTPStatus.INTERNAL_SERVER_ERROR


@merchant_dashboard_bp.route('/products/<int:pid>/media/<int:mid>/set-main-image', methods=['POST'])
@merchant_role_required
def set_product_media_main_image(pid, mid):
    """
    Set a media file as the main image for a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
      - in: path
        name: mid
        type: integer
        required: true
        description: Media ID to set as main image
    responses:
      200:
        description: Main image set successfully
        schema:
          type: object
          properties:
            message:
              type: string
            media_id:
              type: integer
            is_main_image:
              type: boolean
      404:
        description: Product or media not found
      400:
        description: Invalid request (e.g., media is not an image)
      500:
        description: Internal server error
    """
    try:
        # Verify the media belongs to the product and is an image
        media = MerchantProductMediaController.get_by_id(mid)
        if not media or media.product_id != pid:
            return jsonify({'message': 'Media not found or does not belong to this product'}), HTTPStatus.NOT_FOUND
        
        # media.type is an enum (MediaType). Compare against MediaType.IMAGE
        if getattr(media, 'type', None) != MediaType.IMAGE:
            return jsonify({'message': 'Only images can be set as main image'}), HTTPStatus.BAD_REQUEST
        
        # Set this media as main image (unset others)
        result = MerchantProductMediaController.set_main_image(pid, mid)
        return jsonify({
            'message': 'Main image set successfully',
            'media_id': mid,
            'is_main_image': True
        }), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Error setting main image for product {pid}, media {mid}: {e}")
        return jsonify({'message': 'Failed to set main image'}), HTTPStatus.INTERNAL_SERVER_ERROR


@merchant_dashboard_bp.route('/products/media/<int:mid>/update-order', methods=['PUT'])
@merchant_role_required
def update_media_order(mid):
    """
    Update the sort order of a media file
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: mid
        type: integer
        required: true
        description: Media ID to update
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - sort_order
            properties:
              sort_order:
                type: integer
                description: New sort order for the media
    responses:
      200:
        description: Media order updated successfully
        schema:
          type: object
          properties:
            message:
              type: string
            media_id:
              type: integer
            sort_order:
              type: integer
      404:
        description: Media not found
      400:
        description: Invalid request data
      500:
        description: Internal server error
    """
    try:
        data = request.get_json()
        if not data or 'sort_order' not in data:
            return jsonify({'message': 'sort_order is required'}), HTTPStatus.BAD_REQUEST
        
        sort_order = data['sort_order']
        if not isinstance(sort_order, int):
            return jsonify({'message': 'sort_order must be an integer'}), HTTPStatus.BAD_REQUEST
        
        # Update the media sort order
        result = MerchantProductMediaController.update_sort_order(mid, sort_order)
        return jsonify({
            'message': 'Media order updated successfully',
            'media_id': mid,
            'sort_order': sort_order
        }), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Error updating media order for media {mid}: {e}")
        return jsonify({'message': 'Failed to update media order'}), HTTPStatus.INTERNAL_SERVER_ERROR

# PRODUCT ATTRIBUTES
@merchant_dashboard_bp.route('/products/<int:pid>/attributes', methods=['GET'])
@merchant_role_required
def list_product_attributes(pid):
    """
    Get all attributes and their values for a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    responses:
      200:
        description: List of product attributes with their values
        schema:
          type: array
          items:
            type: object
            properties:
              attribute_id:
                type: integer
              attribute_name:
                type: string
              attribute_code:
                type: string
              values:
                type: array
                items:
                  type: object
                  properties:
                    value_id:
                      type: integer
                    value_name:
                      type: string
                    value_code:
                      type: string
                    is_selected:
                      type: boolean
      404:
        description: Product not found
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        attributes = MerchantProductAttributeController.list(pid)
        return jsonify(attributes), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error listing product attributes for product {pid}: {e}")
        if hasattr(e, 'code') and isinstance(e.code, int):
            return jsonify({'message': getattr(e, 'description', str(e))}), e.code
        return jsonify({'message': "Failed to list product attributes."}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/<int:pid>/attributes/values', methods=['POST'])
@merchant_role_required
def set_product_attribute_values(pid):
    try:
        data = request.get_json()
        current_app.logger.info(f"Received attribute values request for product {pid}: {data}")
        
        if not data or not isinstance(data, dict):
            return jsonify({
                'message': 'Invalid data format. Expected a dictionary of attribute values.',
                'error': 'INVALID_FORMAT'
            }), HTTPStatus.BAD_REQUEST

        # Format: { attribute_id: value }
        # value can be string, string[], or null
        for attribute_id, value in data.items():
            try:
                attribute_id = int(attribute_id)
                
                # Skip if value is null or empty
                if value is None or (isinstance(value, list) and len(value) == 0):
                    continue
                    
                # Create or update the attribute value
                MerchantProductAttributeController.upsert(pid, attribute_id, value)
            except ValueError as e:
                current_app.logger.error(f"Invalid attribute value for product {pid}, attribute {attribute_id}: {e}")
                return jsonify({
                    'message': str(e),
                    'error': 'INVALID_VALUE',
                    'attribute_id': attribute_id
                }), HTTPStatus.BAD_REQUEST
            except Exception as e:
                current_app.logger.error(f"Error setting attribute value for product {pid}, attribute {attribute_id}: {e}")
                return jsonify({
                    'message': f'Failed to set attribute value: {str(e)}',
                    'error': 'SERVER_ERROR',
                    'attribute_id': attribute_id
                }), HTTPStatus.INTERNAL_SERVER_ERROR

        # Return updated attributes
        updated_attributes = MerchantProductAttributeController.list(pid)
        return jsonify({
            'message': 'Attribute values updated successfully',
            'attributes': [p.serialize() for p in updated_attributes]
        }), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error setting product attribute values for product {pid}: {e}")
        return jsonify({
            'message': 'Failed to set product attribute values.',
            'error': 'SERVER_ERROR'
        }), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/<int:pid>/attributes/<int:aid>/<value_code>', methods=['PUT'])
@merchant_role_required
def update_product_attribute(pid, aid, value_code):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'message': 'No data provided for update.'}), HTTPStatus.BAD_REQUEST
            
        pa = MerchantProductAttributeController.update(pid, aid, value_code, data)
        return jsonify(pa.serialize()), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error updating product attribute for product {pid}, attribute {aid}: {e}")
        return jsonify({'message': 'Failed to update product attribute.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/<int:pid>/attributes/<int:aid>/<value_code>', methods=['DELETE'])
@merchant_role_required
def delete_product_attribute(pid, aid, value_code):
    try:
        MerchantProductAttributeController.delete(pid, aid, value_code)
        return '', HTTPStatus.NO_CONTENT
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error deleting product attribute for product {pid}, attribute {aid}: {e}")
        return jsonify({'message': 'Failed to delete product attribute.'}), HTTPStatus.INTERNAL_SERVER_ERROR

# TAX CATEGORIES
@merchant_dashboard_bp.route('/tax-categories', methods=['GET'])
@merchant_role_required
def list_tax_categories():
    """
    Get all available tax categories
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    responses:
      200:
        description: List of tax categories
        schema:
          type: array
          items:
            type: object
            properties:
              category_id:
                type: integer
              name:
                type: string
              code:
                type: string
              description:
                type: string
              default_rate:
                type: number
                format: float
                description: Default tax rate as a decimal (e.g., 0.20 for 20%)
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        categories = MerchantTaxCategoryController.list_all()
        return jsonify(categories), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error listing tax categories: {e}")
        if hasattr(e, 'code') and isinstance(e.code, int):
            return jsonify({'message': getattr(e, 'description', str(e))}), e.code
        return jsonify({'message': "Failed to list tax categories."}), HTTPStatus.INTERNAL_SERVER_ERROR

# ── BRAND CATEGORIES ────────────────────────────────────────────────────────────
@merchant_dashboard_bp.route('/brands/categories/<int:cid>', methods=['GET'])
@merchant_role_required
def get_brands_for_category(cid):
    """
    Get all brands associated with a specific category
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: cid
        type: integer
        required: true
        description: Category ID
    responses:
      200:
        description: List of brands for the category
        schema:
          type: array
          items:
            type: object
            properties:
              brand_id:
                type: integer
              name:
                type: string
              code:
                type: string
              description:
                type: string
              logo_url:
                type: string
                format: uri
              is_active:
                type: boolean
              created_at:
                type: string
                format: date-time
      404:
        description: Category not found
        schema:
          type: object
          properties:
            message:
              type: string
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        brands = MerchantBrandController.get_by_category(cid)
        return jsonify(brands), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error getting brands for category {cid}: {e}")
        if hasattr(e, 'code') and isinstance(e.code, int):
            return jsonify({'message': getattr(e, 'description', str(e))}), e.code
        return jsonify({'message': "Failed to get brands for category."}), HTTPStatus.INTERNAL_SERVER_ERROR

# PRODUCT STOCK
@merchant_dashboard_bp.route('/products/<int:pid>/stock', methods=['GET'])
@merchant_role_required
def get_product_stock(pid):
    """
    Get stock information for a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    responses:
      200:
        description: Product stock information
        schema:
          type: object
          properties:
            product_id:
              type: integer
            sku:
              type: string
            stock_quantity:
              type: integer
            low_stock_threshold:
              type: integer
            is_low_stock:
              type: boolean
            is_out_of_stock:
              type: boolean
            last_restocked_at:
              type: string
              format: date-time
            variants:
              type: array
              items:
                type: object
                properties:
                  variant_id:
                    type: integer
                  sku:
                    type: string
                  stock_quantity:
                    type: integer
                  is_low_stock:
                    type: boolean
                  is_out_of_stock:
                    type: boolean
      404:
        description: Product not found
        schema:
          type: object
          properties:
            message:
              type: string
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        stock = MerchantProductStockController.get(pid)
        return jsonify(stock), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error getting product stock for product {pid}: {e}")
        if hasattr(e, 'code') and isinstance(e.code, int):
            return jsonify({'message': getattr(e, 'description', str(e))}), e.code
        return jsonify({'message': "Failed to get product stock."}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/<int:pid>/stock', methods=['PUT'])
@merchant_role_required
def update_product_stock(pid):
    """
    Update stock information for a product
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - stock_qty
            properties:
              stock_qty:
                type: integer
                minimum: 0
                description: New stock quantity
              low_stock_threshold:
                type: integer
                minimum: 0
                description: Threshold for low stock warning
    responses:
      200:
        description: Stock information updated successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            sku:
              type: string
            stock_qty:
              type: integer
            low_stock_threshold:
              type: integer
            is_low_stock:
              type: boolean
            is_out_of_stock:
              type: boolean
            last_restocked_at:
              type: string
              format: date-time
      400:
        description: Invalid request data
        schema:
          type: object
          properties:
            message:
              type: string
      404:
        description: Product not found
        schema:
          type: object
          properties:
            message:
              type: string
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        data = request.get_json()
        if not data or 'stock_qty' not in data:
            return jsonify({'message': 'Missing required field: stock_qty'}), HTTPStatus.BAD_REQUEST
            
        stock = MerchantProductStockController.update(pid, data)
        return jsonify(stock), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error updating product stock for product {pid}: {e}")
        if hasattr(e, 'code') and isinstance(e.code, int):
            return jsonify({'message': getattr(e, 'description', str(e))}), e.code
        return jsonify({'message': "Failed to update product stock."}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/<int:pid>/stock/bulk-update', methods=['POST'])
@merchant_role_required
def bulk_update_product_stock(pid):
    """
    Bulk update stock information for a product and its variants
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: pid
        type: integer
        required: true
        description: Product ID
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - updates
            properties:
              updates:
                type: array
                items:
                  type: object
                  required:
                    - variant_id
                    - stock_quantity
                  properties:
                    variant_id:
                      type: integer
                      description: Variant ID (use 0 for main product)
                    stock_quantity:
                      type: integer
                      minimum: 0
                      description: New stock quantity
                    low_stock_threshold:
                      type: integer
                      minimum: 0
                      description: Threshold for low stock warning
    responses:
      200:
        description: Stock information updated successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            sku:
              type: string
            stock_quantity:
              type: integer
            low_stock_threshold:
              type: integer
            is_low_stock:
              type: boolean
            is_out_of_stock:
              type: boolean
            last_restocked_at:
              type: string
              format: date-time
            variants:
              type: array
              items:
                type: object
                properties:
                  variant_id:
                    type: integer
                  sku:
                    type: string
                  stock_quantity:
                    type: integer
                  is_low_stock:
                    type: boolean
                  is_out_of_stock:
                    type: boolean
      400:
        description: Invalid request data
        schema:
          type: object
          properties:
            message:
              type: string
      404:
        description: Product not found
        schema:
          type: object
          properties:
            message:
              type: string
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        data = request.get_json()
        if not data or 'updates' not in data:
            return jsonify({'message': 'Missing required field: updates'}), HTTPStatus.BAD_REQUEST
            
        stock = MerchantProductStockController.bulk_update(pid, data['updates'])
        return jsonify(stock), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error bulk updating product stock for product {pid}: {e}")
        if hasattr(e, 'code') and isinstance(e.code, int):
            return jsonify({'message': getattr(e, 'description', str(e))}), e.code
        return jsonify({'message': "Failed to bulk update product stock."}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/stock/low-stock', methods=['GET'])
@merchant_role_required
def get_low_stock_products():
    """
    Get all products with low stock
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    responses:
      200:
        description: List of products with low stock
        schema:
          type: array
          items:
            type: object
            properties:
              product_id:
                type: integer
              name:
                type: string
              sku:
                type: string
              stock_quantity:
                type: integer
              low_stock_threshold:
                type: integer
              is_low_stock:
                type: boolean
              is_out_of_stock:
                type: boolean
              variants:
                type: array
                items:
                  type: object
                  properties:
                    variant_id:
                      type: integer
                    name:
                      type: string
                    sku:
                      type: string
                    stock_quantity:
                      type: integer
                    is_low_stock:
                      type: boolean
                    is_out_of_stock:
                      type: boolean
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        products = MerchantProductStockController.get_low_stock()
        return jsonify(products), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error getting low stock products: {e}")
        if hasattr(e, 'code') and isinstance(e.code, int):
            return jsonify({'message': getattr(e, 'description', str(e))}), e.code
        return jsonify({'message': "Failed to get low stock products."}), HTTPStatus.INTERNAL_SERVER_ERROR

# ── PRODUCT APPROVAL ───────────────────────────────────────────────────────────
@merchant_dashboard_bp.route('/products/pending', methods=['GET'])
@super_admin_role_required
def list_pending_products():
    """
    Get all products pending approval
    ---
    tags:
      - Merchant - Products
    security:
      - Bearer: []
    responses:
      200:
        description: List of products pending approval
        schema:
          type: array
          items:
            type: object
            properties:
              product_id:
                type: integer
              name:
                type: string
              sku:
                type: string
              merchant_id:
                type: integer
              merchant_name:
                type: string
              status:
                type: string
                enum: [PENDING]
              created_at:
                type: string
                format: date-time
              updated_at:
                type: string
                format: date-time
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            message:
              type: string
    """
    try:
        products = MerchantProductController.list_pending()
        return jsonify(products), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error listing pending products: {e}")
        if hasattr(e, 'code') and isinstance(e.code, int):
            return jsonify({'message': getattr(e, 'description', str(e))}), e.code
        return jsonify({'message': "Failed to list pending products."}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/approved', methods=['GET'])
@super_admin_role_required
def list_approved_products():
    """Get all approved products."""
    try:
        products = MerchantProductController.get_approved_products()
        return jsonify([p.serialize() for p in products]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error listing approved products: {e}")
        return jsonify({'message': 'Failed to retrieve approved products.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/rejected', methods=['GET'])
@super_admin_role_required
def list_rejected_products():
    """Get all rejected products."""
    try:
        products = MerchantProductController.get_rejected_products()
        return jsonify([p.serialize() for p in products]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error listing rejected products: {e}")
        return jsonify({'message': 'Failed to retrieve rejected products.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/<int:pid>/approve', methods=['POST'])
@super_admin_role_required
def approve_product(pid):
    """Approve a product."""
    try:
        admin_id = get_jwt_identity()
        product = MerchantProductController.approve(pid, admin_id)
        return jsonify(product.serialize()), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error approving product {pid}: {e}")
        return jsonify({'message': 'Failed to approve product.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/products/<int:pid>/reject', methods=['POST'])
@super_admin_role_required
def reject_product(pid):
    """Reject a product."""
    try:
        data = request.get_json()
        if not data or 'reason' not in data:
            return jsonify({'message': 'Rejection reason is required.'}), HTTPStatus.BAD_REQUEST

        admin_id = get_jwt_identity()
        product = MerchantProductController.reject(pid, admin_id, data['reason'])
        return jsonify(product.serialize()), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error rejecting product {pid}: {e}")
        return jsonify({'message': 'Failed to reject product.'}), HTTPStatus.INTERNAL_SERVER_ERROR

# ── MERCHANT ORDERS ───────────────────────────────────────────────────────────
@merchant_dashboard_bp.route('/orders', methods=['GET'])
@jwt_required()
def get_merchant_orders():
    """
    Get all orders for the merchant
    ---
    tags:
      - Merchant - Orders
    security:
      - Bearer: []
    parameters:
      - name: page
        in: query
        type: integer
        default: 1
        description: Page number for pagination
      - name: per_page
        in: query
        type: integer
        default: 20
        description: Number of items per page
      - name: status
        in: query
        type: string
        enum: [PENDING, PROCESSING, SHIPPED, DELIVERED, CANCELLED]
        description: Filter orders by status
      - name: start_date
        in: query
        type: string
        format: date
        description: Filter orders from this date (YYYY-MM-DD)
      - name: end_date
        in: query
        type: string
        format: date
        description: Filter orders until this date (YYYY-MM-DD)
    responses:
      200:
        description: List of orders retrieved successfully
        schema:
          type: object
          properties:
            orders:
              type: array
              items:
                type: object
                properties:
                  order_id:
                    type: string
                  user_id:
                    type: integer
                  total_amount:
                    type: number
                    format: float
                  status:
                    type: string
                    enum: [PENDING, PROCESSING, SHIPPED, DELIVERED, CANCELLED]
                  created_at:
                    type: string
                    format: date-time
                  items:
                    type: array
                    items:
                      type: object
                      properties:
                        product_id:
                          type: integer
                        product_name:
                          type: string
                        quantity:
                          type: integer
                        unit_price:
                          type: number
                          format: float
            pagination:
              type: object
              properties:
                total:
                  type: integer
                pages:
                  type: integer
                current_page:
                  type: integer
                per_page:
                  type: integer
      401:
        description: Unauthorized - Invalid or missing token
      500:
        description: Internal server error
    """
    try:
        # Get the current user's ID from the JWT token
        current_user_id = get_jwt_identity()
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status = request.args.get('status')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        result = MerchantOrderController.get_merchant_orders(
            user_id=current_user_id,
            page=page,
            per_page=per_page,
            status=status,
            start_date=start_date,
            end_date=end_date
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Error getting merchant orders: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@merchant_dashboard_bp.route('/orders/<order_id>', methods=['GET'])
@jwt_required()
def get_merchant_order_details(order_id):
    """
    Get detailed information about a specific order
    ---
    tags:
      - Merchant - Orders
    security:
      - Bearer: []
    parameters:
      - in: path
        name: order_id

        type: string
        required: true
        description: ID of the order to retrieve
    responses:
      200:
        description: Order details retrieved successfully
        schema:
          type: object
          properties:
            order_id:
              type: string
            user_id:
              type: integer
            status:
              type: string
              enum: [PENDING, PROCESSING, SHIPPED, DELIVERED, CANCELLED]
            total_amount:
              type: number
              format: float
            shipping_address:
              type: object
              properties:
                address_line1:
                  type: string
                address_line2:
                  type: string
                city:
                  type: string
                state:
                  type: string
                postal_code:
                  type: string
                country:
                  type: string
            items:
              type: array
              items:
                type: object
                properties:
                  product_id:
                    type: integer
                  product_name:
                    type: string
                  sku:
                    type: string
                  quantity:
                    type: integer
                  unit_price:
                    type: number
                    format: float
                  subtotal:
                    type: number
                    format: float
            created_at:
              type: string
              format: date-time
            updated_at:
              type: string
              format: date-time
      401:
        description: Unauthorized - Invalid or missing token
      404:
        description: Order not found
      500:
        description: Internal server error
    """
    try:
        # Get the current user's ID from the JWT token
        current_user_id = get_jwt_identity()
        
        result = MerchantOrderController.get_merchant_order_details(
            user_id=current_user_id,
            order_id=order_id
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        current_app.logger.error(f"Error getting merchant order details: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@merchant_dashboard_bp.route('/orders/stats', methods=['GET'])
@jwt_required()
def get_merchant_order_stats():
    """
    Get order statistics for the merchant
    ---
    tags:
      - Merchant - Orders
    security:
      - Bearer: []
    parameters:
      - name: start_date
        in: query
        type: string
        format: date
        description: Start date for statistics (YYYY-MM-DD)
      - name: end_date
        in: query
        type: string
        format: date
        description: End date for statistics (YYYY-MM-DD)
    responses:
      200:
        description: Order statistics retrieved successfully
        schema:
          type: object
          properties:
            total_orders:
              type: integer
              description: Total number of orders in the period
            total_revenue:
              type: number
              format: float
              description: Total revenue in the period
            average_order_value:
              type: number
              format: float
              description: Average value per order
            orders_by_status:
              type: object
              properties:
                PENDING:
                  type: integer
                PROCESSING:
                  type: integer
                SHIPPED:
                  type: integer
                DELIVERED:
                  type: integer
                CANCELLED:
                  type: integer
            daily_stats:
              type: array
              items:
                type: object
                properties:
                  date:
                    type: string
                    format: date
                  orders:
                    type: integer
                  revenue:
                    type: number
                    format: float
      401:
        description: Unauthorized - Invalid or missing token
      500:
        description: Internal server error
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        stats = MerchantOrderController.get_order_stats(start_date, end_date)
        return jsonify(stats), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error getting order stats: {e}")
        return jsonify({'message': 'Failed to retrieve order statistics.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/inventory/stats', methods=['GET'])
@merchant_role_required
def get_inventory_stats():
    """
    Get inventory statistics for the merchant
    ---
    tags:
      - Merchant - Inventory
    security:
      - Bearer: []
    responses:
      200:
        description: Inventory statistics retrieved successfully
        schema:
          type: object
          properties:
            total_products:
              type: integer
              description: Total number of products in inventory
            total_stock_value:
              type: number
              format: float
              description: Total value of all inventory items
            low_stock_items:
              type: integer
              description: Number of products with stock below threshold
            out_of_stock_items:
              type: integer
              description: Number of products with zero stock
            stock_by_category:
              type: object
              properties:
                category_id:
                  type: object
                  properties:
                    name:
                      type: string
                    count:
                      type: integer
                    value:
                      type: number
                      format: float
            stock_status:
              type: object
              properties:
                in_stock:
                  type: integer
                low_stock:
                  type: integer
                out_of_stock:
                  type: integer
      401:
        description: Unauthorized - Invalid or missing token
      500:
        description: Internal server error
    """
    try:
        current_user_id = get_jwt_identity()
        stats = MerchantProductStockController.get_inventory_stats(current_user_id)
        return jsonify(stats), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error getting inventory stats: {str(e)}")
        return jsonify({'message': 'Failed to retrieve inventory statistics.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/inventory/products', methods=['GET'])
@merchant_role_required
def list_inventory_products():
    """
    Get a list of all products in the merchant's inventory
    ---
    tags:
      - Merchant - Inventory
    security:
      - Bearer: []
    parameters:
      - name: page
        in: query
        type: integer
        default: 1
        description: Page number for pagination
      - name: per_page
        in: query
        type: integer
        default: 20
        description: Number of items per page
      - name: search
        in: query
        type: string
        description: Search term for product name or SKU
      - name: category_id
        in: query
        type: integer
        description: Filter by category ID
      - name: brand_id
        in: query
        type: integer
        description: Filter by brand ID
      - name: stock_status
        in: query
        type: string
        enum: [in_stock, low_stock, out_of_stock]
        description: Filter by stock status
    responses:
      200:
        description: List of inventory products retrieved successfully
        schema:
          type: object
          properties:
            products:
              type: array
              items:
                type: object
                properties:
                  product_id:
                    type: integer
                  name:
                    type: string
                  sku:
                    type: string
                  category:
                    type: object
                    properties:
                      id:
                        type: integer
                      name:
                        type: string
                      slug:
                        type: string
                  brand:
                    type: object
                    properties:
                      id:
                        type: integer
                      name:
                        type: string
                      slug:
                        type: string
                  stock_qty:
                    type: integer
                  low_stock_threshold:
                    type: integer
                  cost_price:
                    type: number
                    format: float
                  selling_price:
                    type: number
                    format: float
                  stock_value:
                    type: number
                    format: float
            pagination:
              type: object
              properties:
                total:
                  type: integer
                pages:
                  type: integer
                current_page:
                  type: integer
                per_page:
                  type: integer
      401:
        description: Unauthorized - Invalid or missing token
      500:
        description: Internal server error
    """
    try:
        current_user_id = get_jwt_identity()
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '')
        category = request.args.get('category')
        brand = request.args.get('brand')
        stock_status = request.args.get('stock_status')

        result = MerchantProductStockController.get_products(
            user_id=current_user_id,
            page=page,
            per_page=per_page,
            search=search,
            category=category,
            brand=brand,
            stock_status=stock_status
        )
        
        return jsonify(result), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error listing inventory products: {str(e)}")
        return jsonify({'message': 'Failed to retrieve inventory products.'}), HTTPStatus.INTERNAL_SERVER_ERROR


# Inventory Export
@merchant_dashboard_bp.route('/inventory/export', methods=['GET'])
@jwt_required()
@merchant_role_required
def export_inventory_report():
    """Export inventory report in various formats (PDF, Excel, CSV)"""
    try:
        current_user_id = get_jwt_identity()
        
        # Get export format from query parameter (default: pdf)
        export_format = request.args.get('format', 'pdf').lower()
        
        # Validate format
        if export_format not in ['pdf', 'excel', 'csv']:
            return jsonify({
                "status": "error",
                "message": "Invalid export format. Supported formats: pdf, excel, csv"
            }), HTTPStatus.BAD_REQUEST
        
        # Get filters from query parameters (same as inventory page)
        filters = {
            'search': request.args.get('search'),
            'category': request.args.get('category'),
            'brand': request.args.get('brand'),
            'stock_status': request.args.get('stock_status')
        }
        
        # Remove None values
        filters = {k: v for k, v in filters.items() if v is not None and v != ''}
        
        # Generate and return the report
        response = MerchantInventoryExportController.export_inventory_report(
            user_id=current_user_id,
            export_format=export_format,
            filters=filters
        )
        
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error exporting inventory report: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Failed to export inventory report: {str(e)}"
        }), HTTPStatus.INTERNAL_SERVER_ERROR


@merchant_dashboard_bp.route('/brands/<int:bid>', methods=['GET'])
@merchant_role_required
def get_brand(bid):
    """
    Get brand details by ID
    ---
    tags:
      - Merchant - Brands
    security:
      - Bearer: []
    parameters:
      - in: path
        name: bid
        type: integer
        required: true
        description: Brand ID
    responses:
      200:
        description: Brand details retrieved successfully
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
      404:
        description: Brand not found
      500:
        description: Internal server error
    """
    try:
        brand = MerchantBrandController.get(bid)
        return jsonify(brand), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Merchant: Error getting brand {bid}: {e}")
        if hasattr(e, 'code') and isinstance(e.code, int):
            return jsonify({'message': getattr(e, 'description', str(e))}), e.code
        return jsonify({'message': 'Failed to retrieve brand details.'}), HTTPStatus.INTERNAL_SERVER_ERROR

# ── MERCHANT SUBSCRIPTION ─────────────────────────────────────────────────────
@merchant_dashboard_bp.route('/subscription/plans', methods=['GET'])
@merchant_role_required
def list_subscription_plans():
    """
    Get all available subscription plans
    ---
    tags:
      - Merchant - Subscription
    security:
      - Bearer: []
    responses:
      200:
        description: List of subscription plans retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              plan_id:
                type: integer
              name:
                type: string
              description:
                type: string
              featured_limit:
                type: integer
              promo_limit:
                type: integer
              duration_days:
                type: integer
              price:
                type: number
              can_place_premium:
                type: boolean
      500:
        description: Internal server error
    """
    try:
        from models.subscription import SubscriptionPlan
        plans = SubscriptionPlan.query.filter_by(active_flag=True).all()
        return jsonify([plan.serialize() for plan in plans]), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error listing subscription plans: {str(e)}")
        return jsonify({'message': 'Failed to retrieve subscription plans.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/subscription/current', methods=['GET'])
@merchant_role_required
def get_current_subscription():
    """
    Get merchant's current subscription details
    ---
    tags:
      - Merchant - Subscription
    security:
      - Bearer: []
    responses:
      200:
        description: Current subscription details retrieved successfully
        schema:
          type: object
          properties:
            is_subscribed:
              type: boolean
            can_place_premium:
              type: boolean
            subscription_started_at:
              type: string
              format: date-time
            subscription_expires_at:
              type: string
              format: date-time
            plan:
              type: object
              properties:
                plan_id:
                  type: integer
                name:
                  type: string
                description:
                  type: string
                featured_limit:
                  type: integer
                promo_limit:
                  type: integer
                can_place_premium:
                  type: boolean
      404:
        description: Merchant profile not found
      500:
        description: Internal server error
    """
    try:
        current_user_id = get_jwt_identity()
        status = MerchantProfileController.get_subscription_status(current_user_id)
        
        # Ensure can_place_premium is set correctly based on subscription status
        if status['is_subscribed'] and not status['can_place_premium']:
            profile = MerchantProfile.get_by_user_id(current_user_id)
            if profile:
                profile.can_place_premium = True
                db.session.commit()
                status['can_place_premium'] = True
        
        return jsonify(status), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.NOT_FOUND
    except Exception as e:
        current_app.logger.error(f"Error getting subscription status: {str(e)}")
        return jsonify({'message': 'Failed to retrieve subscription status.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/subscription/subscribe', methods=['POST'])
@merchant_role_required
def subscribe_to_plan():
    """
    Subscribe to a subscription plan
    ---
    tags:
      - Merchant - Subscription
    security:
      - Bearer: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - plan_id
            properties:
              plan_id:
                type: integer
                description: ID of the subscription plan to subscribe to
    responses:
      200:
        description: Successfully subscribed to plan
        schema:
          type: object
          properties:
            message:
              type: string
            subscription:
              type: object
              properties:
                is_subscribed:
                  type: boolean
                can_place_premium:
                  type: boolean
                subscription_started_at:
                  type: string
                  format: date-time
                subscription_expires_at:
                  type: string
                  format: date-time
                plan:
                  type: object
      400:
        description: Invalid request data
      404:
        description: Plan or merchant profile not found
      500:
        description: Internal server error
    """
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data or 'plan_id' not in data:
            return jsonify({
                'message': 'Missing required field: plan_id',
                'error': 'MISSING_FIELD'
            }), HTTPStatus.BAD_REQUEST

        profile = MerchantProfileController.subscribe_to_plan(
            current_user_id,
            data['plan_id']
        )
        
        # Ensure can_place_premium is set to True for subscribed users
        if profile.is_subscribed and not profile.can_place_premium:
            profile.can_place_premium = True
            db.session.commit()
        
        return jsonify({
            'message': 'Successfully subscribed to plan',
            'subscription': {
                'is_subscribed': profile.is_subscribed,
                'can_place_premium': profile.can_place_premium,
                'subscription_started_at': profile.subscription_started_at.isoformat(),
                'subscription_expires_at': profile.subscription_expires_at.isoformat(),
                'plan': profile.subscription_plan.serialize() if profile.subscription_plan else None
            }
        }), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.NOT_FOUND
    except Exception as e:
        current_app.logger.error(f"Error subscribing to plan: {str(e)}")
        return jsonify({'message': 'Failed to subscribe to plan.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/subscription/cancel', methods=['POST'])
@merchant_role_required
def cancel_subscription():
    """
    Cancel current subscription
    ---
    tags:
      - Merchant - Subscription
    security:
      - Bearer: []
    responses:
      200:
        description: Successfully cancelled subscription
        schema:
          type: object
          properties:
            message:
              type: string
            subscription:
              type: object
              properties:
                is_subscribed:
                  type: boolean
                can_place_premium:
                  type: boolean
      404:
        description: Merchant profile not found
      500:
        description: Internal server error
    """
    try:
        current_user_id = get_jwt_identity()
        profile = MerchantProfileController.cancel_subscription(current_user_id)
        
        # Ensure can_place_premium is set to False when subscription is cancelled
        if not profile.is_subscribed and profile.can_place_premium:
            profile.can_place_premium = False
            db.session.commit()
        
        return jsonify({
            'message': 'Successfully cancelled subscription',
            'subscription': {
                'is_subscribed': profile.is_subscribed,
                'can_place_premium': profile.can_place_premium
            }
        }), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.NOT_FOUND
    except Exception as e:
        current_app.logger.error(f"Error cancelling subscription: {str(e)}")
        return jsonify({'message': 'Failed to cancel subscription.'}), HTTPStatus.INTERNAL_SERVER_ERROR

# ── PRODUCT PLACEMENTS ─────────────────────────────────────────────────────
@merchant_dashboard_bp.route('/product-placements', methods=['GET'])
@merchant_role_required
def list_product_placements():
    """
    Get all product placements for the merchant
    ---
    tags:
      - Merchant - Product Placements
    security:
      - Bearer: []
    parameters:
      - name: placement_type
        in: query
        type: string
        enum: [FEATURED, PROMOTED]
        description: Optional filter by placement type
    responses:
      200:
        description: List of product placements retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              placement_id:
                type: integer
              product_id:
                type: integer
              merchant_id:
                type: integer
              placement_type:
                type: string
                enum: [featured, promoted]
              sort_order:
                type: integer
              is_active:
                type: boolean
              expires_at:
                type: string
                format: date-time
                nullable: true
              added_at:
                type: string
                format: date-time
              product_details:
                type: object
                properties:
                  product_id:
                    type: integer
                  product_name:
                    type: string
      500:
        description: Internal server error
    """
    try:
        placement_type = request.args.get('placement_type')
        placements = MerchantProductPlacementController.list_placements(placement_type)
        return jsonify([p.serialize() for p in placements]), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error listing product placements: {str(e)}")
        return jsonify({'message': 'Failed to retrieve product placements.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/product-placements', methods=['POST'])
@merchant_role_required
def create_product_placement():
    """
    Create a new product placement
    ---
    tags:
      - Merchant - Product Placements
    security:
      - Bearer: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - product_id
              - placement_type
            properties:
              product_id:
                type: integer
                description: ID of the product to place
              placement_type:
                type: string
                enum: [FEATURED, PROMOTED]
                description: Type of placement
              sort_order:
                type: integer
                description: Order in which the placement should appear
              promotional_price:
                type: number
                description: Special promotional price for PROMOTED placements
              special_start:
                type: string
                format: date
                description: Start date for the promotion (YYYY-MM-DD)
              special_end:
                type: string
                format: date
                description: End date for the promotion (YYYY-MM-DD)
    responses:
      201:
        description: Product placement created successfully
      400:
        description: Invalid request data
      403:
        description: Subscription does not allow premium placements
      500:
        description: Internal server error
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'message': 'No data provided'}), HTTPStatus.BAD_REQUEST

        # Validate required fields
        required_fields = ['product_id', 'placement_type']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                'message': f'Missing required fields: {", ".join(missing_fields)}',
                'error': 'MISSING_FIELDS'
            }), HTTPStatus.BAD_REQUEST

        # Validate promotional data for PROMOTED placements
        if data['placement_type'].upper() == 'PROMOTED':
            promo_fields = ['promotional_price', 'special_start', 'special_end']
            missing_promo_fields = [field for field in promo_fields if field not in data]
            if missing_promo_fields:
                return jsonify({
                    'message': f'Missing required fields for promoted placement: {", ".join(missing_promo_fields)}',
                    'error': 'MISSING_PROMO_FIELDS'
                }), HTTPStatus.BAD_REQUEST

        placement = MerchantProductPlacementController.add_product_to_placement(
            product_id=data['product_id'],
            placement_type_str=data['placement_type'],
            sort_order=data.get('sort_order', 0),
            promotional_price=data.get('promotional_price'),
            special_start=data.get('special_start'),
            special_end=data.get('special_end')
        )
        return jsonify(placement.serialize()), HTTPStatus.CREATED
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except PermissionError as e:
        return jsonify({'message': str(e)}), HTTPStatus.FORBIDDEN
    except Exception as e:
        current_app.logger.error(f"Error creating product placement: {str(e)}")
        return jsonify({'message': 'Failed to create product placement.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/product-placements/<int:placement_id>', methods=['DELETE'])
@merchant_role_required
def delete_product_placement(placement_id):
    """
    Delete a product placement
    ---
    tags:
      - Merchant - Product Placements
    security:
      - Bearer: []
    parameters:
      - in: path
        name: placement_id
        type: integer
        required: true
        description: ID of the placement to delete
    requestBody:
      required: false
      content:
        application/json:
          schema:
            type: object
            properties:
              cleanup_promotion:
                type: boolean
                description: Whether to clean up promotional pricing for promoted placements
    responses:
      204:
        description: Product placement deleted successfully
      404:
        description: Placement not found
      500:
        description: Internal server error
    """
    try:
        data = request.get_json() or {}
        cleanup_promotion = data.get('cleanup_promotion', False)
        
        MerchantProductPlacementController.remove_product_from_placement(placement_id, cleanup_promotion)
        return '', HTTPStatus.NO_CONTENT
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.NOT_FOUND
    except Exception as e:
        current_app.logger.error(f"Error deleting product placement {placement_id}: {str(e)}")
        return jsonify({'message': 'Failed to delete product placement.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/product-placements/<int:placement_id>/sort-order', methods=['PUT'])
@merchant_role_required
def update_placement_sort_order(placement_id):
    """
    Update the sort order of a product placement
    ---
    tags:
      - Merchant - Product Placements
    security:
      - Bearer: []
    parameters:
      - in: path
        name: placement_id
        type: integer
        required: true
        description: ID of the placement to update
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - sort_order
            properties:
              sort_order:
                type: integer
                description: New sort order value
    responses:
      200:
        description: Sort order updated successfully
      400:
        description: Invalid request data
      404:
        description: Placement not found
      500:
        description: Internal server error
    """
    try:
        data = request.get_json()
        if not data or 'sort_order' not in data:
            return jsonify({'message': 'Sort order is required'}), HTTPStatus.BAD_REQUEST

        placement = MerchantProductPlacementController.update_placement_sort_order(
            placement_id,
            data['sort_order']
        )
        return jsonify(placement.serialize()), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error updating placement sort order: {str(e)}")
        return jsonify({'message': 'Failed to update placement sort order.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/product-placements/<int:placement_id>', methods=['PUT'])
@merchant_role_required
def update_promoted_placement(placement_id):
    """
    Update a promoted product placement's promotional details
    ---
    tags:
      - Merchant - Product Placements
    security:
      - Bearer: []
    parameters:
      - in: path
        name: placement_id
        type: integer
        required: true
        description: ID of the promoted placement to update
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - promotional_price
              - special_start
              - special_end
            properties:
              promotional_price:
                type: number
                description: New promotional price
              special_start:
                type: string
                format: date
                description: New promotion start date (YYYY-MM-DD)
              special_end:
                type: string
                format: date
                description: New promotion end date (YYYY-MM-DD)
    responses:
      200:
        description: Promoted placement updated successfully
      400:
        description: Invalid request data or validation error
      404:
        description: Placement not found
      500:
        description: Internal server error
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'message': 'No data provided'}), HTTPStatus.BAD_REQUEST

        # Validate required fields
        required_fields = ['promotional_price', 'special_start', 'special_end']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                'message': f'Missing required fields: {", ".join(missing_fields)}',
                'error': 'MISSING_FIELDS'
            }), HTTPStatus.BAD_REQUEST

        placement = MerchantProductPlacementController.update_promoted_placement(
            placement_id,
            data['promotional_price'],
            data['special_start'],
            data['special_end']
        )
        return jsonify(placement.serialize()), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error updating promoted placement: {str(e)}")
        return jsonify({'message': 'Failed to update promoted placement.'}), HTTPStatus.INTERNAL_SERVER_ERROR

# ── MERCHANT PRODUCT REVIEWS ─────────────────────────────────────────────────────
@merchant_dashboard_bp.route('/product-reviews', methods=['GET'])
@merchant_role_required
def get_merchant_product_reviews():
    """
    Get all reviews for products owned by a merchant
    ---
    tags:
      - Merchant - Reviews
    security:
      - Bearer: []
    parameters:
      - name: page
        in: query
        type: integer
        default: 1
        description: Page number for pagination
      - name: per_page
        in: query
        type: integer
        default: 10
        description: Number of items per page
      - name: rating
        in: query
        type: integer
        description: Filter by rating (1-5)
      - name: product_id
        in: query
        type: integer
        description: Filter by specific product
      - name: start_date
        in: query
        type: string
        format: date
        description: Filter by start date (YYYY-MM-DD)
      - name: end_date
        in: query
        type: string
        format: date
        description: Filter by end date (YYYY-MM-DD)
      - name: has_images
        in: query
        type: boolean
        description: Filter reviews with/without images
    responses:
      200:
        description: List of reviews with pagination and stats
        schema:
          type: object
          properties:
            reviews:
              type: array
              items:
                type: object
                properties:
                  review_id:
                    type: integer
                  rating:
                    type: integer
                  title:
                    type: string
                  body:
                    type: string
                  created_at:
                    type: string
                    format: date-time
                  user:
                    type: object
                    properties:
                      id:
                        type: integer
                      first_name:
                        type: string
                      last_name:
                        type: string
                  product:
                    type: object
                    properties:
                      product_id:
                        type: integer
                      name:
                        type: string
            pagination:
              type: object
              properties:
                total:
                  type: integer
                page:
                  type: integer
                per_page:
                  type: integer
                pages:
                  type: integer
            stats:
              type: object
              properties:
                average_rating:
                  type: number
                total_reviews:
                  type: integer
                rating_distribution:
                  type: object
                  properties:
                    "1":
                      type: integer
                    "2":
                      type: integer
                    "3":
                      type: integer
                    "4":
                      type: integer
                    "5":
                      type: integer
      500:
        description: Internal server error
    """
    try:
        current_user_id = get_jwt_identity()
        merchant = MerchantProfile.get_by_user_id(current_user_id)
        
        if not merchant:
            return jsonify({'message': 'Merchant profile not found'}), HTTPStatus.NOT_FOUND

        # Get query parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Build filters
        filters = {}
        if 'rating' in request.args:
            filters['rating'] = request.args.get('rating', type=int)
        if 'product_id' in request.args:
            filters['product_id'] = request.args.get('product_id', type=int)
        if 'start_date' in request.args:
            filters['start_date'] = datetime.strptime(request.args['start_date'], '%Y-%m-%d')
        if 'end_date' in request.args:
            filters['end_date'] = datetime.strptime(request.args['end_date'], '%Y-%m-%d')
        if 'has_images' in request.args:
            filters['has_images'] = request.args.get('has_images', type=bool)

        from controllers.merchant.merchant_review_controller import MerchantReviewController
        result = MerchantReviewController.get_merchant_product_reviews(
            merchant_id=merchant.id,
            page=page,
            per_page=per_page,
            filters=filters
        )
        
        return jsonify(result), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error getting merchant product reviews: {str(e)}")
        return jsonify({'message': 'Failed to retrieve product reviews.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/product-reviews/stats', methods=['GET'])
@merchant_role_required
def get_product_review_stats():
    """
    Get review statistics for merchant's products
    ---
    tags:
      - Merchant - Reviews
    security:
      - Bearer: []
    parameters:
      - name: product_id
        in: query
        type: integer
        description: Optional product ID to get stats for a specific product
    responses:
      200:
        description: Review statistics for merchant's products
        schema:
          type: array
          items:
            type: object
            properties:
              product_id:
                type: integer
              product_name:
                type: string
              average_rating:
                type: number
              total_reviews:
                type: integer
              rating_distribution:
                type: object
                properties:
                  "1":
                    type: integer
                  "2":
                    type: integer
                  "3":
                    type: integer
                  "4":
                    type: integer
                  "5":
                    type: integer
      500:
        description: Internal server error
    """
    try:
        current_user_id = get_jwt_identity()
        merchant = MerchantProfile.get_by_user_id(current_user_id)
        
        if not merchant:
            return jsonify({'message': 'Merchant profile not found'}), HTTPStatus.NOT_FOUND

        product_id = request.args.get('product_id', type=int)
        
        from controllers.merchant.merchant_review_controller import MerchantReviewController
        stats = MerchantReviewController.get_product_review_stats(
            merchant_id=merchant.id,
            product_id=product_id
        )
        
        return jsonify(stats), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error getting product review stats: {str(e)}")
        return jsonify({'message': 'Failed to retrieve review statistics.'}), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/product-reviews/recent', methods=['GET'])
@merchant_role_required
def get_recent_reviews():
    """
    Get most recent reviews for merchant's products
    ---
    tags:
      - Merchant - Reviews
    security:
      - Bearer: []
    parameters:
      - name: limit
        in: query
        type: integer
        default: 5
        description: Number of recent reviews to return
    responses:
      200:
        description: List of recent reviews
        schema:
          type: array
          items:
            type: object
            properties:
              review_id:
                type: integer
              rating:
                type: integer
              title:
                type: string
              body:
                type: string
              created_at:
                type: string
                format: date-time
              user:
                type: object
                properties:
                  id:
                    type: integer
                  first_name:
                    type: string
                  last_name:
                    type: string
              product:
                type: object
                properties:
                  product_id:
                    type: integer
                  name:
                    type: string
      500:
        description: Internal server error
    """
    try:
        current_user_id = get_jwt_identity()
        merchant = MerchantProfile.get_by_user_id(current_user_id)
        
        if not merchant:
            return jsonify({'message': 'Merchant profile not found'}), HTTPStatus.NOT_FOUND

        limit = request.args.get('limit', 5, type=int)
        
        from controllers.merchant.merchant_review_controller import MerchantReviewController
        reviews = MerchantReviewController.get_recent_reviews(
            merchant_id=merchant.id,
            limit=limit
        )
        
        return jsonify(reviews), HTTPStatus.OK
    except ValueError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error getting recent reviews: {str(e)}")
        return jsonify({'message': 'Failed to retrieve recent reviews.'}), HTTPStatus.INTERNAL_SERVER_ERROR

# Analytics Routes
@merchant_dashboard_bp.route('/analytics/revenue-orders-trend', methods=['GET'])
@jwt_required()
@merchant_role_required
def get_revenue_orders_trend():
    """Get revenue and orders trend data."""
    try:
        current_user_id = get_jwt_identity()
        trend_data = MerchantDashboardController.get_sales_data(current_user_id)
        return jsonify({
            'status': 'success',
            'data': trend_data
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting revenue orders trend: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/analytics/merchant-performance', methods=['GET'])
@jwt_required()
@merchant_role_required
def get_merchant_performance():
    """Get merchant performance metrics."""
    try:
        current_user_id = get_jwt_identity()
        performance_data = MerchantDashboardController.get_monthly_summary(current_user_id)
        return jsonify({
            'status': 'success',
            'data': performance_data
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting merchant performance: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/analytics/top-products', methods=['GET'])
@jwt_required()
@merchant_role_required
def get_analytics_top_products():
    """Get top performing products."""
    try:
        current_user_id = get_jwt_identity()
        # Get optional query parameter for limit
        limit = request.args.get('limit', default=5, type=int)
        products_data = MerchantDashboardController.get_top_products(current_user_id, limit=limit)
        return jsonify({
            'status': 'success',
            'data': products_data
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting top products: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), HTTPStatus.INTERNAL_SERVER_ERROR

@merchant_dashboard_bp.route('/analytics/recent-orders', methods=['GET'])
@jwt_required()
@merchant_role_required
def get_analytics_recent_orders():
    """Get recent orders."""
    try:
        current_user_id = get_jwt_identity()
        orders_data = MerchantDashboardController.get_recent_orders(current_user_id)
        return jsonify({
            'status': 'success',
            'data': orders_data
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting recent orders: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), HTTPStatus.INTERNAL_SERVER_ERROR


# Monthly Sales Analytics
@merchant_dashboard_bp.route('/reports/sales/monthly-sales', methods=['GET'])
@jwt_required()
@merchant_role_required
def get_monthly_sales():
    """Get monthly sales revenue and units sold for the last 5 months."""
    try:
        current_user_id = get_jwt_identity()
        monthly_data = MerchantReportController.get_monthly_sales_analytics(current_user_id)
        return jsonify({
            "status": "success",
            "data": monthly_data
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting monthly sales: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), HTTPStatus.INTERNAL_SERVER_ERROR



# Detailed Monthly Sales Analytics 
@merchant_dashboard_bp.route('/reports/sales/sales-data', methods=['GET'])
@jwt_required()
@merchant_role_required
def get_detailed_monthly_sales():
    try:
        current_user_id = get_jwt_identity()
        data = MerchantReportController.get_detailed_monthly_sales(current_user_id)
        return jsonify({
            "status": "success",
            "data": data
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting detailed monthly sales: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), HTTPStatus.INTERNAL_SERVER_ERROR


# Product Performance Analytics
@merchant_dashboard_bp.route('/reports/sales/product-performance', methods=['GET'])
@jwt_required()
@merchant_role_required
def get_product_performance():
    try:
        current_user_id = get_jwt_identity()
        
        # Get optional query parameters
        months = request.args.get('months', default=3, type=int)
        limit = request.args.get('limit', default=3, type=int)
        
        data = MerchantReportController.get_product_performance(
            current_user_id, 
            months=months,
            limit=limit
        )
        
        return jsonify({
            "status": "success",
            "data": data
        }), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Error getting product performance: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Failed to fetch product performance data"
        }), HTTPStatus.INTERNAL_SERVER_ERROR


# Revenue by Category Analytics
@merchant_dashboard_bp.route('/reports/sales/revenue-by-category', methods=['GET'])
@jwt_required()
@merchant_role_required
def get_revenue_by_category():
    try:
        current_user_id = get_jwt_identity()
        
        # Get optional query parameter
        months = request.args.get('months', default=3, type=int)
        
        data = MerchantReportController.get_revenue_by_category(
            current_user_id, 
            months=months
        )
        
        return jsonify({
            "status": "success",
            "data": data
        }), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Error getting revenue by category: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Failed to fetch revenue by category data"
        }), HTTPStatus.INTERNAL_SERVER_ERROR




@merchant_dashboard_bp.route('/reports/product/dashboard-summary', methods=['GET'])
@jwt_required()
@merchant_role_required
def get_dashboard_summary():
    try:
        current_user_id = get_jwt_identity()
        data = MerchantReportController.get_dashboard_summary(current_user_id)
        
        return jsonify({
            "status": "success",
            "data": data
        }), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Error getting dashboard summary: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Failed to fetch dashboard summary"
        }), HTTPStatus.INTERNAL_SERVER_ERROR



@merchant_dashboard_bp.route('/reports/product/daily-sales', methods=['GET'])
@jwt_required()
@merchant_role_required
def get_daily_sales():
    try:
        current_user_id = get_jwt_identity()
        data = MerchantReportController.get_daily_sales_data(current_user_id)
        
        return jsonify({
            "status": "success",
            "data": data
        }), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Error getting daily sales data: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Failed to fetch daily sales data"
        }), HTTPStatus.INTERNAL_SERVER_ERROR



@merchant_dashboard_bp.route('/reports/product/top-selling-products', methods=['GET'])
@jwt_required()
@merchant_role_required
def get_top_selling_products():
    try:
        current_user_id = get_jwt_identity()
        
        # Get optional query parameters
        days = request.args.get('days', default=30, type=int)
        limit = request.args.get('limit', default=4, type=int)
        
        data = MerchantReportController.get_top_selling_products(
            current_user_id, 
            days=days,
            limit=limit
        )
        
        return jsonify({
            "status": "success",
            "data": data
        }), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Error getting top selling products: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Failed to fetch top selling products"
        }), HTTPStatus.INTERNAL_SERVER_ERROR





@merchant_dashboard_bp.route('/reports/product/most-viewed-products', methods=['GET'])
@jwt_required()
@merchant_role_required
def get_most_viewed_products():
    try:
        current_user_id = get_jwt_identity()
        
        # Optional query param
        limit = request.args.get('limit', default=4, type=int)

        data = MerchantReportController.get_most_viewed_products(
            user_id=current_user_id,
            limit=limit
        )

        return jsonify({
            "status": "success",
            "data": data
        }), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error getting most viewed products: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Failed to fetch most viewed products"
        }), HTTPStatus.INTERNAL_SERVER_ERROR


# Sales Report Export
@merchant_dashboard_bp.route('/reports/sales/export', methods=['GET'])
@jwt_required()
@merchant_role_required
def export_sales_report():
    """Export sales report in various formats (PDF, Excel, CSV)"""
    try:
        current_user_id = get_jwt_identity()
        
        # Get export format from query parameter (default: pdf)
        export_format = request.args.get('format', 'pdf').lower()
        
        # Validate format
        if export_format not in ['pdf', 'excel', 'csv']:
            return jsonify({
                "status": "error",
                "message": "Invalid export format. Supported formats: pdf, excel, csv"
            }), HTTPStatus.BAD_REQUEST
        
        # Generate and return the report
        response = MerchantReportExportController.export_sales_report(
            user_id=current_user_id,
            export_format=export_format
        )
        
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error exporting sales report: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Failed to export sales report: {str(e)}"
        }), HTTPStatus.INTERNAL_SERVER_ERROR


#Merchant-Settings Change Password
@merchant_dashboard_bp.route('/change-password', methods=['POST'])
@merchant_role_required
@jwt_required
def change_password():
    try:
        current_app.logger.debug("Change password request received")
        data = request.get_json()
        current_app.logger.debug(f"Request data: {data}")
        
        if not data:
            current_app.logger.error("No JSON data received")
            return jsonify({"message": "No data provided"}), 400
            
        current_password = data.get("current_password")
        new_password = data.get("new_password")
        
        if not current_password or not new_password:
            current_app.logger.error("Missing password fields")
            return jsonify({"message": "Both current_password and new_password are required"}), 400
            
        current_app.logger.debug("Calling MerchantSettingsController.change_password")
        result = MerchantSettingsController.change_password(current_password, new_password)
        current_app.logger.debug(f"Change password result: {result}")
        
        return result
        
    except Exception as e:
        current_app.logger.error(f"Error in change_password route: {str(e)}")
        return jsonify({"message": f"Internal server error: {str(e)}"}), 500

#Load Merchant Details
@merchant_dashboard_bp.route('/account', methods=['OPTIONS'])
def handle_account_options():
    """Handle OPTIONS request for CORS preflight"""
    response = jsonify({})
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, PUT, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response, 200

@merchant_dashboard_bp.route('/account', methods=['GET'])
@merchant_role_required
def get_merchant_account():
    """
    Get merchant account and bank details
    ---
    tags:
      - Merchant - Settings
    responses:
      200:
        description: Merchant account data returned successfully
      404:
        description: Merchant not found
    """
    return MerchantSettingsController.get_account_settings()

# Update Account Settings
@merchant_dashboard_bp.route('/account', methods=['PUT'])
@merchant_role_required
@jwt_required()
def update_merchant_account():
    """
    Update merchant account and bank details
    ---
    tags:
      - Merchant - Settings
    security:
      - Bearer: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            properties:
              email:
                type: string
                format: email
                description: New email address
              phone:
                type: string
                description: New phone number
              account_name:
                type: string
                description: Business name
              account_number:
                type: string
                description: Bank account number
              ifsc_code:
                type: string
                description: IFSC code
              bank_name:
                type: string
                description: Bank name
              branch_name:
                type: string
                description: Bank branch name
    responses:
      200:
        description: Account settings updated successfully
        schema:
          type: object
          properties:
            message:
              type: string
      400:
        description: Invalid request data or email already exists
      404:
        description: User or merchant profile not found
      500:
        description: Internal server error
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"message": "No data provided"}), 400
        
        return MerchantSettingsController.update_account_settings(data)
        
    except Exception as e:
        current_app.logger.error(f"Error updating account settings: {str(e)}")
        return jsonify({"message": "Internal server error"}), 500

# Get User Info
@merchant_dashboard_bp.route('/user-info', methods=['GET'])
@merchant_role_required
@jwt_required()
def get_user_info():
    """
    Get basic user information for the currently logged-in user
    ---
    tags:
      - Merchant - Settings
    security:
      - Bearer: []
    responses:
      200:
        description: User information returned successfully
        schema:
          type: object
          properties:
            user_id:
              type: integer
            first_name:
              type: string
            last_name:
              type: string
            email:
              type: string
            phone:
              type: string
            role:
              type: string
            is_email_verified:
              type: boolean
            is_phone_verified:
              type: boolean
            is_active:
              type: boolean
      404:
        description: User not found
      500:
        description: Internal server error
    """
    return MerchantSettingsController.get_user_info()

# LIVE STREAM ROUTES
from flask import request

@merchant_dashboard_bp.route('/live-streams', methods=['POST'])
@jwt_required()
def schedule_live_stream():
    user_id = get_jwt_identity()
    merchant = MerchantProfile.get_by_user_id(user_id)
    if not merchant:
        return jsonify({"error": "Merchant profile not found."}), 404
    try:
        if request.content_type and request.content_type.startswith('multipart/form-data'):
            title = request.form.get('title')
            description = request.form.get('description')
            product_id = request.form.get('product_id')
            scheduled_time = request.form.get('scheduled_time')
            thumbnail_file = request.files.get('thumbnail')
            thumbnail_url = None
            allow_embedding = request.form.get('allow_embedding', 'true').lower() == 'true'
        else:
            data = request.get_json()
            title = data.get('title')
            description = data.get('description')
            product_id = data.get('product_id')
            scheduled_time = data.get('scheduled_time')
            thumbnail_file = None
            thumbnail_url = data.get('thumbnail_url')
            allow_embedding = data.get('allow_embedding', True)
        if not all([title, description, product_id, scheduled_time]):
            return jsonify({"error": "Missing required fields."}), 400
        # Updated: get rtmp_info from controller with embedding control
        stream, yt_event_id, yt_status, yt_thumbnails, rtmp_info = MerchantLiveStreamController.schedule_live_stream(
            merchant.id, title, description, product_id, scheduled_time, thumbnail_file, thumbnail_url, allow_embedding
        )
        return jsonify({
            "data": stream.serialize(),
            "youtube_event_id": yt_event_id,
            "youtube_status": yt_status,
            "youtube_thumbnails": yt_thumbnails,
            "rtmp_info": rtmp_info
        }), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error scheduling live stream: {e}")
        return jsonify({"error": str(e)}), 500

@merchant_dashboard_bp.route('/live-streams', methods=['GET'])
@jwt_required()
def list_merchant_live_streams():
    user_id = get_jwt_identity()
    merchant = MerchantProfile.get_by_user_id(user_id)
    if not merchant:
        return jsonify({"error": "Merchant profile not found."}), 404
    streams = MerchantLiveStreamController.get_by_merchant(merchant.id)
    # Only return streams that are not deleted
    visible_streams = [s.serialize() for s in streams if not s.deleted_at]
    return jsonify(visible_streams), 200

@merchant_dashboard_bp.route('/live-streams/<int:stream_id>', methods=['GET'])
@jwt_required()
def get_merchant_live_stream(stream_id):
    import logging
    user_id = get_jwt_identity()
    merchant = MerchantProfile.get_by_user_id(user_id)
    if not merchant:
        return jsonify({"error": "Merchant profile not found."}), 404
    stream = MerchantLiveStreamController.get_by_id(stream_id)
    if not stream or stream.merchant_id != merchant.id:
        return jsonify({"error": "Live stream not found or not owned by merchant."}), 404
    # Debug: log stream key, url, and rtmp_info if present
    logging.debug(f"[GET /live-streams/{stream_id}] stream_key={getattr(stream, 'stream_key', None)} stream_url={getattr(stream, 'stream_url', None)}")
    if hasattr(stream, 'rtmp_info'):
        logging.debug(f"[GET /live-streams/{stream_id}] rtmp_info={getattr(stream, 'rtmp_info')}")
        return jsonify({**stream.serialize(), "rtmp_info": stream.rtmp_info}), 200
    return jsonify(stream.serialize()), 200

@merchant_dashboard_bp.route('/live-streams/<int:stream_id>/start', methods=['POST'])
@jwt_required()
def start_merchant_live_stream(stream_id):
    user_id = get_jwt_identity()
    merchant = MerchantProfile.get_by_user_id(user_id)
    if not merchant:
        return jsonify({"error": "Merchant profile not found."}), 404
    stream = MerchantLiveStreamController.get_by_id(stream_id)
    try:
        # --- YouTube Go Live automation ---
        redundant_transition = False
        if stream and stream.stream_key and stream.yt_livestream_id:
            from models.youtube_token import YouTubeToken
            import requests
            yt_token = YouTubeToken.query.filter_by(is_active=True).order_by(YouTubeToken.created_at.desc()).first()
            if yt_token:
                access_token = yt_token.access_token
                url = 'https://www.googleapis.com/youtube/v3/liveBroadcasts/transition'
                params = {
                    'broadcastStatus': 'live',
                    'id': stream.stream_key,
                    'part': 'status'
                }
                headers = {
                    'Authorization': f'Bearer {access_token}',
                    'Accept': 'application/json'
                }
                resp = requests.post(url, headers=headers, params=params)
                if resp.status_code != 200:
                    # Check for redundantTransition error
                    try:
                        err_json = resp.json()
                        errors = err_json.get('error', {}).get('errors', [])
                        if any(e.get('reason') == 'redundantTransition' for e in errors):
                            # Treat as success: already live
                            redundant_transition = True
                        else:
                            return jsonify({"error": f'YouTube Go Live failed: {resp.text}'}), 400
                    except Exception:
                        return jsonify({"error": f'YouTube Go Live failed: {resp.text}'}), 400
        # --- End YouTube Go Live automation ---
        stream = MerchantLiveStreamController.start_stream(stream, merchant.id)
        return jsonify({"data": stream.serialize()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400

@merchant_dashboard_bp.route('/live-streams/<int:stream_id>/end', methods=['POST'])
@jwt_required()
def end_merchant_live_stream(stream_id):
    user_id = get_jwt_identity()
    merchant = MerchantProfile.get_by_user_id(user_id)
    if not merchant:
        return jsonify({"error": "Merchant profile not found."}), 404
    stream = MerchantLiveStreamController.get_by_id(stream_id)
    try:
        # Now handled in controller: end YouTube broadcast and update DB
        stream = MerchantLiveStreamController.end_stream(stream, merchant.id)
        return jsonify({"data": stream.serialize()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400

@merchant_dashboard_bp.route('/live-streams/<int:stream_id>', methods=['DELETE'])
@jwt_required()
def delete_merchant_live_stream(stream_id):
    user_id = get_jwt_identity()
    merchant = MerchantProfile.get_by_user_id(user_id)
    if not merchant:
        return jsonify({"error": "Merchant profile not found."}), 404
    stream = MerchantLiveStreamController.get_by_id(stream_id)
    try:
        MerchantLiveStreamController.delete_stream(stream, merchant.id)
        return jsonify({"message": "Live stream deleted."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400

@merchant_dashboard_bp.route('/live-streams/<int:stream_id>/embedding', methods=['PUT'])
@jwt_required()
def update_stream_embedding(stream_id):
    """
    Update embedding settings for a live stream
    """
    user_id = get_jwt_identity()
    merchant = MerchantProfile.get_by_user_id(user_id)
    if not merchant:
        return jsonify({"error": "Merchant profile not found."}), 404
    
    data = request.get_json()
    allow_embedding = data.get('allow_embedding')
    
    if allow_embedding is None:
        return jsonify({"error": "allow_embedding field is required."}), 400
    
    stream = MerchantLiveStreamController.get_by_id(stream_id)
    if not stream or stream.merchant_id != merchant.id:
        return jsonify({"error": "Live stream not found or not owned by merchant."}), 404
    
    try:
        updated_stream = MerchantLiveStreamController.update_stream_embedding(stream, merchant.id, allow_embedding)
        return jsonify({
            "message": f"Embedding settings updated successfully. Embedding {'enabled' if allow_embedding else 'disabled'}.",
            "data": updated_stream.serialize()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400

@merchant_dashboard_bp.route('/live-streams/youtube-scheduled', methods=['GET'])
@jwt_required()
def get_youtube_scheduled_streams():
    user_id = get_jwt_identity()
    merchant = MerchantProfile.get_by_user_id(user_id)
    if not merchant:
        return jsonify({"error": "Merchant profile not found."}), 404
    try:
        streams = MerchantLiveStreamController.get_merchant_youtube_scheduled_streams(merchant.id)
        return jsonify({"data": streams}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@merchant_dashboard_bp.route('/live-streams/scheduled', methods=['GET'])
@jwt_required()
def list_merchant_scheduled_live_streams():
    user_id = get_jwt_identity()
    merchant = MerchantProfile.get_by_user_id(user_id)
    if not merchant:
        return jsonify({"error": "Merchant profile not found."}), 404
    scheduled_streams = MerchantLiveStreamController.get_scheduled_streams_by_merchant(merchant.id)
    visible_streams = [s.serialize() for s in scheduled_streams if not s.deleted_at]
    return jsonify(visible_streams), 200

@merchant_dashboard_bp.route('/live-streams/all', methods=['GET'])
@jwt_required()
def list_all_merchant_live_streams():
    """
    Get all live streams (scheduled, live, ended) for the merchant
    """
    from models.live_stream import StreamStatus
    user_id = get_jwt_identity()
    from auth.models.models import MerchantProfile
    merchant = MerchantProfile.get_by_user_id(user_id)
    if not merchant:
        return jsonify({"error": "Merchant profile not found."}), 404
    try:
        streams = MerchantLiveStreamController.get_all_streams_by_merchant(merchant.id)
        return jsonify({
            "scheduled": [s.serialize() for s in streams['scheduled']],
            "live": [s.serialize() for s in streams['live']],
            "ended": [s.serialize() for s in streams['ended']]
        }), 200
    except Exception as e:
        current_app.logger.error(f"Error fetching all streams: {str(e)}")
        return jsonify({"error": str(e)}), 500

@merchant_dashboard_bp.route('/live-streams/available-slots', methods=['GET'])
@jwt_required()
def available_slots():
    date = request.args.get('date')
    slots = MerchantLiveStreamController.get_available_time_slots(date)
    return jsonify({"available_slots": slots})


