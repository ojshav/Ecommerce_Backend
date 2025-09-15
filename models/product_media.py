from datetime import datetime
from common.database import db, BaseModel
from auth.models.models import MerchantProfile
from models.category import Category
from models.brand import Brand
from models.enums import MediaType


class ProductMedia(BaseModel):
    __tablename__ = 'product_media'
    media_id      = db.Column(db.Integer, primary_key=True)
    product_id    = db.Column(db.Integer, db.ForeignKey('products.product_id'), nullable=False)
    type          = db.Column(db.Enum(MediaType), nullable=False)
    url           = db.Column(db.String(255), nullable=False)
    sort_order    = db.Column(db.Integer, default=0, nullable=False)
    public_id = db.Column(db.String(255), nullable=True)
    is_thumbnail  = db.Column(db.Boolean, default=False, nullable=False)
    is_main_image = db.Column(db.Boolean, default=False, nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at    = db.Column(db.DateTime)
    product       = db.relationship('Product', backref='media')
    
    def serialize(self):
        return {
            "media_id": self.media_id,
            "product_id": self.product_id,
            "type": self.type.value,
            "url": self.url,
            "sort_order": self.sort_order,
            "public_id": self.public_id,
            "is_thumbnail": self.is_thumbnail,
            "is_main_image": self.is_main_image,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None
        }
