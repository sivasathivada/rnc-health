from celery import shared_task
from django.contrib.auth import get_user_model
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import send_mail
import logging

from .models import EmailVerificationToken

User = get_user_model()
logger = logging.getLogger(__name__)

@shared_task(name="authentication.tasks.send_verification_email_task")
def send_verification_email_task(user_id):
    """Celery task to send email verification asynchronously"""
    try:
        user = User.objects.get(id=user_id)
        
        # Deactivate previous unused verification tokens
        EmailVerificationToken.objects.filter(user=user, is_used=False).update(is_used=True)
        
        # Create a new verification token
        verification_token = EmailVerificationToken.objects.create(user=user)
        
        subject = f"Verify your email - {getattr(settings, 'APP_NAME', 'Rnchealth App')}"
        
        verification_url = f"{getattr(settings, 'DOMAIN_URL', 'http://127.0.0.1:8000')}/api/auth/verify-email-page/{verification_token.token}"
        
        html_message = render_to_string('emails/email_verification.html', {
            'user': user,
            'verification_url': verification_url,
            'app_name': getattr(settings, 'APP_NAME', 'Rnchealth app')
        })
        
        plain_message = f"""
        Hi {user.first_name},
        Thank you for signing up for {getattr(settings, 'APP_NAME', 'Rnchealth App')}! 
        Please verify your email address by clicking the link below :
        {verification_url}
        This link will expire in 24 hours.
        
        If you didn't create an account, please ignore this email.
         
        Best regards,
        The Healthapp team
        """
        
        send_mail(
            subject=subject,
            message=plain_message,
            html_message=html_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@rnchealthlive.onrender.com'),
            recipient_list=[user.email],
            fail_silently=False
        )
        
        logger.info(f"Verification email sent via Celery task to {user.email}")
        return True
    except User.DoesNotExist:
        logger.error(f"Cannot send verification email: User with id {user_id} does not exist.")
        return False
    except Exception as e:
        logger.error(f"Failed to send verification email to user {user_id} in Celery task: {str(e)}")
        return False
