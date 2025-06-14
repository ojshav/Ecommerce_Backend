import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, render_template_string


# This master template ensures a consistent brand identity across all emails.
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="ie=edge">
    <title>{{ subject }}</title>
    <style>
        /* A Modern, Email-Client-Friendly Stylesheet */
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');
        
        body {
            margin: 0;
            padding: 0;
            width: 100% !important;
            -webkit-text-size-adjust: 100%;
            -ms-text-size-adjust: 100%;
            background-color: #f4f4f7;
            font-family: 'Poppins', Arial, sans-serif;
            color: #333333;
        }
        .container {
            width: 100%;
            max-width: 600px;
            margin: 0 auto;
        }
        .content-wrapper {
            background-color: #ffffff;
            padding: 30px 40px;
            border-radius: 8px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        }
        .header {
            padding: 20px 0;
            text-align: center;
        }
        .logo {
            max-width: 140px;
            height: auto;
        }
        .heading {
            font-size: 24px;
            font-weight: 700;
            color: #1a1a1a;
            margin: 20px 0;
        }
        p {
            font-size: 16px;
            line-height: 1.6;
            margin: 16px 0;
        }
        .button-wrapper {
            text-align: center;
            margin: 30px 0;
        }
        .button {
            display: inline-block;
            background-color: #F97316; /* AOIN Orange Theme */
            color: #ffffff !important;
            padding: 14px 28px;
            text-decoration: none !important;
            font-weight: 600;
            border-radius: 8px;
            font-size: 16px;
        }
        .link {
            word-break: break-all;
            color: #F97316;
            text-decoration: underline;
        }
        .footer {
            text-align: center;
            padding: 20px;
            font-size: 12px;
            color: #888888;
        }
    </style>
</head>
<body>
    <table width="100%" border="0" cellpadding="0" cellspacing="0" bgcolor="#f4f4f7">
        <tr>
            <td align="center" style="padding-top: 20px; padding-bottom: 20px;">
                <table class="container" border="0" cellpadding="0" cellspacing="0">
                    <!-- Header with Logo -->
                    <tr>
                        <td class="header">
                            <a href="{{ frontend_url }}" target="_blank">
                                <img src="{{ logo_url }}" alt="AOIN Logo" class="logo">
                            </a>
                        </td>
                    </tr>
                    <!-- Main Content Body -->
                    <tr>
                        <td>
                            <table class="content-wrapper" border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td>
                                        <h1 class="heading">{{ heading }}</h1>
                                        {{ content_html | safe }}
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td class="footer">
                            <p>© {{ year }} AOIN. All Rights Reserved.</p>
                            <p>This is an automated message. Please do not reply to this email.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

def send_email(to_email, subject, template_str, context):
    """
    Refactored send_email to inject content into a branded base template.
    This function's signature is kept the same for backward compatibility,
    but we will call it differently from our helper functions.
    """
    try:
        current_app.logger.info(f"Attempting to send email to {to_email}")

        # Add base context variables to every email
        context.update({
            'logo_url': 'https://res.cloudinary.com/dyj7ebc7z/image/upload/v1749809170/logo_w3l0tp.png', 
            'frontend_url': current_app.config.get('FRONTEND_URL', '#'),
            'year': datetime.now().year,
            'subject': subject
        })

        # The 'template_str' will now be the main body content,
        # which we wrap inside the base template.
        base_context = context.copy()
        base_context['heading'] = context.get('heading', subject)
        base_context['content_html'] = render_template_string(template_str, **context)
        
        full_html_content = render_template_string(BASE_TEMPLATE, **base_context)
        
        message = MIMEMultipart('alternative')
        message['Subject'] = subject
        sender = current_app.config['MAIL_DEFAULT_SENDER']
        
        if isinstance(sender, tuple):
            sender_name, sender_email = sender
            message['From'] = f"{sender_name} <{sender_email}>"
            sender_address = sender_email
        else:
            message['From'] = sender
            sender_address = sender
            
        message['To'] = to_email
        message.attach(MIMEText(full_html_content, 'html', 'utf-8'))
        
        with smtplib.SMTP(current_app.config['MAIL_SERVER'], current_app.config['MAIL_PORT']) as server:
            if current_app.config['MAIL_USE_TLS']:
                server.starttls()
            if current_app.config['MAIL_USERNAME'] and current_app.config['MAIL_PASSWORD']:
                server.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
            server.sendmail(sender_address, to_email, message.as_string())
        
        current_app.logger.info("Email sent successfully")
        return True
    
    except Exception as e:
        current_app.logger.error(f"Failed to send email: {str(e)}")
        return False


