from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename
from services.s3_service import get_s3_service
from http import HTTPStatus
import os

upload_bp = Blueprint('upload', __name__)

# Configure allowed file extensions
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'svg', 'gif', 'webp'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}

def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

@upload_bp.route('/image', methods=['POST'])
@jwt_required()
def upload_image():
    """
    Upload an image to AWS S3
    ---
    tags:
      - Upload
    security:
      - Bearer: []
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: image
        type: file
        required: true
        description: Image file to upload
      - in: formData
        name: folder
        type: string
        required: false
        description: "Folder parameter (kept for backward compatibility, ignored)"
    responses:
      200:
        description: Image uploaded successfully
        schema:
          type: object
          properties:
            secure_url:
              type: string
              description: CloudFront URL
            public_id:
              type: string
              description: S3 object key
            format:
              type: string
              description: Image format
            resource_type:
              type: string
              description: Resource type (image)
            bytes:
              type: integer
              description: File size in bytes
      400:
        description: No file provided or invalid file type
      500:
        description: Upload failed
    """
    try:
        # Check if file is present
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), HTTPStatus.BAD_REQUEST
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), HTTPStatus.BAD_REQUEST
        
        # Validate file type
        if not allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
            return jsonify({'error': 'Invalid file type. Allowed types: PNG, JPG, JPEG, SVG, GIF, WebP'}), HTTPStatus.BAD_REQUEST

        # Upload to S3
        s3_service = get_s3_service()
        upload_result = s3_service.upload_generic_asset(file)
        
        # Get file extension for format
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        return jsonify({
            'secure_url': upload_result.get('url'),
            'public_id': upload_result.get('s3_key'),
            'format': file_ext,
            'resource_type': 'image',
            'bytes': upload_result.get('bytes', 0)
        }), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Image upload failed: {str(e)}")
        return jsonify({'error': f'Upload failed: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR

@upload_bp.route('/video', methods=['POST'])
@jwt_required()
def upload_video():
    """
    Upload a video to Cloudinary
    ---
    tags:
      - Upload
    security:
      - Bearer: []
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: video
        type: file
        required: true
        description: Video file to upload
      - in: formData
        name: folder
        type: string
        required: false
        description: "Cloudinary folder to upload to (default: products)"
    responses:
      200:
        description: Video uploaded successfully
        schema:
          type: object
          properties:
            secure_url:
              type: string
              description: Cloudinary secure URL
            public_id:
              type: string
              description: Cloudinary public ID
            format:
              type: string
              description: Video format
            resource_type:
              type: string
              description: Resource type (video)
            bytes:
              type: integer
              description: File size in bytes
      400:
        description: No file provided or invalid file type
      500:
        description: Upload failed
    """
    try:
        # Check if file is present
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided'}), HTTPStatus.BAD_REQUEST
        
        file = request.files['video']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), HTTPStatus.BAD_REQUEST
        
        # Validate file type
        if not allowed_file(file.filename, ALLOWED_VIDEO_EXTENSIONS):
            return jsonify({'error': 'Invalid file type. Allowed types: MP4, MOV, AVI, MKV'}), HTTPStatus.BAD_REQUEST
        
        # Get folder parameter
        folder = request.form.get('folder', 'products')
        
        # Upload to Cloudinary
        upload_result = cloudinary.uploader.upload(
            file,
            folder=folder,
            resource_type="video",
            allowed_formats=list(ALLOWED_VIDEO_EXTENSIONS)
        )
        
        return jsonify({
            'secure_url': upload_result.get('secure_url'),
            'public_id': upload_result.get('public_id'),
            'format': upload_result.get('format'),
            'resource_type': 'video',
            'bytes': upload_result.get('bytes')
        }), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Video upload failed: {str(e)}")
        return jsonify({'error': f'Upload failed: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR

@upload_bp.route('/delete', methods=['DELETE'])
@jwt_required()
def delete_media():
    """
    Delete media from AWS S3
    ---
    tags:
      - Upload
    security:
      - Bearer: []
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            public_id:
              type: string
              description: S3 object key or CloudFront URL to delete
    responses:
      200:
        description: Media deleted successfully
      400:
        description: No public_id provided
      500:
        description: Deletion failed
    """
    try:
        data = request.get_json()
        if not data or 'public_id' not in data:
            return jsonify({'error': 'public_id is required'}), HTTPStatus.BAD_REQUEST
        
        url_or_key = data['public_id']
        
        # Delete from S3
        s3_service = get_s3_service()
        result = s3_service.delete_generic_asset(url_or_key)
        
        if result:
            return jsonify({'message': 'Media deleted successfully'}), HTTPStatus.OK
        else:
            return jsonify({'error': 'Failed to delete media'}), HTTPStatus.INTERNAL_SERVER_ERROR
        
    except Exception as e:
        current_app.logger.error(f"Media deletion failed: {str(e)}")
        return jsonify({'error': f'Deletion failed: {str(e)}'}), HTTPStatus.INTERNAL_SERVER_ERROR
