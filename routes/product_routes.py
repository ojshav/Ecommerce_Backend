from flask import Blueprint, request, jsonify
from controllers.product_controller import ProductController
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from flask_cors import cross_origin
from models.recently_viewed import RecentlyViewed
from common.database import db
from datetime import datetime
from sqlalchemy import desc
from sqlalchemy import or_
from models.product import Product
from models.category import Category
from models.brand import Brand

product_bp = Blueprint('product', __name__)

@product_bp.route('/api/products', methods=['GET', 'OPTIONS'])
@cross_origin()
def get_products():
    """
    Get all products with pagination and filtering
    ---
    tags:
      - Products
    parameters:
      - in: query
        name: page
        type: integer
        required: false
        default: 1
        description: Page number
      - in: query
        name: per_page
        type: integer
        required: false
        default: 10
        description: Items per page (max 50)
      - in: query
        name: sort_by
        type: string
        required: false
        default: created_at
        description: Field to sort by
      - in: query
        name: order
        type: string
        required: false
        default: desc
        enum: [asc, desc]
        description: Sort order
      - in: query
        name: category_id
        type: integer
        required: false
        description: Filter by category
      - in: query
        name: brand_id
        type: integer
        required: false
        description: Filter by brand
      - in: query
        name: min_price
        type: number
        required: false
        description: Minimum price filter
      - in: query
        name: max_price
        type: number
        required: false
        description: Maximum price filter
      - in: query
        name: search
        type: string
        required: false
        description: Search term for product name/description
    responses:
      200:
        description: List of products retrieved successfully
        schema:
          type: object
          properties:
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
                  cost_price:
                    type: number
                    format: float
                  selling_price:
                    type: number
                    format: float
                  media:
                    type: array
                    items:
                      type: object
                      properties:
                        url:
                          type: string
                        type:
                          type: string
            total:
              type: integer
            page:
              type: integer
            per_page:
              type: integer
            pages:
              type: integer
      500:
        description: Internal server error
    """
    if request.method == 'OPTIONS':
        return '', 200
    return ProductController.get_all_products()

@product_bp.route('/api/products/<int:product_id>', methods=['GET'])
@cross_origin()
def get_product(product_id):
    """
    Get a single product by ID
    ---
    tags:
      - Products
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
          properties:
            product_id:
              type: integer
            product_name:
              type: string
            sku:
              type: string
            cost_price:
              type: number
              format: float
            selling_price:
              type: number
              format: float
            media:
              type: array
              items:
                type: object
                properties:
                  url:
                    type: string
                  type:
                    type: string
            brand:
              type: object
              properties:
                brand_id:
                  type: integer
                name:
                  type: string
            category:
              type: object
              properties:
                category_id:
                  type: integer
                name:
                  type: string
      404:
        description: Product not found
      500:
        description: Internal server error
    """
    return ProductController.get_product(product_id)

@product_bp.route('/api/products/recently-viewed', methods=['GET'])
@jwt_required()
@cross_origin()
def get_recently_viewed():
    """
    Get recently viewed products for the current user
    ---
    tags:
      - Products
    security:
      - Bearer: []
    responses:
      200:
        description: List of recently viewed products retrieved successfully
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: string
              name:
                type: string
              price:
                type: number
                format: float
              originalPrice:
                type: number
                format: float
              currency:
                type: string
              stock:
                type: integer
              isNew:
                type: boolean
              isBuiltIn:
                type: boolean
              rating:
                type: number
                format: float
              reviews:
                type: array
                items:
                  type: object
              sku:
                type: string
              primary_image:
                type: string
              image:
                type: string
      401:
        description: Unauthorized - JWT token missing or invalid
      500:
        description: Internal server error
    """
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify([]), 200
            
        # Get the 6 most recently viewed products
        recent_views = RecentlyViewed.query.filter_by(
            user_id=user_id
        ).order_by(
            desc(RecentlyViewed.viewed_at)
        ).limit(6).all()
        
        # Get the product details for each view
        products = []
        for view in recent_views:
            if view.product and view.product.active_flag and not view.product.deleted_at:
                product_dict = view.product.serialize()
                # Add frontend-specific fields
                product_dict.update({
                    'id': str(view.product.product_id),
                    'name': view.product.product_name,
                    'price': float(view.product.selling_price),
                    'originalPrice': float(view.product.cost_price),
                    'currency': 'INR',
                    'stock': 100,
                    'isNew': True,
                    'isBuiltIn': False,
                    'rating': 0,
                    'reviews': [],
                    'sku': view.product.sku if hasattr(view.product, 'sku') else None
                })
                
                # Get primary media
                media = ProductController.get_product_media(view.product.product_id)
                if media:
                    product_dict['primary_image'] = media['url']
                    product_dict['image'] = media['url']
                
                products.append(product_dict)
        
        return jsonify(products), 200
        
    except Exception as e:
        print(f"Error in get_recently_viewed: {str(e)}")
        return jsonify({
            "error": "Failed to fetch recently viewed products",
            "message": str(e)
        }), 500

