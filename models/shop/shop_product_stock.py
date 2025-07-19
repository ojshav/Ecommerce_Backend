
# models/shop/shop_product_stock.py
from common.database import db, BaseModel

class ShopProductStock(BaseModel):
    __tablename__ = 'shop_product_stock'

    product_id = db.Column(db.Integer, db.ForeignKey('shop_products.product_id'), primary_key=True)
    stock_qty = db.Column(db.Integer, default=0)
    low_stock_threshold = db.Column(db.Integer, default=0)

    product = db.relationship('ShopProduct', backref=db.backref('stock', uselist=False))

    def serialize(self):
        return {
            'product_id': self.product_id,
            'stock_qty': self.stock_qty,
            'low_stock_threshold': self.low_stock_threshold
        }
