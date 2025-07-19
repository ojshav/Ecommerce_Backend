
# models/shop/shop_product_promotion.py
from datetime import datetime
from common.database import db, BaseModel

class ShopProductPromotion(BaseModel):
    __tablename__ = 'shop_product_promotions'
    product_id     = db.Column(db.Integer, db.ForeignKey('shop_products.product_id'), primary_key=True)
    promotion_id   = db.Column(db.Integer, db.ForeignKey('promotions.promotion_id'), primary_key=True)