@product_bp.route('/api/products/categories', methods=['GET'])
@cross_origin()
def get_categories():
    """
    Get all product categories
    ---
    tags:
      - Products
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
      500:
        description: Internal server error
    """
    return ProductController.get_categories()

@product_bp.route('/api/products/brands', methods=['GET'])
@cross_origin()
def get_brands():
    """
    Get all product brands
    ---
    tags:
      - Products
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
      500:
        description: Internal server error
    """
    return ProductController.get_brands()

@product_bp.route('/api/products/<int:product_id>/details', methods=['GET'])
@cross_origin()
def get_product_details(product_id):
    """
    Get detailed product information including media and meta data
    ---
    tags:
      - Products
    parameters:
      - in: path
        name: product_id
        type: integer
        required: true
        description: ID of the product to retrieve
    responses:
      200:
        description: Detailed product information retrieved successfully
        schema:
          type: object
          properties:
            product_id:
              type: integer
            product_name:
              type: string
            sku:
              type: string
            cost_price:
              type: number
              format: float
            selling_price:
              type: number
              format: float
            media:
              type: array
              items:
                type: object
                properties:
                  url:
                    type: string
                  type:
                    type: string
            attributes:
              type: array
              items:
                type: object
                properties:
                  attribute_id:
                    type: integer
                    description: Unique identifier for the attribute (may be modified for array processing)
                  attribute_name:
                    type: string
                    description: Name of the attribute (e.g., "Size", "Color")
                  value_code:
                    type: string
                    description: Code value for the attribute
                  value_text:
                    type: string
                    description: Text value of the attribute (individual value, not array format)
                  value_label:
                    type: string
                    description: Display label for the attribute value
                  is_text_based:
                    type: boolean
                    description: Whether the attribute is text-based
                  input_type:
                    type: string
                    enum: [text, number, select, multiselect, boolean]
                    description: Input type for the attribute
              description: Array of product attributes. Array format attributes (from variants) are automatically converted to individual attributes for display.
            meta:
              type: object
              properties:
                short_desc:
                  type: string
                full_desc:
                  type: string
            brand:
              type: object
              properties:
                brand_id:
                  type: integer
                name:
                  type: string
            category:
              type: object
              properties:
                category_id:
                  type: integer
                name:
                  type: string
      404:
        description: Product not found
      500:
        description: Internal server error
    """
    try:
        # Try to get the current user ID if authenticated
        user_id = None
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
        except Exception:
            # If JWT verification fails, continue without user tracking
            pass
        
        # If user is authenticated, track the view
        if user_id:
            # Check if there's an existing view record
            existing_view = RecentlyViewed.query.filter_by(
                user_id=user_id,
                product_id=product_id
            ).first()
            
            if existing_view:
                # Update the viewed_at timestamp
                existing_view.viewed_at = datetime.utcnow()
            else:
                # Create a new view record
                new_view = RecentlyViewed(
                    user_id=user_id,
                    product_id=product_id,
                    viewed_at=datetime.utcnow()
                )
                db.session.add(new_view)
            
            # Commit the changes
            db.session.commit()
        
        # Get and return the product details
        return ProductController.get_product_details(product_id)
        
    except Exception as e:
        print(f"Error in get_product_details route: {str(e)}")
        return jsonify({
            "error": "Failed to fetch product details",
            "message": str(e)
        }), 500

