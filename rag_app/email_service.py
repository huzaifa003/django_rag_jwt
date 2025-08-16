import os
import secrets
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from .models import EmailVerificationToken, PasswordResetToken

def generate_secure_token():
    """Generate a cryptographically secure token"""
    return secrets.token_urlsafe(32)

def create_verification_token(user, expires_in_hours=24):
    """Create a new email verification token for a user"""
    # Delete any existing unused tokens for this user
    EmailVerificationToken.objects.filter(user=user, is_used=False).delete()
    
    # Create new token
    token = generate_secure_token()
    expires_at = timezone.now() + timedelta(hours=expires_in_hours)
    
    verification_token = EmailVerificationToken.objects.create(
        user=user,
        token=token,
        expires_at=expires_at
    )
    
    return verification_token

def send_verification_email(user, verification_token):
    """Send verification email to user"""
    try:
        # Create verification URL
        verification_url = f"{settings.FRONTEND_URL}/verify-email?token={verification_token.token}"
        
        # Email content
        subject = "Verify Your Email Address"
        
        # HTML email template
        html_message = render_to_string('email/verification_email.html', {
            'user': user,
            'verification_url': verification_url,
            'expires_at': verification_token.expires_at.strftime('%B %d, %Y at %I:%M %p'),
        })
        
        # Plain text fallback
        text_message = f"""
        Hello {user.first_name},
        
        Please verify your email address by clicking the link below:
        
        {verification_url}
        
        This link will expire on {verification_token.expires_at.strftime('%B %d, %Y at %I:%M %p')}.
        
        If you didn't create an account, please ignore this email.
        
        Best regards,
        Your App Team
        """
        
        # Send email
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        return True
        
    except Exception as e:
        print(f"Error sending verification email: {e}")
        return False

def verify_email_token(token):
    """Verify email token and update user status"""
    try:
        verification_token = EmailVerificationToken.objects.get(
            token=token,
            is_used=False
        )
        
        # Check if token is expired
        if verification_token.is_expired():
            return False, "Token has expired"
        
        # Mark token as used
        verification_token.is_used = True
        verification_token.save()
        
        # Update user email verification status
        user = verification_token.user
        user.email_verified = True
        user.save()
        
        return True, "Email verified successfully"
        
    except EmailVerificationToken.DoesNotExist:
        return False, "Invalid or already used token"
    except Exception as e:
        return False, f"Error verifying token: {str(e)}"

def create_password_reset_token(user, expires_in_hours=1):
    """Create a new password reset token for a user"""
    # Delete any existing unused tokens for this user
    PasswordResetToken.objects.filter(user=user, is_used=False).delete()
    
    # Create new token
    token = generate_secure_token()
    expires_at = timezone.now() + timedelta(hours=expires_in_hours)
    
    reset_token = PasswordResetToken.objects.create(
        user=user,
        token=token,
        expires_at=expires_at
    )
    
    return reset_token

def send_password_reset_email(user, reset_token):
    """Send password reset email to user"""
    try:
        # Create reset URL
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token.token}"
        
        # Email content
        subject = "Reset Your Password"
        
        # HTML email template
        html_message = render_to_string('email/password_reset_email.html', {
            'user': user,
            'reset_url': reset_url,
            'expires_at': reset_token.expires_at.strftime('%B %d, %Y at %I:%M %p'),
        })
        
        # Plain text fallback
        text_message = f"""
        Hello {user.first_name},
        
        You requested to reset your password. Click the link below to set a new password:
        
        {reset_url}
        
        This link will expire on {reset_token.expires_at.strftime('%B %d, %Y at %I:%M %p')}.
        
        If you didn't request a password reset, please ignore this email and your password will remain unchanged.
        
        Best regards,
        Your App Team
        """
        
        # Send email
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        return True
        
    except Exception as e:
        print(f"Error sending password reset email: {e}")
        return False

def verify_password_reset_token(token):
    """Verify password reset token"""
    try:
        reset_token = PasswordResetToken.objects.get(
            token=token,
            is_used=False
        )
        
        # Check if token is expired
        if reset_token.is_expired():
            return False, "Token has expired"
        
        return True, reset_token.user
        
    except PasswordResetToken.DoesNotExist:
        return False, "Invalid or already used token"
    except Exception as e:
        return False, f"Error verifying token: {str(e)}"

def use_password_reset_token(token):
    """Mark password reset token as used"""
    try:
        reset_token = PasswordResetToken.objects.get(
            token=token,
            is_used=False
        )
        
        # Mark token as used
        reset_token.is_used = True
        reset_token.save()
        
        return True
        
    except PasswordResetToken.DoesNotExist:
        return False
