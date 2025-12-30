"""
AWS S3 Service for Product Media Uploads (Images and Videos)
Handles upload, update, and delete operations for product images and videos to S3
"""
import os
import uuid
from flask import current_app
from werkzeug.utils import secure_filename
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config


class S3ProductMediaService:
    """Service for handling product media (images and videos) uploads to AWS S3"""
    
    def __init__(self):
        """Initialize S3 client with credentials from environment"""
        # Use environment variable if set, otherwise default to specified bucket
        self.bucket_name = os.getenv('AWS_S3_BUCKET_NAME', 'aoin-assets-prod')
        self.region = os.getenv('AWS_REGION', 'ap-south-1')
        self.cloudfront_base_url = os.getenv('CLOUDFRONT_ASSETS_BASE_URL')
        
        if not self.cloudfront_base_url:
            raise ValueError("CLOUDFRONT_ASSETS_BASE_URL environment variable is required")
        
        # Configure boto3 client
        # Note: boto3 automatically handles multipart uploads for large files
        # Only valid Config parameters are used (multipart_threshold is NOT a valid Config parameter)
        config = Config(
            region_name=self.region,
            retries={'max_attempts': 3, 'mode': 'standard'}
        )
        
        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=self.region,
            config=config
        )
    
    def _generate_unique_filename(self, original_filename, product_id):
        """
        Generate a unique filename for the uploaded file
        Format: products/{product_id}/{uuid}_{secure_filename}
        """
        # Get file extension
        file_ext = ''
        if '.' in original_filename:
            file_ext = '.' + original_filename.rsplit('.', 1)[1].lower()
        
        # Generate unique filename
        unique_id = str(uuid.uuid4())
        secure_name = secure_filename(original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename)
        
        # Construct S3 key
        s3_key = f"products/{product_id}/{unique_id}_{secure_name}{file_ext}"
        
        return s3_key
    
    def upload_product_media(self, file, product_id):
        """
        Upload a product media file (image or video) to S3
        
        Args:
            file: FileStorage object from Flask request
            product_id: Product ID for organizing files
            
        Returns:
            dict: {
                'url': CloudFront URL,
                's3_key': S3 object key (for deletion),
                'filename': Original filename
            }
            
        Raises:
            Exception: If upload fails
        """
        try:
            print(f"[S3_UPLOAD] Starting S3 upload for product {product_id}")
            print(f"[S3_UPLOAD] Filename: {file.filename}")
            print(f"[S3_UPLOAD] Content type: {file.content_type}")
            print(f"[S3_UPLOAD] Bucket: {self.bucket_name}")
            print(f"[S3_UPLOAD] Region: {self.region}")
            current_app.logger.info(f"[S3_UPLOAD] Starting S3 upload for product {product_id}: filename={file.filename}, content_type={file.content_type}, bucket={self.bucket_name}")
            
            # Generate unique S3 key
            print(f"[S3_UPLOAD] Generating S3 key...")
            s3_key = self._generate_unique_filename(file.filename, product_id)
            print(f"[S3_UPLOAD] Generated S3 key: {s3_key}")
            current_app.logger.info(f"[S3_UPLOAD] Generated S3 key: {s3_key}")
            
            # Reset file pointer to beginning (important for file streams)
            # Check if file is seekable before seeking
            print(f"[S3_UPLOAD] Checking file pointer position...")
            if hasattr(file, 'seek') and hasattr(file, 'tell'):
                try:
                    current_pos = file.tell()
                    print(f"[S3_UPLOAD] Current file position: {current_pos}")
                    if current_pos != 0:
                        print(f"[S3_UPLOAD] Resetting file pointer to 0...")
                        file.seek(0)
                        print(f"[S3_UPLOAD] File pointer reset to 0")
                        current_app.logger.info(f"[S3_UPLOAD] Reset file pointer from position {current_pos} to 0")
                    else:
                        print(f"[S3_UPLOAD] File pointer already at position 0")
                except (IOError, OSError) as seek_error:
                    print(f"[S3_UPLOAD] WARNING: Could not seek file: {seek_error}")
                    current_app.logger.warning(f"[S3_UPLOAD] Could not seek file to beginning: {seek_error}. Continuing anyway.")
            else:
                print(f"[S3_UPLOAD] WARNING: File object does not support seek/tell")
                current_app.logger.warning("[S3_UPLOAD] File object does not support seek/tell operations")
            
            # Determine content type
            content_type = file.content_type or 'application/octet-stream'
            
            # For videos, ensure proper content type
            if file.content_type and file.content_type.startswith('video/'):
                # Keep video content type as is
                pass
            elif file.filename:
                # Try to infer content type from extension if not set
                ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                if ext in ['mp4']:
                    content_type = 'video/mp4'
                elif ext in ['mov']:
                    content_type = 'video/quicktime'
                elif ext in ['avi']:
                    content_type = 'video/x-msvideo'
                elif ext in ['mkv']:
                    content_type = 'video/x-matroska'
            
            # Upload to S3
            # For large files (especially videos), boto3 automatically uses multipart upload
            # Note: ACL is optional - bucket policy should handle public access
            upload_args = {
                'ContentType': content_type
            }
            # Only set ACL if bucket doesn't have a bucket policy for public access
            # Commented out as bucket policy should handle this
            # upload_args['ACL'] = 'public-read'
            
            # boto3 automatically uses multipart upload for large files
            # The client is already configured with multipart support in __init__
            print(f"[S3_UPLOAD] Starting boto3 upload_fileobj()...")
            print(f"[S3_UPLOAD] Bucket: {self.bucket_name}")
            print(f"[S3_UPLOAD] Key: {s3_key}")
            print(f"[S3_UPLOAD] Content type: {content_type}")
            print(f"[S3_UPLOAD] Upload args: {upload_args}")
            current_app.logger.info(f"[S3_UPLOAD] Uploading to S3: bucket={self.bucket_name}, key={s3_key}, content_type={content_type}")
            
            # This is the actual AWS S3 upload call
            print(f"[S3_UPLOAD] Calling s3_client.upload_fileobj() - THIS IS THE AWS UPLOAD...")
            self.s3_client.upload_fileobj(
                file,
                self.bucket_name,
                s3_key,
                ExtraArgs=upload_args
            )
            print(f"[S3_UPLOAD] SUCCESS: boto3 upload_fileobj() completed!")
            current_app.logger.info(f"[S3_UPLOAD] S3 upload completed successfully for key: {s3_key}")
            
            # Construct CloudFront URL
            print(f"[S3_UPLOAD] Constructing CloudFront URL...")
            cloudfront_url = f"{self.cloudfront_base_url.rstrip('/')}/{s3_key}"
            print(f"[S3_UPLOAD] CloudFront URL: {cloudfront_url}")
            
            media_type = 'video' if content_type.startswith('video/') else 'image'
            print(f"[S3_UPLOAD] Upload successful! Media type: {media_type}")
            current_app.logger.info(f"[S3_UPLOAD] Successfully uploaded product {media_type} to S3: {s3_key}")
            
            result = {
                'url': cloudfront_url,
                's3_key': s3_key,
                'filename': file.filename
            }
            print(f"[S3_UPLOAD] Returning result: {result}")
            return result
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            current_app.logger.error(f"AWS S3 upload error for product {product_id}: Code={error_code}, Message={error_message}, Full error: {str(e)}")
            
            # Provide more specific error messages
            if error_code == 'AccessDenied':
                raise Exception(f"AWS S3 Access Denied: Check your AWS credentials and bucket permissions. Details: {error_message}")
            elif error_code == 'NoSuchBucket':
                raise Exception(f"AWS S3 Bucket not found: {self.bucket_name}. Check your bucket name configuration.")
            elif error_code == 'InvalidAccessKeyId':
                raise Exception(f"AWS S3 Invalid Access Key: Check your AWS_ACCESS_KEY_ID environment variable.")
            elif error_code == 'SignatureDoesNotMatch':
                raise Exception(f"AWS S3 Signature Mismatch: Check your AWS_SECRET_ACCESS_KEY environment variable.")
            else:
                raise Exception(f"AWS S3 upload failed ({error_code}): {error_message}")
        except Exception as e:
            current_app.logger.error(f"Unexpected error uploading product media to S3: {str(e)}", exc_info=True)
            raise Exception(f"Failed to upload media to S3: {str(e)}")
    
    def upload_product_image(self, file, product_id):
        """
        Upload a product image to S3 (backward compatibility)
        """
        return self.upload_product_media(file, product_id)
    
    def delete_product_media(self, url_or_s3_key):
        """
        Delete a product media file (image or video) from S3
        
        Args:
            url_or_s3_key: Either a CloudFront URL or S3 key
            
        Returns:
            bool: True if deletion succeeded, False otherwise
            
        Note:
            Does not raise exceptions - logs errors only
        """
        try:
            # Extract S3 key from URL if it's a CloudFront URL
            s3_key = self._extract_s3_key_from_url(url_or_s3_key)
            
            if not s3_key:
                current_app.logger.warning(f"Could not extract S3 key from URL: {url_or_s3_key}")
                return False
            
            # Delete from S3
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            current_app.logger.info(f"Successfully deleted product media from S3: {s3_key}")
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'NoSuchKey':
                current_app.logger.warning(f"Media file not found in S3 (may have been already deleted): {s3_key}")
            else:
                current_app.logger.error(f"AWS S3 delete error: {str(e)}")
            return False
        except Exception as e:
            current_app.logger.error(f"Unexpected error deleting product media from S3: {str(e)}")
            return False
    
    def delete_product_image(self, url_or_s3_key):
        """
        Delete a product image from S3 (backward compatibility)
        """
        return self.delete_product_media(url_or_s3_key)
    
    def _extract_s3_key_from_url(self, url_or_key):
        """
        Extract S3 key from CloudFront URL or return the key if it's already a key
        
        Args:
            url_or_key: CloudFront URL or S3 key
            
        Returns:
            str: S3 key or None if extraction fails
        """
        # If it's already a key (starts with 'products/'), return as is
        if url_or_key.startswith('products/'):
            return url_or_key
        
        # If it's a CloudFront URL, extract the key
        if self.cloudfront_base_url and self.cloudfront_base_url in url_or_key:
            # Remove CloudFront base URL and leading slash
            key = url_or_key.replace(self.cloudfront_base_url, '').lstrip('/')
            return key
        
        # If it contains 'products/', try to extract from URL
        if 'products/' in url_or_key:
            # Extract everything after the domain
            parts = url_or_key.split('products/')
            if len(parts) > 1:
                return 'products/' + parts[1].split('?')[0]  # Remove query params if any
        
        return None
    
    def update_product_media(self, file, product_id, old_url_or_s3_key):
        """
        Update/replace a product media file in S3
        This deletes the old file and uploads a new one
        
        Args:
            file: New FileStorage object
            product_id: Product ID
            old_url_or_s3_key: URL or S3 key of the old file to delete
            
        Returns:
            dict: {
                'url': New CloudFront URL,
                's3_key': New S3 object key,
                'filename': Original filename
            }
        """
        # Delete old file (don't fail if this fails)
        if old_url_or_s3_key:
            self.delete_product_media(old_url_or_s3_key)
        
        # Upload new file
        return self.upload_product_media(file, product_id)
    
    def update_product_image(self, file, product_id, old_url_or_s3_key):
        """
        Update/replace a product image in S3 (backward compatibility)
        """
        return self.update_product_media(file, product_id, old_url_or_s3_key)
    
    def upload_merchant_document(self, file, merchant_id):
        """
        Upload a merchant document to S3
        
        Args:
            file: FileStorage object from Flask request
            merchant_id: Merchant ID for organizing files
            
        Returns:
            dict: {
                'url': CloudFront URL,
                's3_key': S3 object key (for deletion),
                'filename': Original filename,
                'bytes': File size in bytes
            }
            
        Raises:
            Exception: If upload fails
        """
        if not self.cloudfront_base_url:
            raise ValueError("CLOUDFRONT_ASSETS_BASE_URL environment variable is required for S3 operations")
        
        try:
            current_app.logger.info(f"Starting S3 upload for merchant document: merchant_id={merchant_id}, filename={file.filename}, content_type={file.content_type}")
            
            # Generate unique S3 key: merchant-documents/{merchant_id}/{uuid}_{secure_filename}
            s3_key = self._generate_merchant_document_filename(file.filename, merchant_id)
            current_app.logger.info(f"Generated S3 key: {s3_key}")
            
            # Reset file pointer to beginning
            if hasattr(file, 'seek') and hasattr(file, 'tell'):
                try:
                    current_pos = file.tell()
                    if current_pos != 0:
                        file.seek(0)
                        current_app.logger.info(f"Reset file pointer from position {current_pos} to 0")
                except (IOError, OSError) as seek_error:
                    current_app.logger.warning(f"Could not seek file to beginning: {seek_error}. Continuing anyway.")
            
            # Determine content type
            content_type = file.content_type or 'application/octet-stream'
            
            # Get file size
            file.seek(0, 2)  # Move to end
            file_size = file.tell()
            file.seek(0)  # Reset to start
            
            upload_args = {
                'ContentType': content_type
            }
            
            current_app.logger.info(f"Uploading to S3: bucket={self.bucket_name}, key={s3_key}, content_type={content_type}, size={file_size}")
            
            # Upload to S3
            self.s3_client.upload_fileobj(
                file,
                self.bucket_name,
                s3_key,
                ExtraArgs=upload_args
            )
            current_app.logger.info(f"S3 upload completed successfully for key: {s3_key}")
            
            # Construct CloudFront URL
            cloudfront_url = f"{self.cloudfront_base_url.rstrip('/')}/{s3_key}"
            
            current_app.logger.info(f"Successfully uploaded merchant document to S3: {s3_key}")
            
            return {
                'url': cloudfront_url,
                's3_key': s3_key,
                'filename': file.filename,
                'bytes': file_size
            }
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            current_app.logger.error(f"AWS S3 upload error for merchant document {merchant_id}: Code={error_code}, Message={error_message}, Full error: {str(e)}")
            
            if error_code == 'AccessDenied':
                raise Exception(f"AWS S3 Access Denied: Check your AWS credentials and bucket permissions. Details: {error_message}")
            elif error_code == 'NoSuchBucket':
                raise Exception(f"AWS S3 Bucket not found: {self.bucket_name}. Check your bucket name configuration.")
            elif error_code == 'InvalidAccessKeyId':
                raise Exception(f"AWS S3 Invalid Access Key: Check your AWS_ACCESS_KEY_ID environment variable.")
            elif error_code == 'SignatureDoesNotMatch':
                raise Exception(f"AWS S3 Signature Mismatch: Check your AWS_SECRET_ACCESS_KEY environment variable.")
            else:
                raise Exception(f"AWS S3 upload failed ({error_code}): {error_message}")
        except Exception as e:
            current_app.logger.error(f"Unexpected error uploading merchant document to S3: {str(e)}", exc_info=True)
            raise Exception(f"Failed to upload document to S3: {str(e)}")
    
    def delete_merchant_document(self, url_or_s3_key):
        """
        Delete a merchant document from S3
        
        Args:
            url_or_s3_key: Either a CloudFront URL or S3 key
            
        Returns:
            bool: True if deletion succeeded, False otherwise
            
        Note:
            Does not raise exceptions - logs errors only
        """
        try:
            # Extract S3 key from URL if it's a CloudFront URL
            s3_key = self._extract_merchant_document_key_from_url(url_or_s3_key)
            
            if not s3_key:
                current_app.logger.warning(f"Could not extract S3 key from URL: {url_or_s3_key}")
                return False
            
            # Delete from S3
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            current_app.logger.info(f"Successfully deleted merchant document from S3: {s3_key}")
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'NoSuchKey':
                current_app.logger.warning(f"Document file not found in S3 (may have been already deleted): {s3_key}")
            else:
                current_app.logger.error(f"AWS S3 delete error: {str(e)}")
            return False
        except Exception as e:
            current_app.logger.error(f"Unexpected error deleting merchant document from S3: {str(e)}")
            return False
    
    def _generate_merchant_document_filename(self, original_filename, merchant_id):
        """
        Generate a unique filename for the uploaded merchant document
        Format: merchant-documents/{merchant_id}/{uuid}_{secure_filename}
        """
        # Get file extension
        file_ext = ''
        if '.' in original_filename:
            file_ext = '.' + original_filename.rsplit('.', 1)[1].lower()
        
        # Generate unique filename
        unique_id = str(uuid.uuid4())
        secure_name = secure_filename(original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename)
        
        # Construct S3 key
        s3_key = f"merchant-documents/{merchant_id}/{unique_id}_{secure_name}{file_ext}"
        
        return s3_key
    
    def _extract_merchant_document_key_from_url(self, url_or_key):
        """
        Extract S3 key from CloudFront URL or return the key if it's already a key
        
        Args:
            url_or_key: CloudFront URL or S3 key
            
        Returns:
            str: S3 key or None if extraction fails
        """
        # If it's already a key (starts with 'merchant-documents/'), return as is
        if url_or_key.startswith('merchant-documents/'):
            return url_or_key
        
        # If it's a CloudFront URL, extract the key
        if self.cloudfront_base_url and self.cloudfront_base_url in url_or_key:
            # Remove CloudFront base URL and leading slash
            key = url_or_key.replace(self.cloudfront_base_url, '').lstrip('/')
            return key
        
        # If it contains 'merchant-documents/', try to extract from URL
        if 'merchant-documents/' in url_or_key:
            # Extract everything after the domain
            parts = url_or_key.split('merchant-documents/')
            if len(parts) > 1:
                return 'merchant-documents/' + parts[1].split('?')[0]  # Remove query params if any
        
        return None
    
    def upload_generic_asset(self, file):
        """
        Upload a generic asset (logo, icon, banner, etc.) to S3
        Format: assets/{uuid}_{secure_filename}
        
        Args:
            file: FileStorage object from Flask request
            
        Returns:
            dict: {
                'url': CloudFront URL,
                's3_key': S3 object key (for deletion),
                'filename': Original filename,
                'bytes': File size in bytes (if available)
            }
            
        Raises:
            Exception: If upload fails
        """
        if not self.cloudfront_base_url:
            raise ValueError("CLOUDFRONT_ASSETS_BASE_URL environment variable is required for S3 operations")
        
        try:
            current_app.logger.info(f"Starting S3 upload for generic asset: filename={file.filename}, content_type={file.content_type}")
            
            # Generate unique S3 key: assets/{uuid}_{secure_filename}
            s3_key = self._generate_generic_asset_filename(file.filename)
            current_app.logger.info(f"Generated S3 key: {s3_key}")
            
            # Reset file pointer to beginning
            if hasattr(file, 'seek') and hasattr(file, 'tell'):
                try:
                    current_pos = file.tell()
                    if current_pos != 0:
                        file.seek(0)
                        current_app.logger.info(f"Reset file pointer from position {current_pos} to 0")
                except (IOError, OSError) as seek_error:
                    current_app.logger.warning(f"Could not seek file to beginning: {seek_error}. Continuing anyway.")
            
            # Determine content type
            content_type = file.content_type or 'application/octet-stream'
            
            # Get file size if available
            file_size = None
            if hasattr(file, 'content_length') and file.content_length:
                file_size = file.content_length
            else:
                try:
                    file.seek(0, 2)  # Move to end
                    file_size = file.tell()
                    file.seek(0)  # Reset to start
                except (IOError, OSError):
                    pass  # File size not available
            
            upload_args = {
                'ContentType': content_type
            }
            
            current_app.logger.info(f"Uploading to S3: bucket={self.bucket_name}, key={s3_key}, content_type={content_type}, size={file_size}")
            
            # Upload to S3
            self.s3_client.upload_fileobj(
                file,
                self.bucket_name,
                s3_key,
                ExtraArgs=upload_args
            )
            current_app.logger.info(f"S3 upload completed successfully for key: {s3_key}")
            
            # Construct CloudFront URL
            cloudfront_url = f"{self.cloudfront_base_url.rstrip('/')}/{s3_key}"
            
            current_app.logger.info(f"Successfully uploaded generic asset to S3: {s3_key}")
            
            result = {
                'url': cloudfront_url,
                's3_key': s3_key,
                'filename': file.filename,
                'secure_url': cloudfront_url,  # Alias for backward compatibility
                'public_id': s3_key  # Alias for backward compatibility (stores S3 key)
            }
            
            if file_size:
                result['bytes'] = file_size
            
            return result
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            current_app.logger.error(f"AWS S3 upload error for generic asset: Code={error_code}, Message={error_message}, Full error: {str(e)}")
            
            if error_code == 'AccessDenied':
                raise Exception(f"AWS S3 Access Denied: Check your AWS credentials and bucket permissions. Details: {error_message}")
            elif error_code == 'NoSuchBucket':
                raise Exception(f"AWS S3 Bucket not found: {self.bucket_name}. Check your bucket name configuration.")
            elif error_code == 'InvalidAccessKeyId':
                raise Exception(f"AWS S3 Invalid Access Key: Check your AWS_ACCESS_KEY_ID environment variable.")
            elif error_code == 'SignatureDoesNotMatch':
                raise Exception(f"AWS S3 Signature Mismatch: Check your AWS_SECRET_ACCESS_KEY environment variable.")
            else:
                raise Exception(f"AWS S3 upload failed ({error_code}): {error_message}")
        except Exception as e:
            current_app.logger.error(f"Unexpected error uploading generic asset to S3: {str(e)}", exc_info=True)
            raise Exception(f"Failed to upload asset to S3: {str(e)}")
    
    def delete_generic_asset(self, url_or_s3_key):
        """
        Delete a generic asset from S3
        
        Args:
            url_or_s3_key: Either a CloudFront URL or S3 key
            
        Returns:
            bool: True if deletion succeeded, False otherwise
            
        Note:
            Does not raise exceptions - logs errors only
        """
        try:
            # Extract S3 key from URL if it's a CloudFront URL
            s3_key = self._extract_generic_asset_key_from_url(url_or_s3_key)
            
            if not s3_key:
                current_app.logger.warning(f"Could not extract S3 key from URL: {url_or_s3_key}")
                return False
            
            # Delete from S3
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            current_app.logger.info(f"Successfully deleted generic asset from S3: {s3_key}")
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'NoSuchKey':
                current_app.logger.warning(f"Asset file not found in S3 (may have been already deleted): {s3_key}")
            else:
                current_app.logger.error(f"AWS S3 delete error: {str(e)}")
            return False
        except Exception as e:
            current_app.logger.error(f"Unexpected error deleting generic asset from S3: {str(e)}")
            return False
    
    def _generate_generic_asset_filename(self, original_filename):
        """
        Generate a unique filename for the uploaded generic asset
        Format: assets/{uuid}_{secure_filename}
        """
        # Get file extension
        file_ext = ''
        if '.' in original_filename:
            file_ext = '.' + original_filename.rsplit('.', 1)[1].lower()
        
        # Generate unique filename
        unique_id = str(uuid.uuid4())
        secure_name = secure_filename(original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename)
        
        # Construct S3 key
        s3_key = f"assets/{unique_id}_{secure_name}{file_ext}"
        
        return s3_key
    
    def _extract_generic_asset_key_from_url(self, url_or_key):
        """
        Extract S3 key from CloudFront URL or return the key if it's already a key
        
        Args:
            url_or_key: CloudFront URL or S3 key
            
        Returns:
            str: S3 key or None if extraction fails
        """
        # If it's already a key (starts with 'assets/'), return as is
        if url_or_key.startswith('assets/'):
            return url_or_key
        
        # If it's a CloudFront URL, extract the key
        if self.cloudfront_base_url and self.cloudfront_base_url in url_or_key:
            # Remove CloudFront base URL and leading slash
            key = url_or_key.replace(self.cloudfront_base_url, '').lstrip('/')
            return key
        
        # If it contains 'assets/', try to extract from URL
        if 'assets/' in url_or_key:
            # Extract everything after the domain
            parts = url_or_key.split('assets/')
            if len(parts) > 1:
                return 'assets/' + parts[1].split('?')[0]  # Remove query params if any
        
        return None
    
    def upload_ai_temp_image(self, file):
        """
        Upload AI temp image to S3
        Format: assets/ai-temp/{uuid}_{secure_filename}
        """
        file_ext = ''
        if '.' in file.filename:
            file_ext = '.' + file.filename.rsplit('.', 1)[1].lower()
        secure_name = secure_filename(file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename)
        s3_key = f"assets/ai-temp/{uuid.uuid4()}_{secure_name}{file_ext}"
        return self._upload_asset_with_path(file, s3_key)
    
    def upload_profile_image(self, file, user_id):
        """
        Upload user profile image to S3
        Format: assets/profile-images/{user_id}_{uuid}_{secure_filename}
        """
        file_ext = ''
        if '.' in file.filename:
            file_ext = '.' + file.filename.rsplit('.', 1)[1].lower()
        secure_name = secure_filename(file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename)
        s3_key = f"assets/profile-images/{user_id}_{uuid.uuid4()}_{secure_name}{file_ext}"
        return self._upload_asset_with_path(file, s3_key)
    
    def upload_carousel_image(self, file):
        """
        Upload carousel image to S3
        Format: assets/carousel/{uuid}_{secure_filename}
        """
        file_ext = ''
        if '.' in file.filename:
            file_ext = '.' + file.filename.rsplit('.', 1)[1].lower()
        secure_name = secure_filename(file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename)
        s3_key = f"assets/carousel/{uuid.uuid4()}_{secure_name}{file_ext}"
        return self._upload_asset_with_path(file, s3_key)
    
    def upload_support_attachment(self, file, folder_name="support_attachments"):
        """
        Upload support ticket attachment to S3
        Format: assets/support/{folder_name}/{uuid}_{secure_filename}
        """
        file_ext = ''
        if '.' in file.filename:
            file_ext = '.' + file.filename.rsplit('.', 1)[1].lower()
        secure_name = secure_filename(file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename)
        s3_key = f"assets/support/{folder_name}/{uuid.uuid4()}_{secure_name}{file_ext}"
        return self._upload_asset_with_path(file, s3_key)
    
    def upload_review_image(self, file, review_id):
        """
        Upload review image to S3
        Format: assets/reviews/{review_id}/{uuid}_{secure_filename}
        """
        file_ext = ''
        if '.' in file.filename:
            file_ext = '.' + file.filename.rsplit('.', 1)[1].lower()
        secure_name = secure_filename(file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename)
        s3_key = f"assets/reviews/{review_id}/{uuid.uuid4()}_{secure_name}{file_ext}"
        return self._upload_asset_with_path(file, s3_key)
    
    def upload_variant_image(self, file, shop_id, product_id):
        """
        Upload variant image (NOT video) to S3
        Format: assets/variants/shop_{shop_id}/product_{product_id}/{uuid}_{secure_filename}
        """
        file_ext = ''
        if '.' in file.filename:
            file_ext = '.' + file.filename.rsplit('.', 1)[1].lower()
        secure_name = secure_filename(file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename)
        s3_key = f"assets/variants/shop_{shop_id}/product_{product_id}/{uuid.uuid4()}_{secure_name}{file_ext}"
        return self._upload_asset_with_path(file, s3_key)
    
    def _upload_asset_with_path(self, file, s3_key):
        """
        Internal helper to upload an asset with a specific S3 key path
        """
        if not self.cloudfront_base_url:
            raise ValueError("CLOUDFRONT_ASSETS_BASE_URL environment variable is required for S3 operations")
        
        try:
            current_app.logger.info(f"Starting S3 upload: filename={file.filename}, s3_key={s3_key}, content_type={file.content_type}")
            
            # Reset file pointer to beginning
            if hasattr(file, 'seek') and hasattr(file, 'tell'):
                try:
                    current_pos = file.tell()
                    if current_pos != 0:
                        file.seek(0)
                        current_app.logger.info(f"Reset file pointer from position {current_pos} to 0")
                except (IOError, OSError) as seek_error:
                    current_app.logger.warning(f"Could not seek file to beginning: {seek_error}. Continuing anyway.")
            
            # Determine content type
            content_type = file.content_type or 'application/octet-stream'
            
            # Get file size if available
            file_size = None
            if hasattr(file, 'content_length') and file.content_length:
                file_size = file.content_length
            else:
                try:
                    file.seek(0, 2)  # Move to end
                    file_size = file.tell()
                    file.seek(0)  # Reset to start
                except (IOError, OSError):
                    pass  # File size not available
            
            upload_args = {
                'ContentType': content_type
            }
            
            current_app.logger.info(f"Uploading to S3: bucket={self.bucket_name}, key={s3_key}, content_type={content_type}, size={file_size}")
            
            # Upload to S3
            self.s3_client.upload_fileobj(
                file,
                self.bucket_name,
                s3_key,
                ExtraArgs=upload_args
            )
            current_app.logger.info(f"S3 upload completed successfully for key: {s3_key}")
            
            # Construct CloudFront URL
            cloudfront_url = f"{self.cloudfront_base_url.rstrip('/')}/{s3_key}"
            
            current_app.logger.info(f"Successfully uploaded asset to S3: {s3_key}")
            
            result = {
                'url': cloudfront_url,
                's3_key': s3_key,
                'filename': file.filename,
                'secure_url': cloudfront_url,  # Alias for backward compatibility
                'public_id': s3_key  # Alias for backward compatibility (stores S3 key)
            }
            
            if file_size:
                result['bytes'] = file_size
            
            return result
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            current_app.logger.error(f"AWS S3 upload error: Code={error_code}, Message={error_message}, Full error: {str(e)}")
            
            if error_code == 'AccessDenied':
                raise Exception(f"AWS S3 Access Denied: Check your AWS credentials and bucket permissions. Details: {error_message}")
            elif error_code == 'NoSuchBucket':
                raise Exception(f"AWS S3 Bucket not found: {self.bucket_name}. Check your bucket name configuration.")
            elif error_code == 'InvalidAccessKeyId':
                raise Exception(f"AWS S3 Invalid Access Key: Check your AWS_ACCESS_KEY_ID environment variable.")
            elif error_code == 'SignatureDoesNotMatch':
                raise Exception(f"AWS S3 Signature Mismatch: Check your AWS_SECRET_ACCESS_KEY environment variable.")
            else:
                raise Exception(f"AWS S3 upload failed ({error_code}): {error_message}")
        except Exception as e:
            current_app.logger.error(f"Unexpected error uploading asset to S3: {str(e)}", exc_info=True)
            raise Exception(f"Failed to upload asset to S3: {str(e)}")
    
    def delete_ai_temp_image(self, url_or_s3_key):
        """Delete AI temp image from S3"""
        return self.delete_generic_asset(url_or_s3_key)
    
    def delete_profile_image(self, url_or_s3_key):
        """Delete profile image from S3"""
        return self.delete_generic_asset(url_or_s3_key)
    
    def delete_carousel_image(self, url_or_s3_key):
        """Delete carousel image from S3"""
        return self.delete_generic_asset(url_or_s3_key)
    
    def delete_support_attachment(self, url_or_s3_key):
        """Delete support attachment from S3"""
        return self.delete_generic_asset(url_or_s3_key)
    
    def delete_review_image(self, url_or_s3_key):
        """Delete review image from S3"""
        return self.delete_generic_asset(url_or_s3_key)
    
    def delete_variant_image(self, url_or_s3_key):
        """Delete variant image from S3"""
        return self.delete_generic_asset(url_or_s3_key)


# Singleton instance
_s3_service_instance = None

def get_s3_service():
    """Get or create singleton S3 service instance"""
    global _s3_service_instance
    try:
        if _s3_service_instance is None:
            _s3_service_instance = S3ProductMediaService()
    except Exception as e:
        # If initialization fails, log error but don't crash
        # This allows other endpoints to work even if S3 is misconfigured
        from flask import current_app
        current_app.logger.error(f"Failed to initialize S3 service: {str(e)}")
        # Reset and try again (might be a transient issue)
        _s3_service_instance = None
        try:
            _s3_service_instance = S3ProductMediaService()
        except Exception as retry_error:
            current_app.logger.error(f"Failed to initialize S3 service on retry: {str(retry_error)}")
            raise  # Re-raise if retry also fails
    return _s3_service_instance

def reset_s3_service():
    """Reset the singleton instance (useful for testing or after code changes)"""
    global _s3_service_instance
    _s3_service_instance = None