@product_bp.route('/api/products/brand/<string:brand_slug>', methods=['GET'])
@cross_origin()
def get_products_by_brand(brand_slug):
    """
    Get parent products filtered by brand slug (excludes product variants)
    ---
    tags:
      - Products
    parameters:
      - in: path
        name: brand_slug
        type: string
        required: true
        description: Slug of the brand to filter by
      - in: query
        name: page
        type: integer
        required: false
        default: 1
        description: Page number
      - in: query
        name: per_page
        type: integer
        required: false
        default: 10
        description: Items per page (max 50)
      - in: query
        name: sort_by
        type: string
        required: false
        default: created_at
        description: Field to sort by
      - in: query
        name: order
        type: string
        required: false
        default: desc
        enum: [asc, desc]
        description: Sort order
      - in: query
        name: min_price
        type: number
        required: false
        description: Minimum price filter
      - in: query
        name: max_price
        type: number
        required: false
        description: Maximum price filter
      - in: query
        name: search
        type: string
        required: false
        description: Search term for product name/description
    responses:
      200:
        description: List of parent products for the brand retrieved successfully (excludes variants)
        schema:
          type: object
          properties:
            products:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                  name:
                    type: string
                  price:
                    type: number
                    format: float
                  originalPrice:
                    type: number
                    format: float
                  primary_image:
                    type: string
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
                has_next:
                  type: boolean
                has_prev:
                  type: boolean
            brand:
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
      404:
        description: Brand not found
      500:
        description: Internal server error
    """
    return ProductController.get_products_by_brand(brand_slug)

@product_bp.route('/api/products/category/<int:category_id>', methods=['GET'])
@cross_origin()
def get_products_by_category(category_id):
    """
    Get parent products filtered by category ID (excludes product variants)
    ---
    tags:
      - Products
    parameters:
      - in: path
        name: category_id
        type: integer
        required: true
        description: ID of the category to filter by
      - in: query
        name: page
        type: integer
        required: false
        default: 1
        description: Page number
      - in: query
        name: per_page
        type: integer
        required: false
        default: 10
        description: Items per page (max 50)
      - in: query
        name: sort_by
        type: string
        required: false
        default: created_at
        description: Field to sort by
      - in: query
        name: order
        type: string
        required: false
        default: desc
        enum: [asc, desc]
        description: Sort order
      - in: query
        name: min_price
        type: number
        required: false
        description: Minimum price filter
      - in: query
        name: max_price
        type: number
        required: false
        description: Maximum price filter
      - in: query
        name: search
        type: string
        required: false
        description: Search term for product name/description
      - in: query
        name: include_children
        type: boolean
        required: false
        default: true
        description: Whether to include products from child categories
    responses:
      200:
        description: List of parent products for the category retrieved successfully (excludes variants)
        schema:
          type: object
          properties:
            products:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                  name:
                    type: string
                  price:
                    type: number
                    format: float
                  originalPrice:
                    type: number
                    format: float
                  primary_image:
                    type: string
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
                has_next:
                  type: boolean
                has_prev:
                  type: boolean
            category:
              type: object
              properties:
                category_id:
                  type: integer
                name:
                  type: string
                slug:
                  type: string
                icon_url:
                  type: string
      404:
        description: Category not found
      500:
        description: Internal server error
    """
    return ProductController.get_products_by_category(category_id)

