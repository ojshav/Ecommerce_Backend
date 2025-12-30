# models/merchant_dimension_preset.py
from datetime import datetime
from common.database import db, BaseModel
from auth.models.models import MerchantProfile

class MerchantDimensionPreset(BaseModel):
    __tablename__ = 'merchant_dimension_presets'
    
    preset_id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(db.Integer, db.ForeignKey('merchant_profiles.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    
    # Dimension fields (stored in base units: cm for dimensions, kg for weight)
    length_cm = db.Column(db.Numeric(7, 2), nullable=False)
    width_cm = db.Column(db.Numeric(7, 2), nullable=False)
    height_cm = db.Column(db.Numeric(7, 2), nullable=False)
    weight_kg = db.Column(db.Numeric(7, 3), nullable=False)
    shipping_class = db.Column(db.String(50), nullable=True)
    
    # Optional description
    description = db.Column(db.Text, nullable=True)
    
    # Soft delete flag
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relationships
    merchant = db.relationship('MerchantProfile', backref=db.backref('dimension_presets', lazy='dynamic'))
    
    def serialize(self):
        """Serialize the preset to a dictionary."""
        return {
            "preset_id": self.preset_id,
            "merchant_id": self.merchant_id,
            "name": self.name,
            "length_cm": float(self.length_cm) if self.length_cm else 0,
            "width_cm": float(self.width_cm) if self.width_cm else 0,
            "height_cm": float(self.height_cm) if self.height_cm else 0,
            "weight_kg": float(self.weight_kg) if self.weight_kg else 0,
            "shipping_class": self.shipping_class,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f"<MerchantDimensionPreset {self.preset_id}: {self.name}>"

