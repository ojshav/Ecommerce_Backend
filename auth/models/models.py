import bcrypt
import uuid
from datetime import datetime
from enum import Enum

from common.database import db, BaseModel
from auth.models.merchant_document import VerificationStatus, DocumentType

class UserRole(Enum):
    USER = 'user'
    MERCHANT = 'merchant'
    ADMIN = 'admin'
    SUPER_ADMIN = 'super_admin'

class AuthProvider(Enum):
    LOCAL = 'local'
    GOOGLE = 'google'
    # Can add other providers later (Facebook, Apple, etc.)

class User(BaseModel):
    """User model for all types of users (customers, merchants, admins)."""
    __tablename__ = 'users'
    
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)  # Nullable for OAuth users
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    role = db.Column(db.Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_email_verified = db.Column(db.Boolean, default=False, nullable=False)
    is_phone_verified = db.Column(db.Boolean, default=False, nullable=False)
    auth_provider = db.Column(db.Enum(AuthProvider), default=AuthProvider.LOCAL, nullable=False)
    provider_user_id = db.Column(db.String(255), nullable=True)  # For OAuth provider user ID
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    merchant_profile = db.relationship('MerchantProfile', back_populates='user', uselist=False)
    refresh_tokens = db.relationship('RefreshToken', back_populates='user', cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash password."""
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def check_password(self, password):
        """Verify password."""
        if self.password_hash is None:
            return False
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def update_last_login(self):
        """Update last login timestamp."""
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    @classmethod
    def get_by_email(cls, email):
        """Get user by email."""
        return cls.query.filter_by(email=email).first()
    
    @classmethod
    def get_by_provider_id(cls, provider, provider_user_id):
        """Get user by OAuth provider ID."""
        return cls.query.filter_by(
            auth_provider=provider,
            provider_user_id=provider_user_id
        ).first()

class MerchantProfile(BaseModel):
    """Merchant profile model."""
    __tablename__ = 'merchant_profiles'
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    business_name = db.Column(db.String(200), nullable=False)
    business_description = db.Column(db.Text, nullable=True)
    business_email = db.Column(db.String(120), nullable=False)
    business_phone = db.Column(db.String(20), nullable=False)
    business_address = db.Column(db.Text, nullable=False)
    gstin = db.Column(db.String(15), nullable=True)
    pan_number = db.Column(db.String(10), nullable=True)
    store_url = db.Column(db.String(255), nullable=True)
    logo_url = db.Column(db.String(255), nullable=True)
    logo_public_id = db.Column(db.String(255), nullable=True)  # Cloudinary public ID
    verification_status = db.Column(db.Enum(VerificationStatus), default=VerificationStatus.PENDING, nullable=False)
    verification_submitted_at = db.Column(db.DateTime, nullable=True)
    verification_completed_at = db.Column(db.DateTime, nullable=True)
    verification_notes = db.Column(db.Text, nullable=True)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relationships
    user = db.relationship('User', back_populates='merchant_profile')
    documents = db.relationship('MerchantDocument', back_populates='merchant', cascade='all, delete-orphan')
    
    @classmethod
    def get_by_user_id(cls, user_id):
        """Get merchant profile by user ID."""
        return cls.query.filter_by(user_id=user_id).first()
    
    @classmethod
    def get_by_business_name(cls, business_name):
        """Get merchant profile by business name."""
        return cls.query.filter_by(business_name=business_name).first()
    
    def update_verification_status(self, status, notes=None):
        """Update verification status."""
        self.verification_status = status
        if status == VerificationStatus.APPROVED:
            self.is_verified = True
            self.verification_completed_at = datetime.utcnow()
        elif status == VerificationStatus.REJECTED:
            self.is_verified = False
            self.verification_completed_at = datetime.utcnow()
        
        if notes:
            self.verification_notes = notes
            
        db.session.commit()
    
    def submit_for_verification(self):
        """Submit profile for verification."""
        self.verification_status = VerificationStatus.DOCUMENTS_SUBMITTED
        self.verification_submitted_at = datetime.utcnow()
        db.session.commit()

class RefreshToken(BaseModel):
    """Refresh token model for JWT authentication."""
    __tablename__ = 'refresh_tokens'
    
    token = db.Column(db.String(255), nullable=False, unique=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_revoked = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relationships
    user = db.relationship('User', back_populates='refresh_tokens')
    
    @classmethod
    def create_token(cls, user_id, expires_at):
        """Create a new refresh token."""
        token = str(uuid.uuid4())
        refresh_token = cls(
            token=token,
            user_id=user_id,
            expires_at=expires_at
        )
        refresh_token.save()
        return token
    
    @classmethod
    def get_by_token(cls, token):
        """Get refresh token by token string."""
        return cls.query.filter_by(token=token, is_revoked=False).first()
    
    def revoke(self):
        """Revoke refresh token."""
        self.is_revoked = True
        db.session.commit()
    
    @classmethod
    def revoke_all_for_user(cls, user_id):
        """Revoke all refresh tokens for a user."""
        tokens = cls.query.filter_by(user_id=user_id, is_revoked=False).all()
        for token in tokens:
            token.is_revoked = True
        db.session.commit()

class EmailVerification(BaseModel):
    """Email verification token model."""
    __tablename__ = 'email_verifications'
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(255), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    
    @classmethod
    def create_token(cls, user_id, expires_at):
        """Create a new verification token."""
        token = str(uuid.uuid4())
        verification = cls(
            token=token,
            user_id=user_id,
            expires_at=expires_at
        )
        verification.save()
        return token
    
    @classmethod
    def get_by_token(cls, token):
        """Get verification by token."""
        return cls.query.filter_by(token=token, is_used=False).first()
    
    def use(self):
        """Mark verification token as used."""
        self.is_used = True
        db.session.commit()

class PhoneVerification(BaseModel):
    """Phone verification OTP model."""
    __tablename__ = 'phone_verifications'
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    otp = db.Column(db.String(6), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    
    @classmethod
    def create_otp(cls, user_id, phone, expires_at):
        """Create a new OTP."""
        import random
        otp = ''.join(random.choices('0123456789', k=6))
        verification = cls(
            user_id=user_id,
            phone=phone,
            otp=otp,
            expires_at=expires_at
        )
        verification.save()
        return otp
    
    @classmethod
    def verify_otp(cls, user_id, otp):
        """Verify OTP for user."""
        verification = cls.query.filter_by(
            user_id=user_id,
            otp=otp,
            is_used=False
        ).first()
        
        if not verification:
            return False
        
        if verification.expires_at < datetime.utcnow():
            return False
        
        verification.is_used = True
        db.session.commit()
        
        # Update user's phone verification status
        user = User.get_by_id(user_id)
        if user:
            user.is_phone_verified = True
            db.session.commit()
            
            # Update merchant verification status if applicable
            if user.role == UserRole.MERCHANT:
                merchant = MerchantProfile.get_by_user_id(user_id)
                if merchant and merchant.verification_status == VerificationStatus.EMAIL_VERIFIED:
                    merchant.verification_status = VerificationStatus.PHONE_VERIFIED
                    db.session.commit()
        
        return True