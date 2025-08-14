from flask import request, jsonify
from common.database import db
from models.shop.shop_product import ShopProduct
from models.shop.shop_category import ShopCategory
from models.shop.shop_brand import ShopBrand
from models.shop.shop import Shop
from models.shop.shop_product_media import ShopProductMedia
from models.shop.shop_product_attribute import ShopProductAttribute
from models.shop.shop_product_stock import ShopProductStock
from models.shop.shop_product_meta import ShopProductMeta
from models.shop.shop_product_variant import ShopProductVariant, ShopVariantAttributeValue
from models.enums import MediaType
from sqlalchemy import desc, or_, func, and_
from datetime import datetime, timezone

class PublicShopProductController:
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
    def get_optimized_media(product_id):
        """Get optimized media response for frontend (only essential fields)"""
        media_list = ShopProductMedia.query.filter_by(
            product_id=product_id,
            deleted_at=None
        ).order_by(ShopProductMedia.sort_order).all()

        if not media_list:
            return {
                'images': [],
                'videos': [],
                'primary_image': None,
                'total_media': 0
            }

        images = []
        videos = []
        primary_image = None
        
        # Find the minimum sort_order to determine primary image
        min_sort_order = None
        if media_list:
            min_sort_order = min(media.sort_order for media in media_list if media.sort_order is not None)

        for index, media in enumerate(media_list):
            # Determine if this is primary based on sort_order logic
            is_primary = False
            if media.type == MediaType.IMAGE:
                if min_sort_order is not None and media.sort_order == min_sort_order:
                    is_primary = True
                elif min_sort_order is None and media.is_primary:
                    # Fallback to is_primary field if sort_order is not available
                    is_primary = True
                elif min_sort_order is None and not any(m.is_primary for m in media_list if m.type == MediaType.IMAGE) and index == 0:
                    # Final fallback: first image if nothing else is marked as primary
                    is_primary = True
            
            # Only include essential fields
            media_item = {
                'url': media.url,
                'type': media.type.value if hasattr(media.type, 'value') else str(media.type),
                'is_primary': is_primary
            }

            # Set primary image URL
            if is_primary and media.type == MediaType.IMAGE:
                primary_image = media.url

            # Categorize by type
            if media.type == MediaType.IMAGE:
                images.append(media_item)
            elif media.type == MediaType.VIDEO:
                videos.append(media_item)

        return {
            'images': images,
            'videos': videos,
            'primary_image': primary_image,
            'total_media': len(media_list)
        }

    @staticmethod
    def get_all_product_media(product_id):
        """Get all media for a shop product (images, videos, etc.)"""
        all_media = ShopProductMedia.query.filter_by(
            product_id=product_id,
            deleted_at=None
        ).order_by(
            ShopProductMedia.sort_order,
            ShopProductMedia.media_id
        ).all()

        if not all_media:
            return []

        # Find the minimum sort_order to determine primary image
        min_sort_order = None
        if all_media:
            min_sort_order = min(media.sort_order for media in all_media if media.sort_order is not None)

        media_data = []
        for index, media in enumerate(all_media):
            # Determine if this is primary based on sort_order logic
            is_primary = False
            if media.type == MediaType.IMAGE:
                if min_sort_order is not None and media.sort_order == min_sort_order:
                    is_primary = True
                elif min_sort_order is None and media.is_primary:
                    # Fallback to is_primary field if sort_order is not available
                    is_primary = True
                elif min_sort_order is None and not any(m.is_primary for m in all_media if m.type == MediaType.IMAGE) and index == 0:
                    # Final fallback: first image if nothing else is marked as primary
                    is_primary = True

            # Only include essential fields for optimized response
            media_item = {
                'url': media.url,
                'type': media.type.value if hasattr(media.type, 'value') else str(media.type),
                'is_primary': is_primary
            }
            media_data.append(media_item)

        return media_data

    @staticmethod
    def enhance_product_with_meta(product_dict, product_id):
        """Enhance product data with meta information"""
        # Get product meta information
        meta = ShopProductMeta.query.filter_by(product_id=product_id).first()
        
        if meta:
            # Override product_description with short_desc for better UX
            product_dict['product_description'] = meta.short_desc or product_dict.get('product_description', '')
            product_dict['short_description'] = meta.short_desc
            product_dict['full_description'] = meta.full_desc
            product_dict['meta_title'] = meta.meta_title
            product_dict['meta_description'] = meta.meta_desc
            product_dict['meta_keywords'] = meta.meta_keywords
        else:
            # Fallback if meta doesn't exist (though it should always exist)
            product_dict['short_description'] = product_dict.get('product_description', '')
            product_dict['full_description'] = product_dict.get('product_description', '')
            product_dict['meta_title'] = None
            product_dict['meta_description'] = None
            product_dict['meta_keywords'] = None
        
        return product_dict

    @staticmethod
    def get_products_by_shop(shop_id):
        """Get all published products for a specific shop with pagination and filtering"""
        try:
            # Verify shop exists and is active
            shop = Shop.query.filter(
                Shop.shop_id == shop_id,
                Shop.deleted_at.is_(None),
                Shop.is_active.is_(True)
            ).first()

            if not shop:
                return jsonify({
                    'success': False,
                    'message': 'Shop not found or not active'
                }), 404

            # Get query parameters
            page = request.args.get('page', 1, type=int)
            per_page = min(request.args.get('per_page', 20, type=int), 50)
            sort_by = request.args.get('sort_by', 'created_at')
            order = request.args.get('order', 'desc')
            category_id = request.args.get('category_id', type=int)
            brand_id = request.args.get('brand_id', type=int)
            min_price = request.args.get('min_price', type=float)
            max_price = request.args.get('max_price', type=float)
            # New: discount range filtering (percentage). NULL discount treated as 0.
            discount_min = request.args.get('discount_min', type=float)
            discount_max = request.args.get('discount_max', type=float)
            search = request.args.get('search', '').strip()

            # Build base query for shop products (exclude variant products)
            query = ShopProduct.query.filter(
                ShopProduct.shop_id == shop_id,
                ShopProduct.deleted_at.is_(None),
                ShopProduct.active_flag.is_(True),
                ShopProduct.is_published.is_(True),  # Only show published products
                ShopProduct.parent_product_id.is_(None)  # Exclude variant products - only show parent products
            )

            # Apply filters
            if category_id:
                query = query.filter(ShopProduct.category_id == category_id)
            
            if brand_id:
                query = query.filter(ShopProduct.brand_id == brand_id)

            # Price filtering based on current selling price or special price
            if min_price is not None:
                query = query.filter(
                    or_(
                        and_(
                            ShopProduct.special_price.is_(None),
                            ShopProduct.selling_price >= min_price
                        ),
                        and_(
                            ShopProduct.special_price.isnot(None),
                            ShopProduct.special_start <= datetime.now(timezone.utc).date(),
                            ShopProduct.special_end >= datetime.now(timezone.utc).date(),
                            ShopProduct.special_price >= min_price
                        ),
                        and_(
                            ShopProduct.special_price.isnot(None),
                            or_(
                                ShopProduct.special_start > datetime.now(timezone.utc).date(),
                                ShopProduct.special_end < datetime.now(timezone.utc).date()
                            ),
                            ShopProduct.selling_price >= min_price
                        )
                    )
                )

            if max_price is not None:
                query = query.filter(
                    or_(
                        and_(
                            ShopProduct.special_price.is_(None),
                            ShopProduct.selling_price <= max_price
                        ),
                        and_(
                            ShopProduct.special_price.isnot(None),
                            ShopProduct.special_start <= datetime.now(timezone.utc).date(),
                            ShopProduct.special_end >= datetime.now(timezone.utc).date(),
                            ShopProduct.special_price <= max_price
                        ),
                        and_(
                            ShopProduct.special_price.isnot(None),
                            or_(
                                ShopProduct.special_start > datetime.now(timezone.utc).date(),
                                ShopProduct.special_end < datetime.now(timezone.utc).date()
                            ),
                            ShopProduct.selling_price <= max_price
                        )
                    )
                )

            # Discount filtering (COALESCE to 0)
            if discount_min is not None:
                # Clamp to [0,100]
                try:
                    discount_min = max(0.0, min(100.0, float(discount_min)))
                except (TypeError, ValueError):
                    discount_min = None
            if discount_max is not None:
                try:
                    discount_max = max(0.0, min(100.0, float(discount_max)))
                except (TypeError, ValueError):
                    discount_max = None

            if discount_min is not None:
                query = query.filter(func.coalesce(ShopProduct.discount_pct, 0) >= discount_min)
            if discount_max is not None:
                query = query.filter(func.coalesce(ShopProduct.discount_pct, 0) <= discount_max)

            # Search functionality
            if search:
                search_term = f"%{search}%"
                query = query.join(ShopCategory, ShopProduct.category_id == ShopCategory.category_id)\
                            .join(ShopBrand, ShopProduct.brand_id == ShopBrand.brand_id, isouter=True)\
                            .filter(
                                or_(
                                    ShopProduct.product_name.ilike(search_term),
                                    ShopProduct.product_description.ilike(search_term),
                                    ShopProduct.sku.ilike(search_term),
                                    ShopCategory.name.ilike(search_term),
                                    ShopBrand.name.ilike(search_term)
                                )
                            )

            # Sorting
            valid_sort_fields = ['created_at', 'product_name', 'selling_price', 'special_price']
            if sort_by in valid_sort_fields and hasattr(ShopProduct, sort_by):
                if order == 'asc':
                    query = query.order_by(getattr(ShopProduct, sort_by))
                else:
                    query = query.order_by(desc(getattr(ShopProduct, sort_by)))
            else:
                query = query.order_by(desc(ShopProduct.created_at))

            # Execute pagination
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            
            products = pagination.items
            product_data = []

            for product in products:
                product_dict = product.serialize()
                
                # Enhance with meta information
                product_dict = PublicShopProductController.enhance_product_with_meta(
                    product_dict, product.product_id
                )
                
                # Get primary image
                media = PublicShopProductController.get_product_media(product.product_id)
                if media:
                    product_dict['primary_image'] = media['url']
                
                # Get stock information
                stock = ShopProductStock.query.filter_by(
                    product_id=product.product_id
                ).first()
                
                if stock:
                    product_dict['stock'] = stock.serialize()
                    product_dict['is_in_stock'] = stock.stock_qty > 0
                else:
                    product_dict['is_in_stock'] = False
                
                product_data.append(product_dict)

            return jsonify({
                'success': True,
                'shop': shop.serialize(),
                'products': product_data,
                'pagination': {
                    'page': pagination.page,
                    'per_page': pagination.per_page,
                    'total_pages': pagination.pages,
                    'total_items': pagination.total,
                    'has_next': pagination.has_next,
                    'has_prev': pagination.has_prev
                },
                'filters_applied': {
                    'category_id': category_id,
                    'brand_id': brand_id,
                    'min_price': min_price,
                    'max_price': max_price,
                    'discount_min': discount_min,
                    'discount_max': discount_max,
                    'search': search,
                    'sort_by': sort_by,
                    'order': order
                }
            }), 200

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Error fetching products: {str(e)}'
            }), 500

    @staticmethod
    def get_product_by_id(shop_id, product_id):
        """Get a specific product from a shop"""
        try:
            # Verify shop exists and is active
            shop = Shop.query.filter(
                Shop.shop_id == shop_id,
                Shop.deleted_at.is_(None),
                Shop.is_active.is_(True)
            ).first()

            if not shop:
                return jsonify({
                    'success': False,
                    'message': 'Shop not found or not active'
                }), 404

            # Get the product
            product = ShopProduct.query.filter(
                ShopProduct.product_id == product_id,
                ShopProduct.shop_id == shop_id,
                ShopProduct.deleted_at.is_(None),
                ShopProduct.active_flag.is_(True),
                ShopProduct.is_published.is_(True)
            ).first()

            if not product:
                return jsonify({
                    'success': False,
                    'message': 'Product not found in this shop'
                }), 404

            # Get product details
            product_dict = product.serialize()
            
            # Enhance with meta information
            product_dict = PublicShopProductController.enhance_product_with_meta(
                product_dict, product.product_id
            )
            
            # Get optimized media data
            media_data = PublicShopProductController.get_optimized_media(product.product_id)
            product_dict['media'] = media_data
            
            # Provide primary image for backward compatibility
            product_dict['primary_image'] = media_data.get('primary_image')
            
            # Get stock information
            stock = ShopProductStock.query.filter_by(
                product_id=product.product_id
            ).first()
            
            if stock:
                product_dict['stock'] = stock.serialize()
                product_dict['is_in_stock'] = stock.stock_qty > 0
            else:
                product_dict['is_in_stock'] = False

            # Get variant information if this product has variants or is a variant
            parent_id = product.parent_product_id if product.parent_product_id else product_id
            
            # Check if this product has variants
            variants = ShopProductVariant.query.filter(
                ShopProductVariant.parent_product_id == parent_id,
                ShopProductVariant.is_active.is_(True)
            ).join(
                ShopProduct, ShopProductVariant.variant_product_id == ShopProduct.product_id
            ).filter(
                ShopProduct.shop_id == shop_id,
                ShopProduct.deleted_at.is_(None),
                ShopProduct.active_flag.is_(True),
                ShopProduct.is_published.is_(True)
            ).order_by(ShopProductVariant.sort_order, ShopProductVariant.created_at).all()

            # Add variant information to product response
            if variants:
                # Get available attributes for variant selection
                attributes_map = {}
                for variant in variants:
                    if variant.attribute_combination:
                        for attr_name, attr_value in variant.attribute_combination.items():
                            if attr_name not in attributes_map:
                                attributes_map[attr_name] = set()
                            attributes_map[attr_name].add(attr_value)

                attributes_list = []
                for attr_name, values in attributes_map.items():
                    attributes_list.append({
                        'name': attr_name,
                        'values': sorted(list(values))
                    })

                product_dict['has_variants'] = True
                product_dict['variant_attributes'] = attributes_list
                product_dict['total_variants'] = len(variants)
                product_dict['is_parent_product'] = parent_id == product_id
                
                # If this is a variant, include the current variant's attributes
                if product.parent_product_id:
                    current_variant = next((v for v in variants if v.variant_product_id == product_id), None)
                    if current_variant:
                        product_dict['current_variant_attributes'] = current_variant.attribute_combination
            else:
                product_dict['has_variants'] = False
                product_dict['variant_attributes'] = []
                product_dict['total_variants'] = 0
                product_dict['is_parent_product'] = True

            # Get related products (same category, different product, exclude variant products)
            related_products = ShopProduct.query.filter(
                ShopProduct.shop_id == shop_id,
                ShopProduct.category_id == product.category_id,
                ShopProduct.product_id != product_id,
                ShopProduct.parent_product_id.is_(None),  # Exclude variant products
                ShopProduct.deleted_at.is_(None),
                ShopProduct.active_flag.is_(True),
                ShopProduct.is_published.is_(True)
            ).limit(4).all()

            related_data = []
            for related in related_products:
                related_dict = related.serialize()
                
                # Enhance with meta information
                related_dict = PublicShopProductController.enhance_product_with_meta(
                    related_dict, related.product_id
                )
                
                media = PublicShopProductController.get_product_media(related.product_id)
                if media:
                    related_dict['primary_image'] = media['url']
                related_data.append(related_dict)

            return jsonify({
                'success': True,
                'shop': shop.serialize(),
                'product': product_dict,
                'related_products': related_data
            }), 200

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Error fetching product: {str(e)}'
            }), 500

    @staticmethod
    def get_featured_products(shop_id, limit=8):
        """Get featured/new products for a shop"""
        try:
            # Verify shop exists and is active
            shop = Shop.query.filter(
                Shop.shop_id == shop_id,
                Shop.deleted_at.is_(None),
                Shop.is_active.is_(True)
            ).first()

            if not shop:
                return jsonify({
                    'success': False,
                    'message': 'Shop not found or not active'
                }), 404

            limit = min(limit, 20)  # Max 20 featured products

            # Get latest published products
            products = ShopProduct.query.filter(
                ShopProduct.shop_id == shop_id,
                ShopProduct.deleted_at.is_(None),
                ShopProduct.active_flag.is_(True),
                ShopProduct.is_published.is_(True)
            ).order_by(desc(ShopProduct.created_at)).limit(limit).all()

            product_data = []
            for product in products:
                product_dict = product.serialize()
                
                # Enhance with meta information
                product_dict = PublicShopProductController.enhance_product_with_meta(
                    product_dict, product.product_id
                )
                
                # Get primary image
                media = PublicShopProductController.get_product_media(product.product_id)
                if media:
                    product_dict['primary_image'] = media['url']
                
                product_data.append(product_dict)

            return jsonify({
                'success': True,
                'shop': shop.serialize(),
                'featured_products': product_data,
                'total': len(product_data)
            }), 200

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Error fetching featured products: {str(e)}'
            }), 500

    @staticmethod
    def get_product_media_gallery(shop_id, product_id):
        """Get optimized media gallery for a specific product"""
        try:
            # Verify shop exists and is active
            shop = Shop.query.filter(
                Shop.shop_id == shop_id,
                Shop.deleted_at.is_(None),
                Shop.is_active.is_(True)
            ).first()

            if not shop:
                return jsonify({
                    'success': False,
                    'message': 'Shop not found or not active'
                }), 404

            # Verify product exists in this shop
            product = ShopProduct.query.filter(
                ShopProduct.product_id == product_id,
                ShopProduct.shop_id == shop_id,
                ShopProduct.deleted_at.is_(None),
                ShopProduct.active_flag.is_(True),
                ShopProduct.is_published.is_(True)
            ).first()

            if not product:
                return jsonify({
                    'success': False,
                    'message': 'Product not found in this shop'
                }), 404

            # Get optimized media (only essential fields)
            media_data = PublicShopProductController.get_optimized_media(product_id)

            return jsonify({
                'success': True,
                'product_id': product_id,
                'product_name': product.product_name,
                'media': media_data
            }), 200

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Error fetching product media: {str(e)}'
            }), 500

    @staticmethod
    def get_product_variants(shop_id, product_id):
        """Get all variants for a specific product"""
        try:
            # Verify shop exists and is active
            shop = Shop.query.filter(
                Shop.shop_id == shop_id,
                Shop.deleted_at.is_(None),
                Shop.is_active.is_(True)
            ).first()

            if not shop:
                return jsonify({
                    'success': False,
                    'message': 'Shop not found or not active'
                }), 404

            # Verify product exists in this shop (can be parent or variant)
            product = ShopProduct.query.filter(
                ShopProduct.product_id == product_id,
                ShopProduct.shop_id == shop_id,
                ShopProduct.deleted_at.is_(None),
                ShopProduct.active_flag.is_(True),
                ShopProduct.is_published.is_(True)
            ).first()

            if not product:
                return jsonify({
                    'success': False,
                    'message': 'Product not found in this shop'
                }), 404

            # Find the parent product ID
            parent_id = product.parent_product_id if product.parent_product_id else product_id

            # Get all variants for this parent product
            variants = ShopProductVariant.query.filter(
                ShopProductVariant.parent_product_id == parent_id,
                ShopProductVariant.is_active.is_(True)
            ).join(
                ShopProduct, ShopProductVariant.variant_product_id == ShopProduct.product_id
            ).filter(
                ShopProduct.shop_id == shop_id,
                ShopProduct.deleted_at.is_(None),
                ShopProduct.active_flag.is_(True),
                ShopProduct.is_published.is_(True)
            ).order_by(ShopProductVariant.sort_order, ShopProductVariant.created_at).all()

            variant_data = []
            for variant in variants:
                variant_dict = variant.serialize(include_media=True, include_parent_fallback=True)
                
                # Get stock information for the variant
                stock = ShopProductStock.query.filter_by(
                    product_id=variant.variant_product_id
                ).first()
                
                if stock:
                    variant_dict['stock'] = stock.serialize()
                    variant_dict['is_in_stock'] = stock.stock_qty > 0
                    variant_dict['stock_qty'] = stock.stock_qty
                else:
                    variant_dict['is_in_stock'] = False
                    variant_dict['stock_qty'] = 0

                # Get optimized media data for the variant
                media_data = PublicShopProductController.get_optimized_media(variant.variant_product_id)
                variant_dict['media'] = media_data
                variant_dict['primary_image'] = media_data.get('primary_image')

                variant_data.append(variant_dict)

            # Get parent product info
            parent_product = ShopProduct.query.filter_by(
                product_id=parent_id,
                shop_id=shop_id,
                deleted_at=None
            ).first()

            return jsonify({
                'success': True,
                'parent_product_id': parent_id,
                'parent_product_name': parent_product.product_name if parent_product else None,
                'variants': variant_data,
                'total_variants': len(variant_data)
            }), 200

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Error fetching product variants: {str(e)}'
            }), 500

    @staticmethod
    def get_variant_by_attributes(shop_id, product_id):
        """Get a specific variant by attribute combination"""
        try:
            data = request.get_json() or {}
            attributes = data.get('attributes', {})

            if not attributes:
                return jsonify({
                    'success': False,
                    'message': 'Attributes are required'
                }), 400

            # Verify shop exists and is active
            shop = Shop.query.filter(
                Shop.shop_id == shop_id,
                Shop.deleted_at.is_(None),
                Shop.is_active.is_(True)
            ).first()

            if not shop:
                return jsonify({
                    'success': False,
                    'message': 'Shop not found or not active'
                }), 404

            # Verify product exists in this shop
            product = ShopProduct.query.filter(
                ShopProduct.product_id == product_id,
                ShopProduct.shop_id == shop_id,
                ShopProduct.deleted_at.is_(None),
                ShopProduct.active_flag.is_(True),
                ShopProduct.is_published.is_(True)
            ).first()

            if not product:
                return jsonify({
                    'success': False,
                    'message': 'Product not found in this shop'
                }), 404

            # Find the parent product ID
            parent_id = product.parent_product_id if product.parent_product_id else product_id

            # Find variant by exact attribute combination
            # First get all variants for this parent, then filter in Python for more flexible matching
            variants = ShopProductVariant.query.filter(
                ShopProductVariant.parent_product_id == parent_id,
                ShopProductVariant.is_active.is_(True)
            ).join(
                ShopProduct, ShopProductVariant.variant_product_id == ShopProduct.product_id
            ).filter(
                ShopProduct.shop_id == shop_id,
                ShopProduct.deleted_at.is_(None),
                ShopProduct.active_flag.is_(True),
                ShopProduct.is_published.is_(True)
            ).all()

            # Find matching variant by comparing attributes in Python
            variant = None
            for v in variants:
                if v.attribute_combination and set(v.attribute_combination.items()) == set(attributes.items()):
                    variant = v
                    break

            if not variant:
                return jsonify({
                    'success': False,
                    'message': 'Variant not found for the specified attributes'
                }), 404

            # Serialize variant data
            variant_dict = variant.serialize(include_media=True, include_parent_fallback=True)
            
            # Get stock information
            stock = ShopProductStock.query.filter_by(
                product_id=variant.variant_product_id
            ).first()
            
            if stock:
                variant_dict['stock'] = stock.serialize()
                variant_dict['is_in_stock'] = stock.stock_qty > 0
                variant_dict['stock_qty'] = stock.stock_qty
            else:
                variant_dict['is_in_stock'] = False
                variant_dict['stock_qty'] = 0

            # Get optimized media data
            media_data = PublicShopProductController.get_optimized_media(variant.variant_product_id)
            variant_dict['media'] = media_data
            variant_dict['primary_image'] = media_data.get('primary_image')

            return jsonify({
                'success': True,
                'variant': variant_dict
            }), 200

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Error fetching variant: {str(e)}'
            }), 500

    @staticmethod
    def get_available_attributes(shop_id, product_id):
        """Get all available attributes and their values for a product's variants"""
        try:
            # Verify shop exists and is active
            shop = Shop.query.filter(
                Shop.shop_id == shop_id,
                Shop.deleted_at.is_(None),
                Shop.is_active.is_(True)
            ).first()

            if not shop:
                return jsonify({
                    'success': False,
                    'message': 'Shop not found or not active'
                }), 404

            # Verify product exists in this shop
            product = ShopProduct.query.filter(
                ShopProduct.product_id == product_id,
                ShopProduct.shop_id == shop_id,
                ShopProduct.deleted_at.is_(None),
                ShopProduct.active_flag.is_(True),
                ShopProduct.is_published.is_(True)
            ).first()

            if not product:
                return jsonify({
                    'success': False,
                    'message': 'Product not found in this shop'
                }), 404

            # Find the parent product ID
            parent_id = product.parent_product_id if product.parent_product_id else product_id

            # Get all variants for this parent product
            variants = ShopProductVariant.query.filter(
                ShopProductVariant.parent_product_id == parent_id,
                ShopProductVariant.is_active.is_(True)
            ).join(
                ShopProduct, ShopProductVariant.variant_product_id == ShopProduct.product_id
            ).filter(
                ShopProduct.shop_id == shop_id,
                ShopProduct.deleted_at.is_(None),
                ShopProduct.active_flag.is_(True),
                ShopProduct.is_published.is_(True)
            ).all()

            # Aggregate all available attributes and their values
            attributes_map = {}
            for variant in variants:
                if variant.attribute_combination:
                    for attr_name, attr_value in variant.attribute_combination.items():
                        if attr_name not in attributes_map:
                            attributes_map[attr_name] = set()
                        attributes_map[attr_name].add(attr_value)

            # Convert to list format
            attributes_list = []
            for attr_name, values in attributes_map.items():
                attributes_list.append({
                    'name': attr_name,
                    'values': sorted(list(values))
                })

            return jsonify({
                'success': True,
                'parent_product_id': parent_id,
                'attributes': attributes_list,
                'total_variants': len(variants)
            }), 200

        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Error fetching available attributes: {str(e)}'
            }), 500
