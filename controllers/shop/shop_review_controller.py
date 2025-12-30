import logging
from flask import current_app
from common.database import db
from werkzeug.exceptions import BadRequest
from services.s3_service import get_s3_service

from models.enums import OrderStatusEnum
from models.shop.shop_order import ShopOrder, ShopOrderItem
from models.shop.shop_product import ShopProduct
from models.shop.shop_review import ShopReview, ShopReviewImage
from sqlalchemy import func

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


def _estimate_base64_bytes(b64_or_data_url: str) -> int:
    """
    Estimate decoded bytes from a base64 string or data URL.
    data URL format: data:<mime>;base64,<payload>
    """
    try:
        if not b64_or_data_url:
            return 0
        if b64_or_data_url.startswith('data:'):
            parts = b64_or_data_url.split(',', 1)
            if len(parts) == 2:
                b64_str = parts[1]
            else:
                b64_str = ''
        else:
            b64_str = b64_or_data_url
        # Remove whitespace/newlines just in case
        b64_str = ''.join(b64_str.split())
        # Adjust for padding
        padding = b64_str.endswith('==') and 2 or (b64_str.endswith('=') and 1 or 0)
        # Estimated decoded length
        return max(0, (len(b64_str) * 3) // 4 - padding)
    except Exception:
        # On parsing error, return a large value to force validation error later during upload
        return MAX_IMAGE_BYTES + 1

logger = logging.getLogger(__name__)


class ShopReviewController:
    @staticmethod
    def create_review(user_id: int, review_data: dict):
        try:
            required = ['shop_order_id', 'shop_product_id', 'rating', 'title', 'body']
            missing = [f for f in required if f not in review_data]
            if missing:
                raise BadRequest(f"Missing required fields: {', '.join(missing)}")

            rating = review_data.get('rating')
            if not isinstance(rating, int) or rating < 1 or rating > 5:
                raise BadRequest('Rating must be an integer between 1 and 5')

            # Validate order belongs to user
            order: ShopOrder | None = ShopOrder.query.filter_by(order_id=review_data['shop_order_id'], user_id=user_id).first()
            if not order:
                raise BadRequest('Shop order not found or does not belong to user')
            # Delivery gating: allow if order delivered OR the specific item is delivered

            # Validate product exists and is in the order
            product: ShopProduct | None = ShopProduct.query.filter_by(product_id=review_data['shop_product_id']).first()
            if not product:
                raise BadRequest('Shop product not found')

            order_item = ShopOrderItem.query.filter_by(order_id=order.order_id, product_id=product.product_id).first()
            if not order_item:
                raise BadRequest('Product not found in this order')

            if order.order_status != OrderStatusEnum.DELIVERED:
                raise BadRequest('You can only review after delivery')

            # Prevent duplicate review per order/product
            dup = ShopReview.query.filter_by(shop_order_id=order.order_id, shop_product_id=product.product_id, user_id=user_id).first()
            if dup:
                raise BadRequest('You have already reviewed this product for this order')

            review = ShopReview(
                user_id=user_id,
                shop_product_id=product.product_id,
                shop_order_id=order.order_id,
                rating=rating,
                title=review_data.get('title', ''),
                body=review_data.get('body', ''),
            )
            review.save()

            # Images
            images = review_data.get('images')
            if images:
                if not isinstance(images, list):
                    raise BadRequest('Images must be a list')
                if len(images) > 5:
                    raise BadRequest('Maximum 5 images allowed per review')
                s3_service = get_s3_service()
                for idx, img_data in enumerate(images):
                    # Server-side size guard (<= 5 MB per image)
                    est_bytes = _estimate_base64_bytes(img_data if isinstance(img_data, str) else '')
                    if est_bytes > MAX_IMAGE_BYTES:
                        raise BadRequest('Each image must be smaller than 5 MB')
                    try:
                        # Upload to S3
                        upload = s3_service.upload_review_image(img_data, review.review_id)
                        if upload and upload.get('url'):
                            ri = ShopReviewImage(
                                review_id=review.review_id,
                                image_url=upload['url'],
                                public_id=upload['s3_key'],  # Store S3 key in public_id
                                sort_order=idx,
                            )
                            db.session.add(ri)
                    except Exception as e:
                        current_app.logger.error(f"Failed to upload shop review image: {e}")
                        continue

            db.session.commit()
            data = review.serialize(include_images=True)
            return data
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating shop review: {e}")
            raise

    @staticmethod
    def get_product_reviews(shop_product_id: int, page: int = 1, per_page: int = 10):
        try:
            pagination = ShopReview.query.filter_by(shop_product_id=shop_product_id).order_by(ShopReview.created_at.desc()).paginate(page=page, per_page=per_page)
            total = ShopReview.query.filter_by(shop_product_id=shop_product_id).count()

            # Compute average rating across all reviews for this product (efficient SQL AVG)
            avg_row = db.session.query(func.avg(ShopReview.rating)).filter(ShopReview.shop_product_id == shop_product_id).first()
            avg_rating = float(avg_row[0]) if avg_row and avg_row[0] is not None else 0.0

            reviews = []
            for r in pagination.items:
                d = r.serialize(include_images=True)
                reviews.append(d)

            return {
                'reviews': reviews,
                'total': total,
                'pages': pagination.pages,
                'current_page': pagination.page,
                'average_rating': round(avg_rating, 2),
                'review_count': total,
            }
        except Exception as e:
            logger.error(f"Error getting shop product reviews: {e}")
            raise

    @staticmethod
    def get_user_reviews(user_id: int, page: int = 1, per_page: int = 10):
        try:
            pagination = ShopReview.query.filter_by(user_id=user_id).order_by(ShopReview.created_at.desc()).paginate(page=page, per_page=per_page)
            total = ShopReview.query.filter_by(user_id=user_id).count()

            return {
                'reviews': [r.serialize(include_images=True) for r in pagination.items],
                'total': total,
                'pages': pagination.pages,
                'current_page': pagination.page,
            }
        except Exception as e:
            logger.error(f"Error getting user shop reviews: {e}")
            raise

    @staticmethod
    def delete_review(review_id: int, user_id: int):
        try:
            review = ShopReview.query.filter_by(review_id=review_id, user_id=user_id).first()
            if not review:
                raise BadRequest('Review not found or does not belong to user')

            s3_service = get_s3_service()
            for image in review.images:
                if getattr(image, 'public_id', None):
                    try:
                        s3_service.delete_review_image(image.public_id)
                        current_app.logger.info(f"Successfully deleted shop review image {image.public_id} from S3.")
                    except Exception as e:
                        current_app.logger.error(f"Failed to delete shop review image {image.public_id} from S3: {e}")
                elif getattr(image, 'image_url', None):
                    # Fallback: try to delete using image_url
                    try:
                        s3_service.delete_review_image(image.image_url)
                        current_app.logger.info(f"Successfully deleted shop review image from S3 using URL.")
                    except Exception as e:
                        current_app.logger.error(f"Failed to delete shop review image from S3 using URL: {e}")

            db.session.delete(review)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting shop review: {e}")
            raise
