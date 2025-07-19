
from flask import Blueprint
from controllers.shop.shop_product_controller import ShopProductController
from flask_cors import cross_origin
from common.decorators import superadmin_required

shop_product_bp = Blueprint('shop_product', __name__)

@shop_product_bp.route('/api/shop/products', methods=['GET'])
@cross_origin()
def get_products():
    """
    Get all shop products with pagination and filtering
    ---
    tags:
      - Shop Products
    parameters:
      - in: query
        name: page
        type: integer
        description: Page number
      - in: query
        name: per_page
        type: integer
        description: Items per page
      - in: query
        name: sort_by
        type: string
        description: Field to sort by
      - in: query
        name: order
        type: string
        enum: [asc, desc]
        description: Sort order
      - in: query
        name: category_id
        type: integer
        description: Filter by category
      - in: query
        name: brand_id
        type: integer
        description: Filter by brand
      - in: query
        name: min_price
        type: number
        description: Minimum price filter
      - in: query
        name: max_price
        type: number
        description: Maximum price filter
      - in: query
        name: search
        type: string
        description: Search term
    responses:
      200:
        description: A list of shop products
      500:
        description: Internal server error
    """
    return ShopProductController.get_all_products()

@shop_product_bp.route('/api/shop/products/<int:product_id>', methods=['GET'])
@cross_origin()
def get_product(product_id):
    """
    Get a single shop product by ID
    ---
    tags:
      - Shop Products
    parameters:
      - in: path
        name: product_id
        type: integer
        required: true
        description: ID of the shop product to retrieve
    responses:
      200:
        description: Shop product details
      404:
        description: Shop product not found
      500:
        description: Internal server error
    """
    return ShopProductController.get_product(product_id)

@shop_product_bp.route('/api/shop/products', methods=['POST'])
@cross_origin()
@superadmin_required
def create_product():
    """
    Create a new shop product
    ---
    tags:
      - Shop Products
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            product_name:
              type: string
            product_description:
              type: string
            sku:
              type: string
            category_id:
              type: integer
            brand_id:
              type: integer
            cost_price:
              type: number
            selling_price:
              type: number
            is_published:
              type: boolean
    responses:
      201:
        description: Shop product created successfully
      400:
        description: Bad request
      401:
        description: Unauthorized
      403:
        description: Forbidden
    """
    return ShopProductController.create_product()

@shop_product_bp.route('/api/shop/products/<int:product_id>', methods=['PUT'])
@cross_origin()
@superadmin_required
def update_product(product_id):
    """
    Update an existing shop product
    ---
    tags:
      - Shop Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: product_id
        type: integer
        required: true
        description: ID of the shop product to update
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            product_name:
              type: string
            product_description:
              type: string
            sku:
              type: string
            category_id:
              type: integer
            brand_id:
              type: integer
            cost_price:
              type: number
            selling_price:
              type: number
            is_published:
              type: boolean
            active_flag:
              type: boolean
    responses:
      200:
        description: Shop product updated successfully
      400:
        description: Bad request
      401:
        description: Unauthorized
      403:
        description: Forbidden
      404:
        description: Shop product not found
    """
    return ShopProductController.update_product(product_id)

@shop_product_bp.route('/api/shop/products/<int:product_id>', methods=['DELETE'])
@cross_origin()
@superadmin_required
def delete_product(product_id):
    """
    Delete a shop product
    ---
    tags:
      - Shop Products
    security:
      - Bearer: []
    parameters:
      - in: path
        name: product_id
        type: integer
        required: true
        description: ID of the shop product to delete
    responses:
      200:
        description: Shop product deleted successfully
      401:
        description: Unauthorized
      403:
        description: Forbidden
      404:
        description: Shop product not found
    """
    return ShopProductController.delete_product(product_id)
