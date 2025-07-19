
# models/shop/shop_product_tax.py
from datetime import datetime
from common.database import db, BaseModel

class ShopProductTax(BaseModel):
    __tablename__ = 'shop_product_taxes'
    product_id    = db.Column(db.Integer, db.ForeignKey('shop_products.product_id'), primary_key=True)
    tax_rate      = db.Column(db.Numeric(5,2), nullable=False)
    
    product       = db.relationship('ShopProduct', backref=db.backref('tax', uselist=False))
    
    def serialize(self):
        return {
            "product_id": self.product_id,
            "tax_rate": str(self.tax_rate)
        }
