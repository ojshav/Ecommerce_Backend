

# models/shop/shop_product.py
from datetime import datetime, timezone
from common.database import db, BaseModel
from models.category import Category
from models.brand import Brand
from auth.models.models import User  # Assuming superadmins are in the User table

from decimal import Decimal
import json

class ShopProduct(BaseModel):
    __tablename__ = 'shop_products'

    product_id    = db.Column(db.Integer, primary_key=True)
    category_id   = db.Column(db.Integer, db.ForeignKey('categories.category_id'), nullable=False)
    brand_id      = db.Column(db.Integer, db.ForeignKey('brands.brand_id'), nullable=True)
    parent_product_id = db.Column(db.Integer, db.ForeignKey('shop_products.product_id'), nullable=True)
    sku           = db.Column(db.String(50), unique=True, nullable=False)
    product_name  = db.Column(db.String(255), nullable=False)
    product_description = db.Column(db.Text, nullable=False)
    
    cost_price    = db.Column(db.Numeric(10,2), nullable=False) 
    selling_price = db.Column(db.Numeric(10,2), nullable=False) 
    
    discount_pct  = db.Column(db.Numeric(5,2), default=0.00)
    
    special_price = db.Column(db.Numeric(10,2), nullable=True) 
    special_start = db.Column(db.Date)
    special_end   = db.Column(db.Date)
    
    active_flag   = db.Column(db.Boolean, default=True, nullable=False)
    
    # Approval is handled by superadmin, so status is simpler.
    # Or we can keep the approval flow if superadmins also need to approve.
    # Assuming a simple "published" status for now.
    is_published   = db.Column(db.Boolean, default=False, nullable=False)
    
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at    = db.Column(db.DateTime)

    category      = db.relationship('Category', backref='shop_products')
    brand         = db.relationship('Brand', backref='shop_products')
    
    # Updated relationships for shop-specific models
    product_attributes = db.relationship('ShopProductAttribute', backref='product', cascade='all, delete-orphan')
    
    parent = db.relationship('ShopProduct', remote_side=[product_id], backref='variants')

    def get_current_listed_inclusive_price(self):
        """Returns the current GST-inclusive price (special or regular)."""
        today = datetime.now(timezone.utc).date()
        is_on_special = False
        current_price = self.selling_price

        if self.special_price is not None and \
           (self.special_start is None or self.special_start <= today) and \
           (self.special_end is None or self.special_end >= today):
            current_price = self.special_price
            is_on_special = True
        return current_price, is_on_special

    def serialize(self):
        current_listed_inclusive_price, is_on_special = self.get_current_listed_inclusive_price()
        display_price = current_listed_inclusive_price
        original_display_price = self.selling_price if is_on_special and self.selling_price != display_price else None

        return {
            "product_id": self.product_id,
            "category_id": self.category_id,
            "category_name": self.category.name if self.category else None,
            "brand_id": self.brand_id,
            "brand_name": self.brand.name if self.brand else None,
            "parent_product_id": self.parent_product_id,
            "sku": self.sku,
            "product_name": self.product_name,
            "product_description": self.product_description,
            "cost_price": float(self.cost_price) if self.cost_price is not None else None,
            "selling_price": float(self.selling_price) if self.selling_price is not None else None,
            "special_price": float(self.special_price) if self.special_price is not None else None,
            "special_start": self.special_start.isoformat() if self.special_start else None,
            "special_end": self.special_end.isoformat() if self.special_end else None,
            "is_on_special_offer": is_on_special,
            "is_published": self.is_published,
            "active_flag": bool(self.active_flag),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "price": float(display_price) if display_price is not None else 0.0,
            "originalPrice": float(original_display_price) if original_display_price is not None else None,
            "attributes": [attr.serialize() for attr in self.product_attributes] if self.product_attributes else [],
            "variants": [variant.serialize() for variant in self.variants] if self.variants else [],
            "stock": self.stock.serialize() if hasattr(self, 'stock') and self.stock else None
        }

