from flask import current_app
from common.database import db
from models.gst_rule import GSTRule
from models.category import Category # To validate category_id
from models.enums import ProductPriceConditionType # For validation
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import NotFound, BadRequest
from decimal import Decimal

class GSTManagementController:
    @staticmethod
    def list_all_rules():
        try:
            rules = GSTRule.query.order_by(GSTRule.name).all()
            return [rule.serialize() for rule in rules]
        except Exception as e:
            current_app.logger.error(f"Error listing GST rules: {e}")
            raise # Re-raise to be caught by global error handler or route

    @staticmethod
    def get_rule(rule_id):
        rule = GSTRule.query.get(rule_id)
        if not rule:
            raise NotFound(f"GSTRule with ID {rule_id} not found.")
        return rule.serialize()

    @staticmethod
    def create_rule(data, admin_id):
        # Validate category_id exists
        category = Category.query.get(data['category_id'])
        if not category:
            raise BadRequest(f"Category with ID {data['category_id']} not found.")

        # Check for existing rule name
        if GSTRule.query.filter_by(name=data['name']).first():
            raise BadRequest(f"A GST Rule with the name '{data['name']}' already exists.")

        try:
            new_rule = GSTRule(
                name=data['name'],
                category_id=data['category_id'],
                price_condition_type=data['price_condition_type'], # Already an enum object from schema
                price_condition_value=data.get('price_condition_value'), # Schema handles if it should be None
                gst_rate_percentage=Decimal(data['gst_rate_percentage']),
                is_active=data.get('is_active', True),
                start_date=data.get('start_date'),
                end_date=data.get('end_date'),
                created_by=admin_id,
                updated_by=admin_id 
            )
            db.session.add(new_rule)
            db.session.commit()
            # TODO: Trigger background task to update affected products
            return new_rule.serialize()
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"Integrity error creating GST rule: {e}")
            # A more specific error might be useful if possible (e.g. unique constraint on name if not caught above)
            raise BadRequest("Failed to create GST rule due to a data conflict. Please check rule name and other unique constraints.")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Unexpected error creating GST rule: {e}")
            raise

    @staticmethod
    def update_rule(rule_id, data, admin_id):
        rule = GSTRule.query.get(rule_id)
        if not rule:
            raise NotFound(f"GSTRule with ID {rule_id} not found.")

        if 'name' in data and data['name'] != rule.name:
            if GSTRule.query.filter(GSTRule.id != rule_id, GSTRule.name == data['name']).first():
                raise BadRequest(f"A GST Rule with the name '{data['name']}' already exists.")
            rule.name = data['name']
        
       
        
        if 'category_id' in data:
            category = Category.query.get(data['category_id'])
            if not category:
                raise BadRequest(f"Category with ID {data['category_id']} not found.")
            rule.category_id = data['category_id']

        if 'price_condition_type' in data:
            rule.price_condition_type = data['price_condition_type'] # Enum from schema

        # Handle price_condition_value based on type
        if 'price_condition_type' in data or 'price_condition_value' in data: # If either changes, re-evaluate
            new_price_type = data.get('price_condition_type', rule.price_condition_type)
            new_price_value = data.get('price_condition_value')

            if new_price_type == ProductPriceConditionType.ANY:
                rule.price_condition_value = None
            elif new_price_value is not None: # If type is not ANY, value is expected
                rule.price_condition_value = Decimal(new_price_value)
            # If new_price_type is not ANY and new_price_value is None, schema should have caught it.
            # Or, if only type changed to non-ANY, and value wasn't provided, it's an issue schema should handle or we add explicit check.
            # For simplicity here, assuming schema validation has ensured value presence if type is not ANY.
            if 'price_condition_value' in data : # Explicitly set if provided
                 rule.price_condition_value = Decimal(data['price_condition_value']) if data['price_condition_value'] is not None else None


        if 'gst_rate_percentage' in data:
            rule.gst_rate_percentage = Decimal(data['gst_rate_percentage'])
        
        if 'is_active' in data:
            rule.is_active = data['is_active']
        
        if 'start_date' in data: # Schema ensures it's a date object or None
            rule.start_date = data['start_date']
        
        if 'end_date' in data: # Schema ensures it's a date object or None
            rule.end_date = data['end_date']

        rule.updated_by = admin_id
        
        try:
            db.session.commit()
            # TODO: Trigger background task to update affected products
            return rule.serialize()
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"Integrity error updating GST rule {rule_id}: {e}")
            raise BadRequest("Failed to update GST rule due to a data conflict.")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Unexpected error updating GST rule {rule_id}: {e}")
            raise

    @staticmethod
    def delete_rule(rule_id):
        rule = GSTRule.query.get(rule_id)
        if not rule:
            raise NotFound(f"GSTRule with ID {rule_id} not found.")
        
        try:
            db.session.delete(rule)
            db.session.commit()
            # TODO: Trigger background task to update affected products (they would revert to next applicable rule or no GST)
            return True # Or some confirmation
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error deleting GST rule {rule_id}: {e}")
            # Check if it's a foreign key constraint violation (if GSTRules were directly linked elsewhere)
            if isinstance(e, IntegrityError):
                raise BadRequest(f"Cannot delete GST Rule {rule_id} as it might be in use or linked.")
            raise