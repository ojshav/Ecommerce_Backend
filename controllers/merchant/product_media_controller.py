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
            if cloudinary_public_id: 
                 try:
                    resource_type_for_cloudinary = "image" if media_type_enum == MediaType.IMAGE else "video"
                    cloudinary.uploader.destroy(cloudinary_public_id, resource_type=resource_type_for_cloudinary)
                 except Exception as cloud_e:
                    current_app.logger.error(f"Failed to delete orphaned Cloudinary file {cloudinary_public_id} after DB error: {cloud_e}")
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
        
        
        if hasattr(pm, 'public_id') and pm.public_id:
            try:
                resource_type_for_cloudinary = "image" if pm.type == MediaType.IMAGE else "video"
                cloudinary.uploader.destroy(pm.public_id, resource_type=resource_type_for_cloudinary)
                current_app.logger.info(f"Successfully deleted {pm.public_id} from Cloudinary.")
            except Exception as e:
                current_app.logger.error(f"Failed to delete media {pm.public_id} from Cloudinary: {e}")

        pm.deleted_at = datetime.now(timezone.utc)
        db.session.commit()
        return pm