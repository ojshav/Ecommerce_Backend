# FILE: routes/promo_code_routes.py
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from http import HTTPStatus
from datetime import date

from models.promotion import Promotion
from models.product import Product
from common.database import db

promo_code_bp = Blueprint('promo_code_bp', __name__, url_prefix='/api/promo-code')

@promo_code_bp.route('/apply', methods=['POST'])
@jwt_required()
def apply_promo_code():
    """
    Validates a promotion code and returns the discount details.
    Receives the promotion code and the list of cart items.
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
              - promo_code
              - cart_items
            properties:
              promo_code:
                type: string
                description: The promotion code entered by the user.
              cart_items:
                type: array
                description: "A list of items currently in the user's cart."
                items:
                  type: object
                  properties:
                    product_id:
                      type: integer
                    quantity:
                      type: integer
                    price:
                      type: number
    responses:
      200:
        description: Promotion applied successfully.
        schema:
          type: object
          properties:
            message:
              type: string
            discount_amount:
              type: number
            promotion_id:
              type: integer
            new_total:
              type: number
      400:
        description: Invalid request or promotion cannot be applied.
        schema:
          type: object
          properties:
            error:
              type: string
      404:
        description: Promotion code not found.
        schema:
          type: object
          properties:
            error:
              type: string
    """
    data = request.get_json()
    if not data or not data.get('promo_code') or not isinstance(data.get('cart_items'), list):
        return jsonify({'error': 'Promo code and cart items are required.'}), HTTPStatus.BAD_REQUEST

    promo_code = data['promo_code'].upper()
    cart_items = data['cart_items']

   
    today = date.today()
    promo = Promotion.query.filter(
        Promotion.code == promo_code,
        Promotion.deleted_at.is_(None)
    ).first()

    if not promo:
        return jsonify({'error': 'Invalid promotion code.'}), HTTPStatus.NOT_FOUND

    if not promo.active_flag:
        return jsonify({'error': 'This promotion is currently inactive.'}), HTTPStatus.BAD_REQUEST

    if not (promo.start_date <= today <= promo.end_date):
        return jsonify({'error': 'This promotion has expired or is not yet active.'}), HTTPStatus.BAD_REQUEST
    
    total_discount = 0.0
    
    
    product_ids_in_cart = [item['product_id'] for item in cart_items]
    products_in_cart = Product.query.filter(Product.product_id.in_(product_ids_in_cart)).all()
    product_details_map = {p.product_id: p for p in products_in_cart}

    # --- 2. Check the promotion type and apply discount ---
    
    # Case 1: Sitewide Promotion
    if not promo.product_id and not promo.category_id and not promo.brand_id:
        for item in cart_items:
            item_total = item['price'] * item['quantity']
            if promo.discount_type.value == 'fixed':
                # For sitewide fixed discount, apply it once to the whole cart
                total_discount = min(item_total, float(promo.discount_value))
                break 
            elif promo.discount_type.value == 'percentage':
                total_discount += item_total * (float(promo.discount_value) / 100.0)

    # Case 2: Target-specific Promotion
    else:
        applicable_items_found = False
        for item in cart_items:
            product = product_details_map.get(item['product_id'])
            if not product:
                continue

            is_applicable = False
            if promo.product_id and promo.product_id == product.product_id:
                is_applicable = True
            elif promo.category_id and promo.category_id == product.category_id:
                is_applicable = True
            elif promo.brand_id and promo.brand_id == product.brand_id:
                is_applicable = True
            
            if is_applicable:
                applicable_items_found = True
                item_total = item['price'] * item['quantity']
                if promo.discount_type.value == 'fixed':
                    total_discount += min(item_total, float(promo.discount_value))
                elif promo.discount_type.value == 'percentage':
                    total_discount += item_total * (float(promo.discount_value) / 100.0)
        
        if not applicable_items_found:
            return jsonify({'error': 'This promo code is not valid for any items in your cart.'}), HTTPStatus.BAD_REQUEST

    # --- 3. Return the result ---
    original_total = sum(item['price'] * item['quantity'] for item in cart_items)
    new_total = original_total - total_discount

    return jsonify({
        'message': 'Promotion applied successfully!',
        'discount_amount': round(total_discount, 2),
        'new_total': round(new_total, 2),
        'promotion_id': promo.promotion_id
    }), HTTPStatus.OK