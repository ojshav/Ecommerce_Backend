from flask import Blueprint, request, jsonify
from models.newsletter_subscription import NewsletterSubscription
from common.database import db
from datetime import datetime
from sqlalchemy.exc import IntegrityError

newsletter_public_bp = Blueprint('newsletter_public', __name__)

# Handle OPTIONS preflight for all routes in this blueprint
@newsletter_public_bp.before_request
def handle_preflight():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200

@newsletter_public_bp.route('/newsletter/subscribe', methods=['POST', 'OPTIONS'])
def subscribe_newsletter():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    data = request.get_json()
    email = data.get('email')
    if not email:
        return jsonify({'status': 'error', 'message': 'Email is required.'}), 400

    # Check if email already exists
    existing = NewsletterSubscription.query.filter_by(email=email).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Email already subscribed.'}), 400

    try:
        new_sub = NewsletterSubscription(
            email=email,
            created_at=datetime.utcnow()
        )
        db.session.add(new_sub)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Subscribed successfully.'}), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'Email already subscribed.'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Failed to subscribe: {str(e)}'}), 500 