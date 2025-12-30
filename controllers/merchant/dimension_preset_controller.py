# controllers/merchant/dimension_preset_controller.py
from flask import abort
from flask_jwt_extended import get_jwt_identity
from common.database import db
from models.merchant_dimension_preset import MerchantDimensionPreset
from auth.models.models import MerchantProfile
from decimal import Decimal

class MerchantDimensionPresetController:
    @staticmethod
    def _get_merchant_id():
        """Helper to get current authenticated merchant's ID."""
        user_id = get_jwt_identity()
        merchant = MerchantProfile.get_by_user_id(user_id)
        if not merchant:
            abort(404, "Merchant profile not found")
        return merchant.id

    @staticmethod
    def list_all():
        """Get all dimension presets for the current merchant."""
        merchant_id = MerchantDimensionPresetController._get_merchant_id()
        return MerchantDimensionPreset.query.filter_by(
            merchant_id=merchant_id,
            is_deleted=False
        ).order_by(MerchantDimensionPreset.created_at.desc()).all()

    @staticmethod
    def get(preset_id):
        """Get a specific dimension preset by ID."""
        merchant_id = MerchantDimensionPresetController._get_merchant_id()
        preset = MerchantDimensionPreset.query.filter_by(
            preset_id=preset_id,
            merchant_id=merchant_id,
            is_deleted=False
        ).first_or_404()
        return preset

    @staticmethod
    def create(data):
        """Create a new dimension preset."""
        merchant_id = MerchantDimensionPresetController._get_merchant_id()
        
        # Validate required fields
        required_fields = ['name', 'length_cm', 'width_cm', 'height_cm', 'weight_kg']
        for field in required_fields:
            if field not in data or data[field] is None:
                abort(400, f"Field '{field}' is required")
        
        # Create new preset
        preset = MerchantDimensionPreset(
            merchant_id=merchant_id,
            name=data['name'],
            length_cm=Decimal(str(data['length_cm'])),
            width_cm=Decimal(str(data['width_cm'])),
            height_cm=Decimal(str(data['height_cm'])),
            weight_kg=Decimal(str(data['weight_kg'])),
            shipping_class=data.get('shipping_class'),
            description=data.get('description')
        )
        
        db.session.add(preset)
        db.session.commit()
        return preset

    @staticmethod
    def update(preset_id, data):
        """Update an existing dimension preset."""
        merchant_id = MerchantDimensionPresetController._get_merchant_id()
        preset = MerchantDimensionPreset.query.filter_by(
            preset_id=preset_id,
            merchant_id=merchant_id,
            is_deleted=False
        ).first_or_404()
        
        # Update fields if provided
        if 'name' in data:
            preset.name = data['name']
        if 'length_cm' in data:
            preset.length_cm = Decimal(str(data['length_cm']))
        if 'width_cm' in data:
            preset.width_cm = Decimal(str(data['width_cm']))
        if 'height_cm' in data:
            preset.height_cm = Decimal(str(data['height_cm']))
        if 'weight_kg' in data:
            preset.weight_kg = Decimal(str(data['weight_kg']))
        if 'shipping_class' in data:
            preset.shipping_class = data['shipping_class']
        if 'description' in data:
            preset.description = data['description']
        
        db.session.commit()
        return preset

    @staticmethod
    def delete(preset_id):
        """Soft delete a dimension preset."""
        merchant_id = MerchantDimensionPresetController._get_merchant_id()
        preset = MerchantDimensionPreset.query.filter_by(
            preset_id=preset_id,
            merchant_id=merchant_id,
            is_deleted=False
        ).first_or_404()
        
        preset.is_deleted = True
        db.session.commit()
        return preset