def send_verification_email(user, token):
    """Sends email verification with the new AOIN theme."""
    verification_link = f"{current_app.config['FRONTEND_URL']}/verify-email/{token}"
    
    template_content = """
        <p>Hello {{ name }},</p>
        <p>Thank you for registering with us. Please click the button below to verify your email address:</p>
        <div class="button-wrapper">
            <a href="{{ verification_link }}" class="button" target="_blank">Verify Email</a>
        </div>
        <p>Or copy and paste this link in your browser:</p>
        <p><a href="{{ verification_link }}" class="link">{{ verification_link }}</a></p>
        <p>This link will expire in 24 hours.</p>
        <p>If you did not register for an account, please ignore this email.</p>
        <p>Best regards,<br>The Team</p>
    """
    
    context = {
        'name': f"{user.first_name} {user.last_name}",
        'verification_link': verification_link,
        'heading': "Email Verification"
    }
    
    return send_email(
        user.email,
        "Verify Your Email Address for AOIN",
        template_content,
        context
    )

def send_password_reset_email(user, token):
    """Sends password reset email with the new AOIN theme."""
    reset_link = f"{current_app.config['FRONTEND_URL']}/password/reset?token={token}"
    
    template_content = """
        <p>Hello {{ name }},</p>
        <p>We received a request to reset your password. Click the button below to create a new password:</p>
        <div class="button-wrapper">
            <a href="{{ reset_link }}" class="button" target="_blank">Reset Password</a>
        </div>
        <p>Or copy and paste this link in your browser:</p>
        <p><a href="{{ reset_link }}" class="link">{{ reset_link }}</a></p>
        <p><strong>Important:</strong> This link will expire in 1 hour.</p>
        <p>If you did not request a password reset, please ignore this email.</p>
        <p>Best regards,<br>The Team</p>
    """
    
    context = {
        'name': f"{user.first_name} {user.last_name}",
        'reset_link': reset_link,
        'heading': "Password Reset Request"
    }
    
    return send_email(
        user.email,
        "Reset Your AOIN Password",
        template_content,
        context
    )

def send_merchant_docs_submitted_to_admin(merchant_profile, admin_email_list=None): 
    """Notifies admins of merchant document submission with the new AOIN theme."""
    from .utils import get_super_admin_emails 

    if admin_email_list is None: 
        admin_email_list = get_super_admin_emails()
    if not admin_email_list:
        return False

    merchant_user = merchant_profile.user 
    merchant_name = f"{merchant_user.first_name} {merchant_user.last_name}" if merchant_user else "N/A"
    admin_link = f"{current_app.config['FRONTEND_URL']}/superadmin/merchant-management" 

    template_content = """
        <p>Hello Admin,</p>
        <p>The merchant '<strong>{{ business_name }}</strong>' (User: {{ merchant_name }}) has submitted their documents for verification.</p>
        <p>Please review their submission in the admin panel:</p>
        <div class="button-wrapper">
            <a href="{{ admin_link }}" class="button" target="_blank">Review Documents</a>
        </div>
        <p>Or copy and paste this link into your browser:</p>
        <p><a href="{{ admin_link }}" class="link">{{ admin_link }}</a></p>
        <p>Thank you.</p>
    """
    context = {
        'business_name': merchant_profile.business_name,
        'merchant_name': merchant_name,
        'admin_link': admin_link,
        'heading': "Merchant Document Submission"
    }

    subject = f"Merchant Document Submission: {merchant_profile.business_name}"
    all_sent = True
    for admin_email in admin_email_list:
        if not send_email(admin_email, subject, template_content, context):
            all_sent = False
    return all_sent

