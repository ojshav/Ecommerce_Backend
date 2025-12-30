from flask import current_app
from flask_jwt_extended import get_jwt_identity
from models.product_media import ProductMedia
from models.enums import MediaType
from models.product import Product
from auth.models.models import MerchantProfile 
from common.database import db
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
import cloudinary
from services.s3_service import get_s3_service 

class MerchantProductMediaController:
    @staticmethod
    def _get_merchant_id_from_jwt(): 
        """Gets the merchant_id associated with the current JWT user."""
        user_id = get_jwt_identity()
        merchant = MerchantProfile.get_by_user_id(user_id) 
        if not merchant:
            raise FileNotFoundError("Merchant profile not found for the current user.") 
        return merchant.id 

    @staticmethod
    def list(pid):
        merchant_id = MerchantProductMediaController._get_merchant_id_from_jwt() 
        product = Product.query.filter_by(
            product_id=pid,
            merchant_id=merchant_id, 
            deleted_at=None
        ).first_or_404(
            description=f"Product with ID {pid} not found or you do not have permission to access its media."
        )
        return ProductMedia.query.filter_by(product_id=product.product_id, deleted_at=None).order_by(ProductMedia.sort_order).all()

    @staticmethod
    def create(product_id_param, data):
        merchant_id = MerchantProductMediaController._get_merchant_id_from_jwt() 
        product = Product.query.filter_by(
            product_id=product_id_param,
            merchant_id=merchant_id, 
            deleted_at=None
        ).first_or_404(
            description=f"Product with ID {product_id_param} not found or you do not have permission to add media to it."
        )

        if not data.get('url'):
            raise ValueError("Media URL is required.")
        if not data.get('type'):
            raise ValueError("Media type is required.")

        media_type_str = data.get('type').upper()
        try:
            media_type_enum = MediaType[media_type_str]
        except KeyError:
            allowed_types = [t.name for t in MediaType]
            raise ValueError(f"Invalid media type '{data.get('type')}'. Allowed types are: {', '.join(allowed_types)}")

        sort_order = data.get('sort_order', 0)
        try:
            sort_order = int(sort_order)
        except (ValueError, TypeError):
            sort_order = 0
       
        cloudinary_public_id = data.get('public_id', None) 

        try:
            pm = ProductMedia(
                product_id=product.product_id, 
                url=data['url'],
                type=media_type_enum,
                sort_order=sort_order,
                public_id=cloudinary_public_id 
            )
            db.session.add(pm)
            db.session.commit()
            return pm
        except IntegrityError as e:
            db.session.rollback()
            raise ValueError("Failed to create product media due to a data conflict.") from e
        except Exception as e:
            db.session.rollback()
            # Clean up uploaded file if DB save fails (both images and videos use S3 now)
            s3_key = data.get('public_id', None)
            if s3_key:
                try:
                    get_s3_service().delete_product_media(s3_key)
                except Exception as s3_e:
                    current_app.logger.error(f"Failed to delete orphaned S3 file {s3_key} after DB error: {s3_e}")
            raise RuntimeError(f"An unexpected error occurred while creating product media: {e}") from e

    @staticmethod
    def delete(mid):
        merchant_id = MerchantProductMediaController._get_merchant_id_from_jwt() 
        pm = ProductMedia.query.join(ProductMedia.product).filter( 
            ProductMedia.media_id == mid,
            ProductMedia.deleted_at == None,
            Product.merchant_id == merchant_id 
        ).first_or_404(
            description=f"Product media with ID {mid} not found or you do not have permission to delete it."
        )
        
        # Delete from S3 (both images and videos now use S3)
        if hasattr(pm, 'public_id') and pm.public_id:
            # Delete from S3 using the stored S3 key (in public_id field)
            # Also try URL as fallback
            s3_key = pm.public_id
            s3_url = pm.url
            
            # Try deleting using S3 key first, then URL
            deleted = False
            if s3_key and s3_key.startswith('products/'):
                deleted = get_s3_service().delete_product_media(s3_key)
            
            if not deleted and s3_url:
                # Fallback: try extracting key from URL
                deleted = get_s3_service().delete_product_media(s3_url)
            
            if not deleted:
                media_type = 'image' if pm.type == MediaType.IMAGE else 'video'
                current_app.logger.warning(f"Failed to delete product {media_type} from S3: {s3_key or s3_url}")

        # Hard delete the media row from the database
        try:
            db.session.delete(pm)
            db.session.commit()
            return pm
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to hard delete media {mid} from database: {e}")
            raise

    @staticmethod
    def get_by_id(mid):
        """Get a media item by ID"""
        merchant_id = MerchantProductMediaController._get_merchant_id_from_jwt()
        pm = ProductMedia.query.join(ProductMedia.product).filter(
            ProductMedia.media_id == mid,
            ProductMedia.deleted_at == None,
            Product.merchant_id == merchant_id
        ).first_or_404(
            description=f"Product media with ID {mid} not found or you do not have permission to access it."
        )
        return pm

    @staticmethod
    def set_thumbnail(pid, mid):
        """Set a media item as thumbnail for a product"""
        merchant_id = MerchantProductMediaController._get_merchant_id_from_jwt()
        
        # Verify the product belongs to the merchant
        product = Product.query.filter_by(
            product_id=pid,
            merchant_id=merchant_id,
            deleted_at=None
        ).first_or_404(
            description=f"Product with ID {pid} not found or you do not have permission to access it."
        )
        
        # Get the media item
        media = ProductMedia.query.filter_by(
            media_id=mid,
            product_id=pid,
            deleted_at=None
        ).first_or_404(
            description=f"Media with ID {mid} not found for product {pid}."
        )
        
        # Unset all other thumbnails for this product
        ProductMedia.query.filter_by(
            product_id=pid,
            deleted_at=None
        ).update({'is_thumbnail': False})
        
        # Set this media as thumbnail
        media.is_thumbnail = True
        db.session.commit()
        
        return media

    @staticmethod
    def set_main_image(pid, mid):
        """Set a media item as main image for a product"""
        merchant_id = MerchantProductMediaController._get_merchant_id_from_jwt()
        
        # Verify the product belongs to the merchant
        product = Product.query.filter_by(
            product_id=pid,
            merchant_id=merchant_id,
            deleted_at=None
        ).first_or_404(
            description=f"Product with ID {pid} not found or you do not have permission to access it."
        )
        
        # Get the media item
        media = ProductMedia.query.filter_by(
            media_id=mid,
            product_id=pid,
            deleted_at=None
        ).first_or_404(
            description=f"Media with ID {mid} not found for product {pid}."
        )
        
        # Unset all other main images for this product
        ProductMedia.query.filter_by(
            product_id=pid,
            deleted_at=None
        ).update({'is_main_image': False})
        
        # Set this media as main image
        media.is_main_image = True
        db.session.commit()
        
        return media

    @staticmethod
    def update_sort_order(mid, new_sort_order):
        """Update the sort order of a media item"""
        merchant_id = MerchantProductMediaController._get_merchant_id_from_jwt()
        
        # Get the media item
        media = ProductMedia.query.join(ProductMedia.product).filter(
            ProductMedia.media_id == mid,
            ProductMedia.deleted_at == None,
            Product.merchant_id == merchant_id
        ).first_or_404(
            description=f"Product media with ID {mid} not found or you do not have permission to access it."
        )
        
        # Update sort order
        media.sort_order = new_sort_order
        db.session.commit()
        
        return media