@product_bp.route('/api/products/<int:product_id>/variants', methods=['GET'])
@cross_origin()
def get_product_variants(product_id):
    """
    Get all variants for a parent product
    ---
    tags:
      - Products
    parameters:
      - in: path
        name: product_id
        type: integer
        required: true
        description: ID of the parent product
    responses:
      200:
        description: List of product variants retrieved successfully
        schema:
          type: object
          properties:
            variants:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                  name:
                    type: string
                  price:
                    type: number
                    format: float
                  originalPrice:
                    type: number
                    format: float
                  primary_image:
                    type: string
                  isVariant:
                    type: boolean
                  parentProductId:
                    type: string
            total:
              type: integer
      404:
        description: Parent product not found
      500:
        description: Internal server error
    """
    return ProductController.get_product_variants(product_id)

@product_bp.route('/api/products/new', methods=['GET'])
@cross_origin()
def get_new_products():
    """
    Get products that were added within the last week (excluding variants)
    ---
    tags:
      - Products
    parameters:
      - in: query
        name: page
        type: integer
        required: false
        default: 1
        description: Page number
      - in: query
        name: per_page
        type: integer
        required: false
        default: 10
        description: Items per page (max 50)
    responses:
      200:
        description: List of new products retrieved successfully (excluding variants)
        schema:
          type: object
          properties:
            products:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                  name:
                    type: string
                  description:
                    type: string
                  price:
                    type: number
                    format: float
                  originalPrice:
                    type: number
                    format: float
                  stock:
                    type: integer
                  isNew:
                    type: boolean
                  isBuiltIn:
                    type: boolean
                  primary_image:
                    type: string
                  image:
                    type: string
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
                has_next:
                  type: boolean
                has_prev:
                  type: boolean
      500:
        description: Internal server error
    """
    return ProductController.get_new_products()

@product_bp.route('/api/products/trendy-deals', methods=['GET'])
@cross_origin()
def get_trendy_deals():
    """
    Get products that have been ordered the most (trendy deals)
    ---
    tags:
      - Products
    parameters:
      - in: query
        name: page
        type: integer
        required: false
        default: 1
        description: Page number
      - in: query
        name: per_page
        type: integer
        required: false
        default: 10
        description: Items per page (max 50)
    responses:
      200:
        description: List of trendy products retrieved successfully
        schema:
          type: object
          properties:
            products:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                  name:
                    type: string
                  description:
                    type: string
                  price:
                    type: number
                    format: float
                  originalPrice:
                    type: number
                    format: float
                  stock:
                    type: integer
                  isNew:
                    type: boolean
                  isBuiltIn:
                    type: boolean
                  orderCount:
                    type: integer
                  primary_image:
                    type: string
                  image:
                    type: string
                  currency:
                    type: string
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
                has_next:
                  type: boolean
                has_prev:
                  type: boolean
      500:
        description: Internal server error
        schema:
          type: object
          properties:
            error:
              type: string
            products:
              type: array
              items: {}
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
                has_next:
                  type: boolean
                has_prev:
                  type: boolean
    """
    try:
        return ProductController.get_trendy_deals()
    except Exception as e:
        print(f"Error in get_trendy_deals route: {str(e)}")
        return jsonify({
            "error": "Failed to fetch trendy deals",
            "message": str(e),
            "products": [],
            "pagination": {
                "total": 0,
                "pages": 0,
                "current_page": 1,
                "per_page": 10,
                "has_next": False,
                "has_prev": False
            }
        }), 500 

