# controllers/shop/shop_variant_media_controller.py
from flask import request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from models.shop.shop_product import ShopProduct
from models.shop.shop_product_variant import ShopProductVariant
from models.shop.shop_product_media import ShopProductMedia
from models.enums import MediaType
from common.database import db
from common.response import success_response, error_response
import json
from datetime import datetime, timezone
import cloudinary
import cloudinary.uploader
from services.s3_service import get_s3_service
from werkzeug.utils import secure_filename
import os

class ShopVariantMediaController:
    
    @staticmethod
    @jwt_required()
    def upload_variant_media(variant_id):
        """Upload media files for a specific variant"""
        try:
            # Find variant
            variant_relation = ShopProductVariant.query.get(variant_id)
            if not variant_relation:
                return error_response("Variant not found", 404)
            
            variant_product = variant_relation.variant_product
            if not variant_product:
                return error_response("Variant product not found", 404)
            
            # Check if files are present
            if 'files' not in request.files:
                return error_response("No files provided", 400)
            
            files = request.files.getlist('files')
            if not files or all(file.filename == '' for file in files):
                return error_response("No valid files provided", 400)
            
            # Get additional form data
            is_primary = request.form.get('is_primary', 'false').lower() == 'true'
            
            # Check current media count (limit per variant: 4 images + 1 video)
            current_images = ShopProductMedia.query.filter_by(
                product_id=variant_product.product_id,
                type=MediaType.IMAGE,
                deleted_at=None
            ).count()
            
            current_videos = ShopProductMedia.query.filter_by(
                product_id=variant_product.product_id,
                type=MediaType.VIDEO,
                deleted_at=None
            ).count()
            
            # Count new media files by type (detect from file content)
            new_images = 0
            new_videos = 0
            
            for file in files:
                if file.filename == '':
                    continue
                    
                # Detect media type from file
                if file.content_type and file.content_type.startswith('image/'):
                    new_images += 1
                elif file.content_type and file.content_type.startswith('video/'):
                    new_videos += 1
            
            # Validate media limits for variants
            if current_images + new_images > 4:
                return error_response("Maximum 4 images allowed per variant", 400)
                
            if current_videos + new_videos > 1:
                return error_response("Maximum 1 video allowed per variant", 400)
            
            uploaded_media = []
            
            # Start transaction
            db.session.begin()
            
            try:
                # If this is set as primary, unset other primary media for this variant
                if is_primary:
                    ShopProductMedia.query.filter_by(
                        product_id=variant_product.product_id,
                        is_primary=True,
                        deleted_at=None
                    ).update({'is_primary': False})
                
                for i, file in enumerate(files):
                    if file.filename == '':
                        continue
                    
                    # Secure filename
                    filename = secure_filename(file.filename)
                    
                    # Determine media type from file content
                    file_media_type = MediaType.IMAGE
                    is_video = False
                    if file.content_type and file.content_type.startswith('video/'):
                        file_media_type = MediaType.VIDEO
                        is_video = True
                    
                    try:
                        upload_result = None
                        
                        if is_video:
                            # Videos still go to Cloudinary
                            folder_path = f"shop_{variant_product.shop_id}/products/variants/{variant_product.product_id}"
                            upload_result = cloudinary.uploader.upload(
                                file,
                                folder=folder_path,
                                resource_type="video",
                                quality="auto",
                                fetch_format="auto"
                            )
                        else:
                            # Images go to S3
                            s3_service = get_s3_service()
                            upload_result = s3_service.upload_variant_image(
                                file,
                                variant_product.shop_id,
                                variant_product.product_id
                            )
                        
                        if not upload_result:
                            raise Exception("Upload failed - no result returned")
                        
                        # Determine sort order
                        max_sort_order = db.session.query(
                            db.func.max(ShopProductMedia.sort_order)
                        ).filter_by(
                            product_id=variant_product.product_id,
                            deleted_at=None
                        ).scalar() or 0
                        
                        # Create media record
                        if is_video:
                            # Cloudinary response format
                            media = ShopProductMedia(
                                product_id=variant_product.product_id,
                                type=file_media_type,
                                url=upload_result['secure_url'],
                                public_id=upload_result['public_id'],
                                sort_order=max_sort_order + i + 1,
                                is_primary=is_primary and i == 0,
                                file_size=upload_result.get('bytes'),
                                file_name=filename
                            )
                        else:
                            # S3 response format
                            media = ShopProductMedia(
                                product_id=variant_product.product_id,
                                type=file_media_type,
                                url=upload_result['url'],
                                public_id=upload_result['s3_key'],  # Store S3 key in public_id
                                sort_order=max_sort_order + i + 1,
                                is_primary=is_primary and i == 0,
                                file_size=upload_result.get('bytes', 0),
                                file_name=filename
                            )
                        
                        db.session.add(media)
                        db.session.flush()  # Get the media_id
                        
                        uploaded_media.append(media.serialize())
                        
                    except Exception as upload_error:
                        # Log the error but continue with other files
                        current_app.logger.error(f"Failed to upload file {filename}: {str(upload_error)}")
                        continue
                
                if not uploaded_media:
                    db.session.rollback()
                    return error_response("No files were successfully uploaded", 400)
                
                db.session.commit()
                
                return success_response({
                    "uploaded_media": uploaded_media,
                    "uploaded_count": len(uploaded_media),
                    "message": f"Successfully uploaded {len(uploaded_media)} media files"
                })
                
            except Exception as e:
                db.session.rollback()
                raise e
                
        except Exception as e:
            return error_response(f"Failed to upload media: {str(e)}", 500)
    
    @staticmethod
    @jwt_required()
    def get_variant_media(variant_id):
        """Get all media for a specific variant"""
        try:
            variant_relation = ShopProductVariant.query.get(variant_id)
            if not variant_relation:
                return error_response("Variant not found", 404)
            
            variant_product = variant_relation.variant_product
            if not variant_product:
                return error_response("Variant product not found", 404)
            
            # Get variant-specific media
            variant_media = ShopProductMedia.query.filter_by(
                product_id=variant_product.product_id,
                deleted_at=None
            ).order_by(ShopProductMedia.sort_order, ShopProductMedia.media_id).all()
            
            # Get parent media as fallback
            parent_media = []
            if not variant_media:
                parent_product = variant_relation.parent_product
                if parent_product:
                    parent_media = ShopProductMedia.query.filter_by(
                        product_id=parent_product.product_id,
                        deleted_at=None
                    ).order_by(ShopProductMedia.sort_order, ShopProductMedia.media_id).all()
            
            return success_response({
                "variant_media": [media.serialize() for media in variant_media],
                "parent_media": [media.serialize() for media in parent_media],
                "has_variant_media": len(variant_media) > 0,
                "total_media": len(variant_media) or len(parent_media)
            })
            
        except Exception as e:
            return error_response(f"Failed to get variant media: {str(e)}", 500)
    
    @staticmethod
    @jwt_required()
    def update_media_order(variant_id):
        """Update the sort order of media files for a variant"""
        try:
            data = request.get_json()
            media_orders = data.get('media_orders', [])
            
            if not media_orders:
                return error_response("No media order data provided", 400)
            
            variant_relation = ShopProductVariant.query.get(variant_id)
            if not variant_relation:
                return error_response("Variant not found", 404)
            
            variant_product = variant_relation.variant_product
            
            # Start transaction
            db.session.begin()
            
            try:
                for item in media_orders:
                    media_id = item.get('media_id')
                    sort_order = item.get('sort_order')
                    
                    if media_id and sort_order is not None:
                        media = ShopProductMedia.query.filter_by(
                            media_id=media_id,
                            product_id=variant_product.product_id,
                            deleted_at=None
                        ).first()
                        
                        if media:
                            media.sort_order = sort_order
                            media.updated_at = datetime.now(timezone.utc)
                
                db.session.commit()
                
                return success_response({"message": "Media order updated successfully"})
                
            except Exception as e:
                db.session.rollback()
                raise e
                
        except Exception as e:
            return error_response(f"Failed to update media order: {str(e)}", 500)
    
    @staticmethod
    @jwt_required()
    def set_primary_media(variant_id, media_id):
        """Set a media file as primary for the variant"""
        try:
            variant_relation = ShopProductVariant.query.get(variant_id)
            if not variant_relation:
                return error_response("Variant not found", 404)
            
            variant_product = variant_relation.variant_product
            
            # Find the media
            media = ShopProductMedia.query.filter_by(
                media_id=media_id,
                product_id=variant_product.product_id,
                deleted_at=None
            ).first()
            
            if not media:
                return error_response("Media not found", 404)
            
            # Start transaction
            db.session.begin()
            
            try:
                # Unset other primary media for this variant
                ShopProductMedia.query.filter_by(
                    product_id=variant_product.product_id,
                    deleted_at=None
                ).update({'is_primary': False})
                
                # Set this media as primary
                media.is_primary = True
                media.updated_at = datetime.now(timezone.utc)
                
                db.session.commit()
                
                return success_response({
                    "media": media.serialize(),
                    "message": "Primary media updated successfully"
                })
                
            except Exception as e:
                db.session.rollback()
                raise e
                
        except Exception as e:
            return error_response(f"Failed to set primary media: {str(e)}", 500)
    
    @staticmethod
    @jwt_required()
    def delete_variant_media(variant_id, media_id):
        """Delete a media file from a variant"""
        try:
            variant_relation = ShopProductVariant.query.get(variant_id)
            if not variant_relation:
                return error_response("Variant not found", 404)
            
            variant_product = variant_relation.variant_product
            
            # Find the media
            media = ShopProductMedia.query.filter_by(
                media_id=media_id,
                product_id=variant_product.product_id,
                deleted_at=None
            ).first()
            
            if not media:
                return error_response("Media not found", 404)
            
            # Start transaction
            db.session.begin()
            
            try:
                # Delete from storage (S3 for images, Cloudinary for videos)
                if media.public_id:
                    try:
                        if media.type == MediaType.VIDEO:
                            # Delete video from Cloudinary
                            cloudinary.uploader.destroy(media.public_id)
                            current_app.logger.info(f"Deleted video {media.public_id} from Cloudinary")
                        else:
                            # Delete image from S3
                            s3_service = get_s3_service()
                            s3_service.delete_variant_image(media.public_id)
                            current_app.logger.info(f"Deleted image {media.public_id} from S3")
                    except Exception as delete_error:
                        current_app.logger.error(f"Failed to delete media from storage: {str(delete_error)}")
                        # Continue with database deletion even if storage delete fails
                
                # Soft delete from database
                media.deleted_at = datetime.now(timezone.utc)
                
                # If this was primary, set another media as primary
                if media.is_primary:
                    next_media = ShopProductMedia.query.filter_by(
                        product_id=variant_product.product_id,
                        deleted_at=None
                    ).filter(
                        ShopProductMedia.media_id != media_id
                    ).order_by(ShopProductMedia.sort_order).first()
                    
                    if next_media:
                        next_media.is_primary = True
                
                db.session.commit()
                
                return success_response({"message": "Media deleted successfully"})
                
            except Exception as e:
                db.session.rollback()
                raise e
                
        except Exception as e:
            return error_response(f"Failed to delete media: {str(e)}", 500)
    
    @staticmethod
    @jwt_required()
    def get_media_stats(variant_id):
        """Get media statistics for a variant"""
        try:
            variant_relation = ShopProductVariant.query.get(variant_id)
            if not variant_relation:
                return error_response("Variant not found", 404)
            
            variant_product = variant_relation.variant_product
            
            # Count media by type
            media_stats = db.session.query(
                ShopProductMedia.type,
                db.func.count(ShopProductMedia.media_id).label('count'),
                db.func.sum(ShopProductMedia.file_size).label('total_size')
            ).filter_by(
                product_id=variant_product.product_id,
                deleted_at=None
            ).group_by(ShopProductMedia.type).all()
            
            # Calculate totals
            total_count = sum(stat.count for stat in media_stats)
            total_size = sum(stat.total_size or 0 for stat in media_stats)
            
            # Max limits
            max_media_per_variant = 10
            max_size_mb = 50  # 50MB total per variant
            
            stats = {
                "total_count": total_count,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "max_media_count": max_media_per_variant,
                "remaining_slots": max_media_per_variant - total_count,
                "max_size_mb": max_size_mb,
                "remaining_size_mb": max_size_mb - round(total_size / (1024 * 1024), 2),
                "by_type": {}
            }
            
            for stat in media_stats:
                stats["by_type"][stat.type.value] = {
                    "count": stat.count,
                    "size_bytes": stat.total_size or 0,
                    "size_mb": round((stat.total_size or 0) / (1024 * 1024), 2)
                }
            
            return success_response(stats)
            
        except Exception as e:
            return error_response(f"Failed to get media stats: {str(e)}", 500)
    
    @staticmethod
    @jwt_required()
    def copy_parent_media(variant_id):
        """Copy parent product media to variant"""
        try:
            variant_relation = ShopProductVariant.query.get(variant_id)
            if not variant_relation:
                return error_response("Variant not found", 404)
            
            variant_product = variant_relation.variant_product
            parent_product = variant_relation.parent_product
            
            if not parent_product:
                return error_response("Parent product not found", 404)
            
            # Check if variant already has media
            existing_media = ShopProductMedia.query.filter_by(
                product_id=variant_product.product_id,
                deleted_at=None
            ).count()
            
            if existing_media > 0:
                return error_response("Variant already has media. Delete existing media first.", 400)
            
            # Get parent media
            parent_media = ShopProductMedia.query.filter_by(
                product_id=parent_product.product_id,
                deleted_at=None
            ).order_by(ShopProductMedia.sort_order).all()
            
            if not parent_media:
                return error_response("Parent product has no media to copy", 404)
            
            # Start transaction
            db.session.begin()
            
            try:
                copied_media = []
                
                for media in parent_media:
                    # Create copy for variant
                    variant_media = ShopProductMedia(
                        product_id=variant_product.product_id,
                        type=media.type,
                        url=media.url,  # Same URL, different product association
                        public_id=media.public_id,  # Same public_id for shared resources
                        sort_order=media.sort_order,
                        is_primary=media.is_primary,
                        file_size=media.file_size,
                        file_name=media.file_name
                    )
                    
                    db.session.add(variant_media)
                    db.session.flush()
                    
                    copied_media.append(variant_media.serialize())
                
                db.session.commit()
                
                return success_response({
                    "copied_media": copied_media,
                    "copied_count": len(copied_media),
                    "message": f"Successfully copied {len(copied_media)} media files from parent"
                })
                
            except Exception as e:
                db.session.rollback()
                raise e
                
        except Exception as e:
            return error_response(f"Failed to copy parent media: {str(e)}", 500)
