
from flask import request, jsonify
from common.database import db
from models.shop.shop_product import ShopProduct
from models.category import Category
from models.brand import Brand
from models.shop.shop_product_media import ShopProductMedia
from models.enums import MediaType
from sqlalchemy import desc, or_, func
from common.decorators import superadmin_required
from datetime import datetime, timezone

class ShopProductController:
    @staticmethod
    def get_product_media(product_id):
        """Get primary media for a shop product"""
        primary_media = ShopProductMedia.query.filter_by(
            product_id=product_id,
            deleted_at=None,
            type=MediaType.IMAGE
        ).order_by(
            ShopProductMedia.sort_order
        ).first()

        return primary_media.serialize() if primary_media else None

    @staticmethod
    def get_all_products():
        """Get all shop products with pagination and filtering"""
        try:
            page = request.args.get('page', 1, type=int)
            per_page = min(request.args.get('per_page', 10, type=int), 50)
            sort_by = request.args.get('sort_by', 'created_at')
            order = request.args.get('order', 'desc')
            category_id = request.args.get('category_id')
            brand_id = request.args.get('brand_id')
            min_price = request.args.get('min_price', type=float)
            max_price = request.args.get('max_price', type=float)
            search = request.args.get('search', '')

            query = ShopProduct.query.filter(
                ShopProduct.deleted_at.is_(None),
                ShopProduct.active_flag.is_(True)
            )

            if category_id:
                query = query.filter(ShopProduct.category_id == category_id)
            
            if brand_id:
                query = query.filter(ShopProduct.brand_id == brand_id)

            if min_price is not None:
                query = query.filter(ShopProduct.selling_price >= min_price)
            if max_price is not None:
                query = query.filter(ShopProduct.selling_price <= max_price)

            if search:
                search_term = f"%{search}%"
                query = query.join(Category).join(Brand, isouter=True).filter(
                    or_(
                        ShopProduct.product_name.ilike(search_term),
                        ShopProduct.product_description.ilike(search_term),
                        ShopProduct.sku.ilike(search_term),
                        Category.name.ilike(search_term),
                        Brand.name.ilike(search_term)
                    )
                )

            if sort_by and hasattr(ShopProduct, sort_by):
                if order == 'asc':
                    query = query.order_by(getattr(ShopProduct, sort_by))
                else:
                    query = query.order_by(desc(getattr(ShopProduct, sort_by)))

            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            
            products = pagination.items
            product_data = []
            for product in products:
                product_dict = product.serialize()
                media = ShopProductController.get_product_media(product.product_id)
                if media:
                    product_dict['primary_image'] = media['url']
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
            return jsonify({'error': str(e)}), 500

    @staticmethod
    def get_product(product_id):
        """Get a single shop product by ID"""
        product = ShopProduct.query.filter_by(
            product_id=product_id,
            deleted_at=None,
            active_flag=True
        ).first_or_404()
        
        product_dict = product.serialize()
        media = ShopProductController.get_product_media(product_id)
        if media:
            product_dict['primary_image'] = media['url']
        
        return jsonify(product_dict)

    @staticmethod
    @superadmin_required
    def create_product():
        """Create a new shop product"""
        data = request.get_json()
        
        new_product = ShopProduct(
            product_name=data.get('product_name'),
            product_description=data.get('product_description'),
            sku=data.get('sku'),
            category_id=data.get('category_id'),
            brand_id=data.get('brand_id'),
            cost_price=data.get('cost_price'),
            selling_price=data.get('selling_price'),
            is_published=data.get('is_published', False)
        )
        
        db.session.add(new_product)
        db.session.commit()
        
        return jsonify(new_product.serialize()), 201

    @staticmethod
    @superadmin_required
    def update_product(product_id):
        """Update an existing shop product"""
        product = ShopProduct.query.get_or_404(product_id)
        data = request.get_json()
        
        product.product_name = data.get('product_name', product.product_name)
        product.product_description = data.get('product_description', product.product_description)
        product.sku = data.get('sku', product.sku)
        product.category_id = data.get('category_id', product.category_id)
        product.brand_id = data.get('brand_id', product.brand_id)
        product.cost_price = data.get('cost_price', product.cost_price)
        product.selling_price = data.get('selling_price', product.selling_price)
        product.is_published = data.get('is_published', product.is_published)
        product.active_flag = data.get('active_flag', product.active_flag)
        
        db.session.commit()
        
        return jsonify(product.serialize())

    @staticmethod
    @superadmin_required
    def delete_product(product_id):
        """Delete a shop product"""
        product = ShopProduct.query.get_or_404(product_id)
        
        product.deleted_at = datetime.now(timezone.utc)
        db.session.commit()
        
        return jsonify({'message': 'Product deleted successfully'})
