
# models/shop/shop_product_placement.py
from datetime import datetime, timezone
from common.database import db, BaseModel
from models.enums import PlacementTypeEnum

class ShopProductPlacement(BaseModel):
    __tablename__ = 'shop_product_placements'

    placement_id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('shop_products.product_id'), nullable=False)
    
    placement_type = db.Column(db.Enum(PlacementTypeEnum), nullable=False)
    
    is_active = db.Column(db.Boolean, default=True, nullable=False, server_default=db.true(), index=True)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    
    added_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=True) 

    product = db.relationship('ShopProduct', backref=db.backref('placements', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('product_id', 'placement_type', name='uq_shop_product_placement_type_unique'),
        db.Index('idx_shop_placement_display_query', 'placement_type', 'is_active', 'expires_at', 'sort_order'), 
    )

    def __repr__(self):
        return f"<ShopProductPlacement id={self.placement_id} p_id={self.product_id} type='{self.placement_type.value}' active={self.is_active}>"

    def serialize(self):
        product_info = None
        if self.product:
            try:
                product_info = self.product.serialize() 
            except Exception: 
                product_info = {"product_id": self.product.product_id, "name": getattr(self.product, 'product_name', None)}
        
        return {
            "placement_id": self.placement_id,
            "product_id": self.product_id,
            "placement_type": self.placement_type.value,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "product_details": product_info,
            "created_at": self.created_at.isoformat() if hasattr(self, 'created_at') and self.created_at else None,
            "updated_at": self.updated_at.isoformat() if hasattr(self, 'updated_at') and self.updated_at else None,
        }

    @classmethod
    def get_active_display_placements(cls, placement_type, limit=10):
        """Gets placements to be displayed on the frontend."""
        now_utc = datetime.now(timezone.utc)
        return cls.query.filter(
            cls.placement_type == placement_type,
            cls.is_active == True,
            (cls.expires_at == None) | (cls.expires_at > now_utc)
        ).order_by(cls.sort_order.asc(), cls.added_at.desc()).limit(limit).all()
