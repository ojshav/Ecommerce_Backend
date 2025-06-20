from marshmallow import Schema, fields, validate, validates_schema, validates, ValidationError
from models.enums import ProductPriceConditionType
from decimal import Decimal, InvalidOperation

class GSTRuleBaseSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=3, max=100))
    category_id = fields.Integer(required=True) 
    
    price_condition_type = fields.Enum(ProductPriceConditionType, required=True, by_value=True)
    price_condition_value = fields.Decimal(places=2, allow_none=True) # Allow none if type is ANY

    gst_rate_percentage = fields.Decimal(required=True, places=2, validate=validate.Range(min=0, max=100))
    is_active = fields.Boolean(load_default=True)
    start_date = fields.Date(allow_none=True) 
    end_date = fields.Date(allow_none=True)   

    @validates('price_condition_value')
    def validate_price_condition_value(self, value, **kwargs):
        # Access other field's value through self.context if needed, but here direct access to `data` via `self.get_value` is more appropriate for current field
        # For this validation, we need to know the price_condition_type
        pass # Handled in validates_schema

    @validates_schema
    def validate_schema_level(self, data, **kwargs):
        errors = {}
        price_type = data.get('price_condition_type')
        price_value = data.get('price_condition_value')

        if price_type != ProductPriceConditionType.ANY and price_value is None:
            errors['price_condition_value'] = ["Price condition value is required if type is not 'ANY'."]
        
        if price_type == ProductPriceConditionType.ANY and price_value is not None:
            # Optionally, you could auto-nullify it or raise an error
            # For now, let's suggest it should be null or raise an error if superadmin sends it.
             errors['price_condition_value'] = ["Price condition value should be null if type is 'ANY'."]


        start_date = data.get('start_date')
        end_date = data.get('end_date')

        if start_date and end_date and end_date < start_date:
            errors['end_date'] = ["End date cannot be before start date."]
        
        if errors:
            raise ValidationError(errors)


class CreateGSTRuleSchema(GSTRuleBaseSchema):
   
    pass

class UpdateGSTRuleSchema(GSTRuleBaseSchema):
   
    name = fields.String(validate=validate.Length(min=3, max=100))
    category_id = fields.Integer() # Category usually isn't changed for an existing rule, but allow if needed.
    price_condition_type = fields.Enum(ProductPriceConditionType, by_value=True)
    gst_rate_percentage = fields.Decimal(places=2, validate=validate.Range(min=0, max=100))
    is_active = fields.Boolean()

   
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for field_name, field_obj in self.fields.items():
            field_obj.required = False