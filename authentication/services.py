from symtable import Class
from django.contrib.auth import  get_user_model
from django.contrib.auth import  authenticate
from django.contrib.messages import success
from django.core.cache import  cache
from django.core.serializers import serialize
from django.utils import  timezone
from rest_framework.fields import get_attribute
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import  TokenError, InvalidToken
from .models import  User, EmailVerificationToken
from consultants.models import  ConsultantProfile
import  uuid
import  logging
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import send_mail


User = get_user_model()
logger = logging.getLogger(__name__)

class AuthenticationService:
    @staticmethod
    def register_user(email, password, first_name, last_name, role = 'patient'):
        try:
            if User.objects.filter(email = email).exists():
                return  None, " User with this email already exists"
            
            user = User.objects.create_user(email = email, password = password,    
            first_name = first_name, last_name = last_name, role = role)      # creates the instance
            
            if role == 'consultant':
                ConsultantProfile.objects.create(user=user)  # passes the instance

            logger.info(f"User Registered Successfully : {email} with role {role}")
            return  user, None
        
        except Exception as e:
            logger.error(f"Registration failed for {email}: {str(e)}")
            return None, str(e)

    @staticmethod
    def authenticate_user(email, password):
        try:
            user = authenticate(email = email , password = password)
            if user:
                if not user.is_active:
                    return None, " User account is deactivated "
                refresh = RefreshToken.for_user(user)

                user.last_seen =  timezone.now()
                user.save(update_fields=['last_seen'])

                logger.info(f"User authenticated successfully : {email} with role {refresh.access_token}")

                return {
                    'user' : user,
                    'access_token' : str(refresh.access_token),
                     'refresh_token' : str(refresh),
                     }, None
            else:
                logger.warning(f" Authentication failed for : {email}")
                return  None, " Invalid Credentials "
        except Exception as e:
             logger.warning(f"Authentication failed for : {email} : {str(e)}")
             return  None, f"Authentication failed : {str(e)}"

    @staticmethod
    def update_user_status(user, is_online=True):
        try:
            user.is_online = is_online
            user.last_seen = timezone.now()
            user.save(update_fields=['is_online', 'last_seen'])

            cache_key = f"user_status_{user.id}"
            cache.set(cache_key, {
                'is_online': is_online,
                'last_seen': user.last_seen.isoformat()

            }, timeout=3600)

            logger.debug(f"Updated user status for {user.email}: online = {is_online}")

        except Exception as e:
            (logger.error(f"Failed to update user status for {user.email} : {str(e)}"))


class EmailVerificationService:
    @staticmethod
    def send_verification_email(user):
        try:
            from .tasks import send_verification_email_task
            send_verification_email_task.delay(user.id)
            logger.info(f"Enqueued verification email task for {user.email}")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue verification email task for {user.email} : {str(e)}")
            return False

    @staticmethod
    def verify_email_token(token):
        try:
            verification_token = EmailVerificationToken.objects.get(token = token)

            if not verification_token.is_valid:
                if verification_token.is_expired:
                    return  None, "Verification link has expired"
                else:
                    return None, "verification link has already been used"

            verification_token.is_used = True
            verification_token.save()

            user = verification_token.user
            user.mark_email_verified()

            logger.info(f" Email verified successfully for user: {user.email}")
            return user, None
        except EmailVerificationToken.DoesNotExist:
            logger.warning(f"Invalid verification token: {token}")
            return None, "Invalid verification link"
        except Exception as e:
            logger.error(f"Email verification failed for {token} : {str(e)}")
            return None, f"Verification failed : {str(e)}"
    

    @staticmethod
    def resend_verification_email(user):
        if user.is_verified:
            return False, "Email is already verified"

        recent_tokens = EmailVerificationToken.objects.filter(user = user, created_at__gte = timezone.now() - timezone.timedelta(minutes = 5)).count()

        if recent_tokens >= 3:
            return False, "Too many verification emails send. Please wait before requesting another."

        success = EmailVerificationService.send_verification_email(user)
        if success:
            return True, "Verification email sent successfully"
        else:
            return False, "Failed to send Verification email"