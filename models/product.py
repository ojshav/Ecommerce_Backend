# models/product.py
from datetime import datetime,timezone
from common.database import db, BaseModel
from auth.models.models import MerchantProfile
from models.category import Category
from models.brand import Brand
from decimal import Decimal, ROUND_HALF_UP
from models.gst_rule import GSTRule 


class Product(BaseModel):
    __tablename__ = 'products'

    product_id    = db.Column(db.Integer, primary_key=True)
    merchant_id   = db.Column(db.Integer, db.ForeignKey('merchant_profiles.id'), nullable=False)
    category_id   = db.Column(db.Integer, db.ForeignKey('categories.category_id'), nullable=False)
    brand_id      = db.Column(db.Integer, db.ForeignKey('brands.brand_id'), nullable=False)
    parent_product_id = db.Column(db.Integer, db.ForeignKey('products.product_id'), nullable=True)
    sku           = db.Column(db.String(50), unique=True, nullable=False)
    product_name  = db.Column(db.String(255), nullable=False)
    product_description = db.Column(db.Text, nullable=False)
    
    cost_price    = db.Column(db.Numeric(10,2), nullable=False)
    selling_price = db.Column(db.Numeric(10,2), nullable=False) # This is BASE PRICE (PRE-GST)
    
    discount_pct  = db.Column(db.Numeric(5,2), default=0.00)
    special_price = db.Column(db.Numeric(10,2), nullable=True) # This should also be PRE-GST if active
    special_start = db.Column(db.Date)
    special_end   = db.Column(db.Date)
    active_flag   = db.Column(db.Boolean, default=True, nullable=False)
    
    approval_status = db.Column(db.String(20), default='pending', nullable=False)
    approved_at     = db.Column(db.DateTime, nullable=True)
    approved_by     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    rejection_reason = db.Column(db.String(255), nullable=True)
    
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at    = db.Column(db.DateTime)

    gst_rate_percentage_applied = db.Column(db.Numeric(5,2), nullable=True)
    price_inclusive_gst = db.Column(db.Numeric(10,2), nullable=True)


    merchant      = db.relationship('MerchantProfile', backref='products')
    category      = db.relationship('Category', backref='products')
    brand         = db.relationship('Brand', backref='products')
    product_attributes = db.relationship('ProductAttribute', backref='product', cascade='all, delete-orphan')
    cart_items    = db.relationship('CartItem', back_populates='product', cascade='all, delete-orphan')
    wishlist_items = db.relationship('WishlistItem', back_populates='product', cascade='all, delete-orphan')
    approved_by_admin = db.relationship('User', backref='approved_products', foreign_keys=[approved_by])
    
    parent = db.relationship('Product', remote_side=[product_id], backref='variants')

    def update_gst_and_final_price(self):
        from flask import current_app 

        effective_base_price = self.selling_price 
        today = datetime.now(timezone.utc).date()
        if self.special_price is not None and \
           (self.special_start is None or self.special_start <= today) and \
           (self.special_end is None or self.special_end >= today):
            effective_base_price = self.special_price

        if not effective_base_price:
            current_app.logger.warning(f"Product {self.product_id} has no effective base price. GST not calculated.")
            self.gst_rate_percentage_applied = None
            self.price_inclusive_gst = self.selling_price
            return

        applicable_rule = GSTRule.find_applicable_rule(
            db_session=db.session,
            product_category_id=self.category_id, 
            base_price=effective_base_price
           
        )

        if applicable_rule:
            gst_rate = Decimal(applicable_rule.gst_rate_percentage)
            base_for_final_price_calc = Decimal(self.selling_price) # Final inclusive price is always based on standard selling_price
            
            gst_amount = (base_for_final_price_calc * gst_rate) / Decimal('100.00')
            gst_amount_rounded = gst_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            self.gst_rate_percentage_applied = gst_rate
            self.price_inclusive_gst = base_for_final_price_calc + gst_amount_rounded
            
            current_app.logger.info(f"Applied GST rule '{applicable_rule.name}' (Rate: {gst_rate}%) to product {self.product_id}. Standard Price inclusive GST: {self.price_inclusive_gst}")
        else:
            self.gst_rate_percentage_applied = None 
            self.price_inclusive_gst = Decimal(self.selling_price) 
            current_app.logger.warning(f"No applicable GST rule found for product {self.product_id} (Category: {self.category_id}, Base Price: {effective_base_price}). GST not applied.")

    def serialize(self):
        # (Serialization logic remains mostly the same as previously provided,
        # ensuring it uses self.selling_price for base, and self.price_inclusive_gst for final display.
        # The key is that update_gst_and_final_price now correctly sets these values.)
        active_price_base = self.selling_price # Base price before GST
        is_on_special = False
        today = datetime.now(timezone.utc).date()

        if self.special_price is not None and \
           (self.special_start is None or self.special_start <= today) and \
           (self.special_end is None or self.special_end >= today):
            active_price_base = self.special_price
            is_on_special = True
        
        active_price_inclusive_gst = active_price_base # Default if no GST
        if self.gst_rate_percentage_applied is not None:
            gst_rate = Decimal(self.gst_rate_percentage_applied)
            gst_on_active_base = (Decimal(active_price_base) * gst_rate) / Decimal('100.00')
            gst_on_active_base_rounded = gst_on_active_base.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            active_price_inclusive_gst = Decimal(active_price_base) + gst_on_active_base_rounded
        
        standard_price_inclusive_gst = self.price_inclusive_gst # This is already calculated from selling_price (base)

        serialized_data = {
            "product_id": self.product_id,
            "merchant_id": self.merchant_id,
            "category_id": self.category_id,
            "brand_id": self.brand_id,
            "parent_product_id": self.parent_product_id,
            "sku": self.sku,
            "product_name": self.product_name,
            "product_description": self.product_description,
            "cost_price": float(self.cost_price) if self.cost_price is not None else None,
            "selling_price_base": float(self.selling_price) if self.selling_price is not None else None, # Base (pre-GST)
            "discount_pct": float(self.discount_pct) if self.discount_pct is not None else 0.0,
            "special_price_base": float(self.special_price) if self.special_price is not None else None, # Base (pre-GST)
            "special_start": self.special_start.isoformat() if self.special_start else None,
            "special_end": self.special_end.isoformat() if self.special_end else None,
            "active_flag": bool(self.active_flag),
            "approval_status": self.approval_status,
            "gst_rate_percentage_applied": str(self.gst_rate_percentage_applied) if self.gst_rate_percentage_applied is not None else None,
            "price_inclusive_gst_standard": str(standard_price_inclusive_gst) if standard_price_inclusive_gst is not None else None,
            "current_display_price_inclusive_gst": str(active_price_inclusive_gst) if active_price_inclusive_gst is not None else None,
            "is_on_special_offer": is_on_special,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "price": float(active_price_inclusive_gst) if active_price_inclusive_gst is not None else float(self.selling_price),
            "originalPrice": float(standard_price_inclusive_gst) if standard_price_inclusive_gst is not None and is_on_special else None,
             "attributes":      [attr.serialize() for attr in self.product_attributes] if self.product_attributes else [],
            "variants":        [variant.serialize() for variant in self.variants] if self.variants else [],
            "stock":           self.stock.serialize() if hasattr(self, 'stock') and self.stock else None

        }
        return serialized_data