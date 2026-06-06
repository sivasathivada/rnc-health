
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import  get_user_model
import  logging

User = get_user_model()

logger = logging.getLogger(__name__)

@receiver(post_save, sender = User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        try:
            if instance.role == 'patient':
                from patients.models import PatientProfile
                PatientProfile.objects.create(user = instance)
                logger.info(f"Created patient profile for user {instance.id}")
            elif instance.role == 'consultant':
                from consultants.models import ConsultantProfile
                logger.info(
                    f"Created consultant profile for user {instance.id} - profile will be created when speciality is assigned"
                )

        except Exception as e:
            logger.error(f" Error creating profile for user {instance.id}: {str(e)}")
