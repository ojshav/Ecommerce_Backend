
# models/shop/shop_product_attribute.py
from datetime import datetime
from common.database import db, BaseModel
from models.attribute import Attribute
from models.attribute_value import AttributeValue

class ShopProductAttribute(BaseModel):
    __tablename__ = 'shop_product_attributes'
    
    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    product_id    = db.Column(db.Integer, db.ForeignKey('shop_products.product_id'), nullable=False)
    attribute_id  = db.Column(db.Integer, db.ForeignKey('attributes.attribute_id'), nullable=False)
    
    value_code    = db.Column(db.String(50), nullable=True)
    value_text    = db.Column(db.String(255), nullable=True)
    value_number  = db.Column(db.Float,   nullable=True)

    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('product_id', 'attribute_id', 'value_code', name='uq_shop_product_attribute_code'),
        db.ForeignKeyConstraint(
            ['attribute_id', 'value_code'],
            ['attribute_values.attribute_id', 'attribute_values.value_code'],
            name='fk_shop_attrvalue',
            ondelete='CASCADE'
        ),
    )
    
    attribute = db.relationship('Attribute', foreign_keys=[attribute_id])
    attribute_value = db.relationship('AttributeValue',
        primaryjoin="and_(ShopProductAttribute.attribute_id==AttributeValue.attribute_id, "
                    "ShopProductAttribute.value_code==AttributeValue.value_code)",
        foreign_keys=[attribute_id, value_code],
        overlaps="attribute"
    )
    
    def serialize(self):
        val = None
        if self.attribute.input_type == 'select' or self.attribute.input_type == 'multiselect':
            val = self.value_code
        elif self.attribute.input_type == 'number':
            val = self.value_number
        else:
            val = self.value_text
        
        return {
            "id": self.id,
            "product_id": self.product_id,
            "attribute_id": self.attribute_id,
            "value": val,
            "attribute": self.attribute.serialize() if self.attribute else None,
            "attribute_value": self.attribute_value.serialize() if self.attribute_value else None,
        }
