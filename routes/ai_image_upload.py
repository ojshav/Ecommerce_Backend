"""
Temporary image upload endpoint for AI Product Description feature
Uploads images to AWS S3 and returns URLs for AI processing
"""
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename
from services.s3_service import get_s3_service
from http import HTTPStatus
from auth.utils import merchant_role_required

ai_image_upload_bp = Blueprint('ai_image_upload', __name__)

# Configure allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@ai_image_upload_bp.route('/api/merchant-dashboard/upload-temp-image', methods=['POST'])
@jwt_required()
@merchant_role_required
def upload_temp_image():
    """
    Upload temporary image to AWS S3 for AI processing
    Returns the CloudFront URL and S3 key that can be used by the AI service
    """
    try:
        # Check if file is present in request
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), HTTPStatus.BAD_REQUEST
        
        file = request.files['file']
        
        # Check if file is selected
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), HTTPStatus.BAD_REQUEST
        
        # Check file extension
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP'}), HTTPStatus.BAD_REQUEST
        
        # Upload to S3
        s3_service = get_s3_service()
        upload_result = s3_service.upload_ai_temp_image(file)
        
        # Get file extension for format
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        return jsonify({
            'success': True,
            'url': upload_result.get('url'),
            'image_url': upload_result.get('url'),
            'public_id': upload_result.get('s3_key'),
            'format': file_ext,
            'bytes': upload_result.get('bytes', 0),
            'message': 'Image uploaded successfully to S3'
        }), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"AI temp image upload failed: {str(e)}")
        return jsonify({
            'error': 'Failed to upload image',
            'details': str(e)
        }), HTTPStatus.INTERNAL_SERVER_ERROR

@ai_image_upload_bp.route('/api/merchant-dashboard/delete-temp-image/<path:public_id>', methods=['DELETE'])
@jwt_required()
@merchant_role_required
def delete_temp_image(public_id):
    """
    Delete temporary uploaded image from AWS S3
    Note: public_id can be S3 key or CloudFront URL
    """
    try:
        # Delete from S3
        s3_service = get_s3_service()
        result = s3_service.delete_ai_temp_image(public_id)
        
        if result:
            return jsonify({
                'success': True,
                'message': 'Image deleted successfully from S3'
            }), HTTPStatus.OK
        else:
            return jsonify({
                'error': 'File not found or already deleted'
            }), HTTPStatus.NOT_FOUND
            
    except Exception as e:
        current_app.logger.error(f"AI temp image deletion failed: {str(e)}")
        return jsonify({
            'error': 'Failed to delete image',
            'details': str(e)
        }), HTTPStatus.INTERNAL_SERVER_ERROR