def send_merchant_document_rejection_email(merchant_user, merchant_profile, document, admin_notes):
    """Notifies merchant of document rejection with the new AOIN theme."""
    merchant_dashboard_link = f"{current_app.config['FRONTEND_URL']}/business/verification" 
    
    template_content = """
        <p>Dear {{ user_name }},</p>
        <p>We are writing to inform you that your submitted document, <strong>{{ document_type }}</strong>, for your merchant profile '<strong>{{ business_name }}</strong>' has been rejected.</p>
        <p><strong>Reason for rejection:</strong></p>
        <p>{{ admin_notes }}</p>
        <p>Please log in to your merchant dashboard to review the details and upload the corrected document(s).</p>
        <div class="button-wrapper">
            <a href="{{ merchant_link }}" class="button" target="_blank">Go to Dashboard</a>
        </div>
        <p>If you have any questions, please contact our support team.</p>
        <p>Sincerely,<br>The Verification Team</p>
    """
    context = {
        'user_name': f"{merchant_user.first_name} {merchant_user.last_name}",
        'business_name': merchant_profile.business_name,
        'document_type': document.document_type.value.replace('_', ' ').title(),
        'admin_notes': admin_notes or "No specific reason provided. Please check your dashboard.",
        'merchant_link': merchant_dashboard_link,
        'heading': "Document Rejection Notice"
    }
    subject = f"Action Required: Document Rejected for {merchant_profile.business_name}"
    return send_email(merchant_user.email, subject, template_content, context)

def send_merchant_profile_rejection_email(merchant_user, merchant_profile, reason):
    """Notifies merchant of profile rejection with the new AOIN theme."""
    merchant_dashboard_link = f"{current_app.config['FRONTEND_URL']}/business/verification" 

    template_content = """
        <p>Dear {{ user_name }},</p>
        <p>We regret to inform you that your merchant profile '<strong>{{ business_name }}</strong>' has been rejected.</p>
        <p><strong>Reason for rejection:</strong></p>
        <p>{{ reason }}</p>
        <p>Please review the feedback and contact our support team if you have questions or wish to re-apply after addressing the issues.</p>
        <div class="button-wrapper">
            <a href="{{ merchant_link }}" class="button" target="_blank">Visit Dashboard</a>
        </div>
        <p>Sincerely,<br>The Verification Team</p>
    """
    context = {
        'user_name': f"{merchant_user.first_name} {merchant_user.last_name}",
        'business_name': merchant_profile.business_name,
        'reason': reason or "Please check your merchant dashboard for details or contact support.",
        'merchant_link': merchant_dashboard_link,
        'heading': "Merchant Profile Rejection"
    }
    subject = f"Important: Your Merchant Profile for {merchant_profile.business_name} was Rejected"
    return send_email(merchant_user.email, subject, template_content, context)

def send_merchant_profile_approval_email(merchant_user, merchant_profile):
    """Notifies merchant of profile approval with the new AOIN theme."""
    merchant_dashboard_link = f"{current_app.config['FRONTEND_URL']}/business/dashboard" 

    template_content = """
        <p>Dear {{ user_name }},</p>
        <p>Congratulations! We are pleased to inform you that your merchant profile '<strong>{{ business_name }}</strong>' has been successfully verified and approved.</p>
        <p>You can now access all merchant features and start managing your store.</p>
        <div class="button-wrapper">
            <a href="{{ merchant_link }}" class="button" target="_blank">Go to Your Dashboard</a>
        </div>
        <p>Welcome aboard!</p>
        <p>Sincerely,<br>The Team</p>
    """
    context = {
        'user_name': f"{merchant_user.first_name} {merchant_user.last_name}",
        'business_name': merchant_profile.business_name,
        'merchant_link': merchant_dashboard_link,
        'heading': "Merchant Profile Approved!"
    }
    subject = f"Congratulations! Your Merchant Profile for {merchant_profile.business_name} is Approved"
    return send_email(merchant_user.email, subject, template_content, context)