from auth.models.models import User, MerchantProfile
from sqlalchemy.exc import SQLAlchemyError
from flask_jwt_extended import get_jwt_identity
from werkzeug.security import check_password_hash, generate_password_hash
from common.database import db
import logging

logger = logging.getLogger(__name__)

class MerchantSettingsController:
    @staticmethod
    def change_password(current_password, new_password):
        """
        Change the password for the currently logged-in user.
        """
        try:
            user_id = get_jwt_identity()  # Get user ID from JWT token
            user = User.query.get(user_id)

            if not user:
                return {"message": "User not found"}, 404

            if not check_password_hash(user.password, current_password):
                return {"message": "Current password is incorrect"}, 401

            user.password = generate_password_hash(new_password)
            db.session.commit()

            return {"message": "Password changed successfully"}, 200

        except SQLAlchemyError as e:
            logger.error(f"Database error while changing password: {str(e)}")
            return {"message": "Database error"}, 500
        

    @staticmethod
    def get_account_settings():
        """
        Fetch account and bank details for the currently logged-in merchant.
        """
        try:
            user_id = get_jwt_identity()
            merchant = MerchantProfile.get_by_user_id(user_id)

            if not merchant:
                return {"message": "Merchant not found"}, 404

            return {
                "email": merchant.business_email,
                "phone": merchant.business_phone,
                "account_number": merchant.bank_account_number,
                "account_name": merchant.business_name,
                "branch_name": merchant.bank_branch,
                "bank_name": merchant.bank_name,
                "ifsc_code": merchant.bank_ifsc_code
            }, 200

        except SQLAlchemyError as e:
            return {"message": "Error fetching merchant data"}, 500
