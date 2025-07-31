# controllers/shop/shop_variant_controller.py
from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.shop.shop_product import ShopProduct
from models.shop.shop_product_variant import ShopProductVariant, ShopVariantAttributeValue
from models.shop.shop_product_stock import ShopProductStock
from models.shop.shop_product_media import ShopProductMedia
from models.shop.shop_attribute import ShopAttribute, ShopAttributeValue
from models.enums import MediaType
from common.database import db
from common.response import success_response, error_response
import json
from datetime import datetime, timezone

class ShopVariantController:
    
    @staticmethod
    @jwt_required()
    def create_variant(parent_id):
        """Create a new product variant"""
        try:
            current_user = get_jwt_identity()
            data = request.get_json()
            
            # Validate parent product exists and belongs to user's shop
            parent_product = ShopProduct.query.filter_by(
                product_id=parent_id,
                deleted_at=None
            ).first()
            
            if not parent_product:
                return error_response("Parent product not found", 404)
            
            # Validate required fields
            required_fields = ['sku', 'selling_price', 'attributes']
            for field in required_fields:
                if field not in data:
                    return error_response(f"Missing required field: {field}", 400)
            
            # Check if SKU already exists
            if ShopProduct.query.filter_by(sku=data['sku'], deleted_at=None).first():
                return error_response("SKU already exists", 400)
            
            # Validate attributes
            attributes = data['attributes']
            if not isinstance(attributes, dict) or not attributes:
                return error_response("Attributes must be a non-empty object", 400)
            
            try:
                # Create variant product (inherits most from parent)
                variant_product = ShopProduct(
                    shop_id=parent_product.shop_id,
                    category_id=parent_product.category_id,
                    brand_id=parent_product.brand_id,
                    parent_product_id=parent_id,
                    sku=data['sku'],
                    product_name=parent_product.product_name,
                    product_description=parent_product.product_description,
                    cost_price=data.get('cost_price', parent_product.cost_price),
                    selling_price=data['selling_price'],
                    discount_pct=parent_product.discount_pct,
                    special_price=data.get('special_price'),
                    special_start=data.get('special_start'),
                    special_end=data.get('special_end'),
                    active_flag=data.get('active_flag', True),
                    is_published=parent_product.is_published
                )
                
                db.session.add(variant_product)
                db.session.flush()  # Get the product_id
                
                # Create variant relationship record
                variant_relation = ShopProductVariant(
                    parent_product_id=parent_id,
                    variant_product_id=variant_product.product_id,
                    variant_sku=data['sku'],
                    variant_name=data.get('variant_name'),
                    attribute_combination=attributes,
                    price_override=data.get('price_override'),
                    cost_override=data.get('cost_override'),
                    is_default=data.get('is_default', False),
                    sort_order=data.get('sort_order', 0)
                )
                
                db.session.add(variant_relation)
                db.session.flush()
                
                # Create variant attribute values for easier querying
                for attr_name, attr_value in attributes.items():
                    # Find the attribute by name in the category
                    attribute = ShopAttribute.query.filter_by(
                        shop_id=parent_product.shop_id,
                        category_id=parent_product.category_id,
                        name=attr_name,
                        deleted_at=None
                    ).first()
                    
                    if attribute:
                        # Try to find existing attribute value
                        attr_value_obj = ShopAttributeValue.query.filter_by(
                            attribute_id=attribute.attribute_id,
                            value=attr_value,
                            deleted_at=None
                        ).first()
                        
                        variant_attr = ShopVariantAttributeValue(
                            variant_id=variant_relation.variant_id,
                            attribute_id=attribute.attribute_id,
                            value_id=attr_value_obj.value_id if attr_value_obj else None,
                            value_text=attr_value if not attr_value_obj else None
                        )
                        
                        db.session.add(variant_attr)
                
                # Create stock record
                stock = ShopProductStock(
                    product_id=variant_product.product_id,
                    stock_qty=data.get('stock_qty', 0),
                    low_stock_threshold=data.get('low_stock_threshold', 0)
                )
                
                db.session.add(stock)
                
                # If this is marked as default, unset other defaults
                if data.get('is_default', False):
                    ShopProductVariant.query.filter_by(
                        parent_product_id=parent_id
                    ).update({'is_default': False})
                    variant_relation.is_default = True
                
                db.session.commit()
                
                # Return created variant data
                variant_product.stock = stock
                return success_response({
                    "variant": variant_relation.serialize(),
                    "message": "Variant created successfully"
                })
                
            except Exception as e:
                db.session.rollback()
                raise e
                
        except Exception as e:
            return error_response(f"Failed to create variant: {str(e)}", 500)
    
    @staticmethod
    @jwt_required()
    def get_variants(parent_id):
        """Get all variants for a parent product"""
        try:
            # Validate parent product exists
            parent_product = ShopProduct.query.filter_by(
                product_id=parent_id,
                deleted_at=None
            ).first()
            
            if not parent_product:
                return error_response("Parent product not found", 404)
            
            # Get all variants with their relationships
            variant_relations = ShopProductVariant.query.filter_by(
                parent_product_id=parent_id
            ).order_by(ShopProductVariant.sort_order, ShopProductVariant.variant_id).all()
            
            variants = []
            for relation in variant_relations:
                variant_data = relation.serialize()
                variants.append(variant_data)
            
            return success_response({
                "parent_product": parent_product.serialize(include_variants=False),
                "variants": variants,
                "total_variants": len(variants)
            })
            
        except Exception as e:
            return error_response(f"Failed to get variants: {str(e)}", 500)
    
    @staticmethod
    @jwt_required()
    def update_variant(variant_id):
        """Update a specific variant"""
        try:
            data = request.get_json()
            
            # Find variant relation
            variant_relation = ShopProductVariant.query.get(variant_id)
            if not variant_relation:
                return error_response("Variant not found", 404)
            
            # Get the variant product
            variant_product = variant_relation.variant_product
            if not variant_product:
                return error_response("Variant product not found", 404)
            
            try:
                # Update variant product fields
                if 'sku' in data and data['sku'] != variant_product.sku:
                    # Check if new SKU is unique
                    if ShopProduct.query.filter(
                        ShopProduct.sku == data['sku'],
                        ShopProduct.product_id != variant_product.product_id,
                        ShopProduct.deleted_at == None
                    ).first():
                        return error_response("SKU already exists", 400)
                    variant_product.sku = data['sku']
                    variant_relation.variant_sku = data['sku']
                
                # Update pricing
                if 'selling_price' in data:
                    variant_product.selling_price = data['selling_price']
                
                if 'cost_price' in data:
                    variant_product.cost_price = data['cost_price']
                
                if 'special_price' in data:
                    variant_product.special_price = data['special_price']
                
                # Update variant relation fields
                if 'variant_name' in data:
                    variant_relation.variant_name = data['variant_name']
                
                if 'price_override' in data:
                    variant_relation.price_override = data['price_override']
                
                if 'cost_override' in data:
                    variant_relation.cost_override = data['cost_override']
                
                if 'sort_order' in data:
                    variant_relation.sort_order = data['sort_order']
                
                if 'is_active' in data:
                    variant_product.active_flag = data['is_active']
                    variant_relation.is_active = data['is_active']
                
                # Handle default variant change
                if 'is_default' in data and data['is_default']:
                    # Unset other defaults
                    ShopProductVariant.query.filter_by(
                        parent_product_id=variant_relation.parent_product_id
                    ).update({'is_default': False})
                    variant_relation.is_default = True
                
                # Update stock if provided
                if 'stock_qty' in data or 'low_stock_threshold' in data:
                    stock = variant_product.stock
                    if not stock:
                        stock = ShopProductStock(product_id=variant_product.product_id)
                        db.session.add(stock)
                    
                    if 'stock_qty' in data:
                        stock.stock_qty = data['stock_qty']
                    if 'low_stock_threshold' in data:
                        stock.low_stock_threshold = data['low_stock_threshold']
                
                # Update attributes if provided
                if 'attributes' in data:
                    # Delete existing variant attributes
                    ShopVariantAttributeValue.query.filter_by(
                        variant_id=variant_id
                    ).delete()
                    
                    # Update the JSON field
                    variant_relation.attribute_combination = data['attributes']
                    
                    # Recreate variant attribute values
                    for attr_name, attr_value in data['attributes'].items():
                        attribute = ShopAttribute.query.filter_by(
                            shop_id=variant_product.shop_id,
                            category_id=variant_product.category_id,
                            name=attr_name,
                            deleted_at=None
                        ).first()
                        
                        if attribute:
                            attr_value_obj = ShopAttributeValue.query.filter_by(
                                attribute_id=attribute.attribute_id,
                                value=attr_value,
                                deleted_at=None
                            ).first()
                            
                            variant_attr = ShopVariantAttributeValue(
                                variant_id=variant_id,
                                attribute_id=attribute.attribute_id,
                                value_id=attr_value_obj.value_id if attr_value_obj else None,
                                value_text=attr_value if not attr_value_obj else None
                            )
                            
                            db.session.add(variant_attr)
                
                variant_relation.updated_at = datetime.now(timezone.utc)
                variant_product.updated_at = datetime.now(timezone.utc)
                
                db.session.commit()
                
                return success_response({
                    "variant": variant_relation.serialize(),
                    "message": "Variant updated successfully"
                })
                
            except Exception as e:
                db.session.rollback()
                raise e
                
        except Exception as e:
            return error_response(f"Failed to update variant: {str(e)}", 500)
    
    @staticmethod
    @jwt_required()
    def delete_variant(variant_id):
        """Delete a variant (soft delete)"""
        try:
            variant_relation = ShopProductVariant.query.get(variant_id)
            if not variant_relation:
                return error_response("Variant not found", 404)
            
            variant_product = variant_relation.variant_product
            
            try:
                # Soft delete the variant product
                variant_product.deleted_at = datetime.now(timezone.utc)
                variant_product.active_flag = False
                
                # Delete variant relation
                db.session.delete(variant_relation)
                
                # Delete variant attribute values
                ShopVariantAttributeValue.query.filter_by(
                    variant_id=variant_id
                ).delete()
                
                db.session.commit()
                
                return success_response({"message": "Variant deleted successfully"})
                
            except Exception as e:
                db.session.rollback()
                raise e
                
        except Exception as e:
            return error_response(f"Failed to delete variant: {str(e)}", 500)
    
    @staticmethod
    def generate_variant_sku(parent_sku, attributes):
        """
        Generate variant SKU following industry standards
        Format: PARENT-SKU-ATTR1-ATTR2-ATTR3
        """
        attr_codes = []
        
        # Common attribute abbreviations
        attr_abbreviations = {
            'color': 'CLR',
            'size': 'SZ',
            'storage': 'STG',
            'memory': 'MEM',
            'material': 'MAT',
            'style': 'STY',
            'weight': 'WGT',
            'capacity': 'CAP'
        }
        
        for key, value in attributes.items():
            if isinstance(value, str):
                # Use predefined abbreviation or create one
                attr_key = attr_abbreviations.get(key.lower(), key.upper()[:3])
                value_code = value.upper().replace(' ', '').replace('-', '')[:3]
                attr_codes.append(f"{attr_key}{value_code}")
        
        variant_suffix = '-'.join(attr_codes)
        
        # Ensure total SKU length doesn't exceed 50 characters
        max_suffix_length = 50 - len(parent_sku) - 1  # -1 for the dash
        if len(variant_suffix) > max_suffix_length:
            variant_suffix = variant_suffix[:max_suffix_length]
        
        return f"{parent_sku}-{variant_suffix}"
    
    @staticmethod
    @jwt_required()  
    def bulk_create_variants(parent_id):
        """Create multiple variants from attribute combinations"""
        try:
            data = request.get_json()
            print(f"Received data for bulk variant creation: {data}")
            
            # Validate parent product
            parent_product = ShopProduct.query.filter_by(
                product_id=parent_id,
                deleted_at=None
            ).first()
            
            if not parent_product:
                return error_response("Parent product not found", 404)
            
            attribute_combinations = data.get('combinations', [])
            print(f"Found {len(attribute_combinations)} combinations to process")
            if not attribute_combinations:
                return error_response("No attribute combinations provided", 400)
            
            created_variants = []
            errors = []
            
            try:
                for i, combination in enumerate(attribute_combinations):
                    try:
                        # Use provided SKU or generate one
                        if 'sku' in combination and combination['sku']:
                            variant_sku = combination['sku']
                        else:
                            # Generate SKU for this combination
                            variant_sku = ShopVariantController.generate_variant_sku(
                                parent_product.sku, 
                                combination.get('attributes', {})
                            )
                        
                        # Ensure uniqueness
                        counter = 1
                        original_sku = variant_sku
                        while ShopProduct.query.filter_by(sku=variant_sku, deleted_at=None).first():
                            variant_sku = f"{original_sku}-{counter:02d}"
                            counter += 1
                        
                        # Create variant product
                        variant_product = ShopProduct(
                            shop_id=parent_product.shop_id,
                            category_id=parent_product.category_id,
                            brand_id=parent_product.brand_id,
                            parent_product_id=parent_id,
                            sku=variant_sku,
                            product_name=parent_product.product_name,
                            product_description=parent_product.product_description,
                            cost_price=combination.get('cost_price', parent_product.cost_price),
                            selling_price=combination.get('selling_price', parent_product.selling_price),
                            discount_pct=parent_product.discount_pct,
                            active_flag=True,
                            is_published=parent_product.is_published
                        )
                        
                        db.session.add(variant_product)
                        db.session.flush()
                        
                        # Create variant relation
                        variant_relation = ShopProductVariant(
                            parent_product_id=parent_id,
                            variant_product_id=variant_product.product_id,
                            variant_sku=variant_sku,
                            variant_name=combination.get('name'),
                            attribute_combination=combination.get('attributes', {}),
                            sort_order=i
                        )
                        
                        db.session.add(variant_relation)
                        db.session.flush()
                        
                        # Create stock
                        stock = ShopProductStock(
                            product_id=variant_product.product_id,
                            stock_qty=combination.get('stock_qty', 0),
                            low_stock_threshold=combination.get('low_stock_threshold', 0)
                        )
                        
                        db.session.add(stock)
                        
                        # Handle media if provided
                        if 'media' in combination and combination['media']:
                            for media_item in combination['media']:
                                if media_item.get('url'):  # Only process if URL exists
                                    variant_media = ShopProductMedia(
                                        product_id=variant_product.product_id,
                                        type=MediaType(media_item.get('type', 'image')),
                                        url=media_item['url'],
                                        public_id=media_item.get('public_id'),
                                        sort_order=media_item.get('sort_order', 0),
                                        is_primary=media_item.get('is_primary', False),
                                        file_name=media_item.get('file_name'),
                                        file_size=media_item.get('file_size')
                                    )
                                    db.session.add(variant_media)
                        
                        created_variants.append(variant_relation.serialize())
                        
                    except Exception as e:
                        print(f"Error creating variant {i+1}: {str(e)}")
                        errors.append(f"Combination {i+1}: {str(e)}")
                        continue
                
                if created_variants:
                    db.session.commit()
                else:
                    db.session.rollback()
                    return error_response("No variants created due to errors", 400)
                
                response_data = {
                    "created_variants": created_variants,
                    "created_count": len(created_variants),
                    "total_combinations": len(attribute_combinations),
                    "message": f"Successfully created {len(created_variants)} variants"
                }
                
                if errors:
                    response_data["errors"] = errors
                
                return success_response(response_data)
                
            except Exception as e:
                db.session.rollback()
                raise e
                
        except Exception as e:
            return error_response(f"Failed to create variants: {str(e)}", 500)
    
    @staticmethod
    @jwt_required()
    def update_variant_attributes(variant_id):
        """Update only the attributes of a variant"""
        try:
            data = request.get_json()
            
            # Find variant relation
            variant_relation = ShopProductVariant.query.get(variant_id)
            if not variant_relation:
                return error_response("Variant not found", 404)
            
            # Get the variant product
            variant_product = variant_relation.variant_product
            if not variant_product:
                return error_response("Variant product not found", 404)
            
            attribute_combination = data.get('attribute_combination', {})
            if not attribute_combination:
                return error_response("No attributes provided", 400)
            
            try:
                # Delete existing variant attributes
                ShopVariantAttributeValue.query.filter_by(
                    variant_id=variant_id
                ).delete()
                
                # Update the JSON field
                variant_relation.attribute_combination = attribute_combination
                
                # Recreate variant attribute values
                for attr_name, attr_value in attribute_combination.items():
                    attribute = ShopAttribute.query.filter_by(
                        shop_id=variant_product.shop_id,
                        category_id=variant_product.category_id,
                        name=attr_name,
                        deleted_at=None
                    ).first()
                    
                    if attribute:
                        attr_value_obj = ShopAttributeValue.query.filter_by(
                            attribute_id=attribute.attribute_id,
                            value=attr_value,
                            deleted_at=None
                        ).first()
                        
                        variant_attr = ShopVariantAttributeValue(
                            variant_id=variant_id,
                            attribute_id=attribute.attribute_id,
                            value_id=attr_value_obj.value_id if attr_value_obj else None,
                            value_text=attr_value if not attr_value_obj else None
                        )
                        
                        db.session.add(variant_attr)
                
                variant_relation.updated_at = datetime.now(timezone.utc)
                
                db.session.commit()
                
                return success_response({
                    "variant": variant_relation.serialize(),
                    "message": "Variant attributes updated successfully"
                })
                
            except Exception as e:
                db.session.rollback()
                raise e
                
        except Exception as e:
            return error_response(f"Failed to update variant attributes: {str(e)}", 500)