# Add new route for getting product reviews
@product_bp.route('/api/products/<int:product_id>/reviews', methods=['GET'])
@cross_origin()
def get_product_reviews(product_id):
    """
    Get all reviews for a product
    ---
    tags:
      - Products
    parameters:
      - in: path
        name: product_id
        type: integer
        required: true
        description: ID of the product to retrieve reviews for
      - in: query
        name: page
        type: integer
        required: false
        default: 1
        description: Page number
      - in: query
        name: per_page
        type: integer
        required: false
        default: 10
        description: Items per page (max 50)
      - in: query
        name: min_rating
        type: integer
        required: false
        description: Minimum rating filter
      - in: query
        name: sort_by
        type: string
        required: false
        default: created_at
        description: Field to sort by
      - in: query
        name: order
        type: string
        required: false
        default: desc
        enum: [asc, desc]
        description: Sort order
    responses:
      200:
        description: List of product reviews retrieved successfully
        schema:
          type: object
          properties:
            reviews:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  user:
                    type: object
                    properties:
                      id:
                        type: integer
                      name:
                        type: string
                      avatar:
                        type: string
                  rating:
                    type: integer
                  title:
                    type: string
                  body:
                    type: string
                  created_at:
                    type: string
                  images:
                    type: array
                    items:
                      type: object
            average_rating:
              type: number
              format: float
            total_reviews:
              type: integer
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
                has_next:
                  type: boolean
                has_prev:
                  type: boolean
      404:
        description: Product not found
      500:
        description: Internal server error
    """
    try:
        from models.review import Review
        from sqlalchemy import func
        from common.database import db

        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 50)

        # Get filter parameters
        min_rating = request.args.get('min_rating', type=int)
        sort_by = request.args.get('sort_by', 'created_at')
        order = request.args.get('order', 'desc')

        # Base query
        query = Review.query.filter_by(
            product_id=product_id,
            deleted_at=None
        )

        # Apply rating filter
        if min_rating is not None:
            query = query.filter(Review.rating >= min_rating)

        # Apply sorting
        if order == 'asc':
            query = query.order_by(getattr(Review, sort_by))
        else:
            query = query.order_by(getattr(Review, sort_by).desc())

        # Execute paginated query
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # Calculate average rating
        avg_rating = db.session.query(func.avg(Review.rating))\
            .filter(Review.product_id == product_id)\
            .scalar() or 0

        # Prepare response
        reviews = pagination.items
        review_data = [{
            'id': review.review_id,
            'user': {
                'id': review.user.id,
                'name': review.user.name,
                'avatar': review.user.avatar_url
            },
            'rating': review.rating,
            'title': review.title,
            'body': review.body,
            'created_at': review.created_at.isoformat(),
            'images': [img.serialize() for img in review.images] if review.images else []
        } for review in reviews]

        return jsonify({
            'reviews': review_data,
            'average_rating': round(float(avg_rating), 1),
            'total_reviews': pagination.total,
            'pagination': {
                'total': pagination.total,
                'pages': pagination.pages,
                'current_page': page,
                'per_page': per_page,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        })

    except Exception as e:
        print(f"Error in get_product_reviews: {str(e)}")
        return jsonify({
            'error': 'Failed to fetch product reviews',
            'message': str(e)
        }), 500

# Add new route for getting product discounts
@product_bp.route('/api/products/discounts', methods=['GET'])
@cross_origin()
def get_product_discounts():
    """
    Get all products with discounts
    ---
    tags:
      - Products
    parameters:
      - in: query
        name: page
        type: integer
        required: false
        default: 1
        description: Page number
      - in: query
        name: per_page
        type: integer
        required: false
        default: 10
        description: Items per page (max 50)
      - in: query
        name: min_discount
        type: number
        required: false
        description: Minimum discount percentage filter
      - in: query
        name: max_discount
        type: number
        required: false
        description: Maximum discount percentage filter
      - in: query
        name: sort_by
        type: string
        required: false
        default: discount_pct
        description: Field to sort by
      - in: query
        name: order
        type: string
        required: false
        default: desc
        enum: [asc, desc]
        description: Sort order
    responses:
      200:
        description: List of discounted products retrieved successfully
        schema:
          type: object
          properties:
            products:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                  name:
                    type: string
                  description:
                    type: string
                  price:
                    type: number
                    format: float
                  originalPrice:
                    type: number
                    format: float
                  discount_pct:
                    type: number
                    format: float
                  discount_amount:
                    type: number
                    format: float
                  primary_image:
                    type: string
                  image:
                    type: string
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
                has_next:
                  type: boolean
                has_prev:
                  type: boolean
      500:
        description: Internal server error
    """
    try:
        from models.product import Product
        from sqlalchemy import func
        from common.database import db

        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 50)

        # Get filter parameters
        min_discount = request.args.get('min_discount', type=float)
        max_discount = request.args.get('max_discount', type=float)
        sort_by = request.args.get('sort_by', 'discount_pct')
        order = request.args.get('order', 'desc')

        # Base query
        query = Product.query.filter(
            Product.deleted_at.is_(None),
            Product.active_flag.is_(True),
            Product.approval_status == 'approved',
            Product.discount_pct > 0
        )

        # Apply discount filters
        if min_discount is not None:
            query = query.filter(Product.discount_pct >= min_discount)
        if max_discount is not None:
            query = query.filter(Product.discount_pct <= max_discount)

        # Apply sorting
        if order == 'asc':
            query = query.order_by(getattr(Product, sort_by))
        else:
            query = query.order_by(getattr(Product, sort_by).desc())

        # Execute paginated query
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # Prepare response
        products = pagination.items
        product_data = []
        for product in products:
            product_dict = product.serialize()
            # Add frontend-specific fields
            product_dict.update({
                'id': str(product.product_id),
                'name': product.product_name,
                'description': product.product_description,
                'price': float(product.selling_price),
                'originalPrice': float(product.cost_price),
                'discount_pct': float(product.discount_pct),
                'discount_amount': float(product.cost_price - product.selling_price)
            })
            
            # Get primary media
            media = ProductController.get_product_media(product.product_id)
            if media:
                product_dict['primary_image'] = media['url']
                product_dict['image'] = media['url']
            
            product_data.append(product_dict)

        return jsonify({
            'products': product_data,
            'pagination': {
                'total': pagination.total,
                'pages': pagination.pages,
                'current_page': page,
                'per_page': per_page,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        })

    except Exception as e:
        print(f"Error in get_product_discounts: {str(e)}")
        return jsonify({
            'error': 'Failed to fetch discounted products',
            'message': str(e)
        }), 500 

@product_bp.route('/api/products/search-suggestions', methods=['GET'])
@cross_origin()
def get_search_suggestions():
    """
    Get search suggestions for products, categories, and brands
    ---
    tags:
      - Products
    parameters:
      - in: query
        name: q
        type: string
        required: true
        description: Search query string
    responses:
      200:
        description: Search suggestions retrieved successfully
        schema:
          type: object
          properties:
            products:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                  name:
                    type: string
                  price:
                    type: number
                    format: float
                  primary_image:
                    type: string
            categories:
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
            brands:
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
      500:
        description: Internal server error
    """
    try:
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify({
                'products': [],
                'categories': [],
                'brands': []
            })

        # Get products suggestions
        products = Product.query.filter(
            Product.deleted_at.is_(None),
            Product.active_flag.is_(True),
            Product.approval_status == 'approved',
            or_(
                Product.product_name.ilike(f'%{query}%'),
                Product.sku.ilike(f'%{query}%')
            )
        ).limit(5).all()

        # Get category suggestions
        categories = Category.query.filter(
            Category.name.ilike(f'%{query}%')
        ).limit(5).all()

        # Get brand suggestions
        brands = Brand.query.filter(
            Brand.name.ilike(f'%{query}%'),
            Brand.deleted_at.is_(None)
        ).limit(5).all()

        return jsonify({
            'products': [{
                'id': str(p.product_id),
                'name': p.product_name,
                'price': float(p.selling_price),
                'primary_image': ProductController.get_product_media(p.product_id)['url'] if ProductController.get_product_media(p.product_id) else None
            } for p in products],
            'categories': [c.serialize() for c in categories],
            'brands': [b.serialize() for b in brands]
        })

    except Exception as e:
        print(f"Error in get_search_suggestions: {str(e)}")
        return jsonify({
            'error': str(e),
            'products': [],
            'categories': [],
            'brands': []
        }), 500 