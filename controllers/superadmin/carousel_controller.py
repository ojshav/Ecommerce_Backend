from models.carousel import Carousel
from common.database import db
from services.s3_service import get_s3_service
from flask import current_app
from datetime import datetime

class CarouselController:
    @staticmethod
    def list_all():
        """
        Get all active carousel items.
        Returns:
            List[Carousel]: List of all active carousel items
        """
        return Carousel.query.filter_by(deleted_at=None).order_by(Carousel.display_order).all()

    @staticmethod
    def create(data, image_file=None):
        """
        Create a new carousel item. Handles S3 upload if image_file is provided.
        Args:
            data (dict): Carousel item data (type, target_id, display_order, is_active, shareable_link)
            image_file (FileStorage): Image file to upload (optional)
        Returns:
            Carousel: Created carousel item
        """
        image_url = data.get('image_url')
        if image_file:
            try:
                # Validate file object
                if not hasattr(image_file, 'filename') or not image_file.filename:
                    raise Exception("Invalid file object: missing filename")
                
                current_app.logger.info(f"Starting carousel image upload to S3: filename={image_file.filename}")
                
                # Reset file pointer to beginning if needed
                if hasattr(image_file, 'seek') and hasattr(image_file, 'tell'):
                    try:
                        current_pos = image_file.tell()
                        if current_pos != 0:
                            image_file.seek(0)
                            current_app.logger.info(f"Reset file pointer from position {current_pos} to 0")
                    except (IOError, OSError) as seek_error:
                        current_app.logger.warning(f"Could not seek file to beginning: {seek_error}. Continuing anyway.")
                
                # Get S3 service
                s3_service = get_s3_service()
                if not s3_service:
                    raise Exception("S3 service failed to initialize")
                current_app.logger.info("S3 service initialized successfully")
                
                # Upload to S3
                upload_result = s3_service.upload_carousel_image(image_file)
                if not upload_result or not upload_result.get('url'):
                    raise Exception("S3 upload returned no URL")
                image_url = upload_result.get('url')
                current_app.logger.info(f"Carousel image uploaded successfully to S3: {image_url}")
            except Exception as e:
                current_app.logger.error(f"Failed to upload carousel image to S3: {str(e)}", exc_info=True)
                raise Exception(f"Failed to upload carousel image: {str(e)}")
        carousel = Carousel(
            type=data['type'],
            image_url=image_url,
            target_id=data['target_id'],
            display_order=data.get('display_order', 0),
            is_active=data.get('is_active', True),
            shareable_link=data.get('shareable_link')
        )
        db.session.add(carousel)
        db.session.commit()
        return carousel

    @staticmethod
    def delete(carousel_id):
        """
        Soft delete a carousel item.
        Args:
            carousel_id (int): ID of the carousel item to delete
        Returns:
            Carousel: Deleted carousel item
        """
        carousel = Carousel.query.get_or_404(carousel_id)
        
        # Delete image from S3 if it exists
        if carousel.image_url:
            try:
                s3_service = get_s3_service()
                s3_service.delete_carousel_image(carousel.image_url)
            except Exception as e:
                current_app.logger.warning(f"Failed to delete carousel image from S3: {str(e)}")
        
        carousel.deleted_at = datetime.utcnow()
        db.session.commit()
        return carousel

    @staticmethod
    def update(carousel_id, data, image_file=None):
        """
        Update a carousel item by ID. Supports updating fields and image upload.
        Args:
            carousel_id (int): ID of the carousel item to update
            data (dict): Fields to update
            image_file (FileStorage): New image file (optional)
        Returns:
            Carousel: Updated carousel item
        """
        carousel = Carousel.query.get_or_404(carousel_id)
        if 'type' in data:
            carousel.type = data['type']
        if 'target_id' in data:
            carousel.target_id = data['target_id']
        if 'display_order' in data:
            carousel.display_order = data['display_order']
        if 'is_active' in data:
            carousel.is_active = data['is_active']
        if 'shareable_link' in data:
            carousel.shareable_link = data['shareable_link']
        if image_file:
            # Delete old image from S3 if it exists
            if carousel.image_url:
                try:
                    s3_service = get_s3_service()
                    s3_service.delete_carousel_image(carousel.image_url)
                except Exception as e:
                    current_app.logger.warning(f"Failed to delete old carousel image from S3: {str(e)}")
            
            # Upload new image to S3
            try:
                s3_service = get_s3_service()
                upload_result = s3_service.upload_carousel_image(image_file)
                carousel.image_url = upload_result.get('url')
            except Exception as e:
                current_app.logger.error(f"Failed to upload carousel image: {str(e)}")
                raise Exception(f"Failed to upload carousel image: {str(e)}")
        db.session.commit()
        return carousel

    @staticmethod
    def update_display_orders(order_list):
        """
        Update display_order for multiple carousel items.
        Args:
            order_list (list of dict): [{'id': 1, 'display_order': 0}, ...]
        Returns:
            int: Number of updated items
        """
        updated = 0
        for item in order_list:
            carousel = Carousel.query.get(item['id'])
            if carousel and carousel.deleted_at is None:
                carousel.display_order = item['display_order']
                updated += 1
        db.session.commit()
        return updated 