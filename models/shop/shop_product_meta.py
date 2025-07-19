
# models/shop/shop_product_meta.py
from datetime import datetime
from common.database import db, BaseModel

class ShopProductMeta(BaseModel):
    __tablename__ = 'shop_product_meta'
    product_id    = db.Column(db.Integer, db.ForeignKey('shop_products.product_id'), primary_key=True)
    short_desc    = db.Column(db.String(255))
    full_desc     = db.Column(db.Text)
    meta_title    = db.Column(db.String(100))
    meta_desc     = db.Column(db.String(255))
    meta_keywords = db.Column(db.String(255))
    
    product       = db.relationship('ShopProduct', backref=db.backref('meta', uselist=False))
    
    def serialize(self):
        return {
            "product_id": self.product_id,
            "short_desc": self.short_desc,
            "full_desc": self.full_desc,
            "meta_title": self.meta_title,
            "meta_desc": self.meta_desc,
            "meta_keywords": self.meta_keywords
        }
