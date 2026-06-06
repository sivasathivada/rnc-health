from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import ConsultantReview
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender= ConsultantReview)
def update_consultant_rating_on_review_save(sender, instance, created, **kwargs):
    """" Update consultant rating when review is saved """
    
    try:
        instance.consultant.update_rating()
    except Exception as e:
        logger.error(f" Error updating consultant rating: {str(e)}")
        
@receiver(post_delete, sender=ConsultantReview)
def update_consultant_rating_on_review_delete(sender, instance, **kwargs):
    """ Update consultant rating when review is deleted """
    
    try:
        instance.consultant.update_rating()
        instance.consultant.total_reviews = instance.consultant.reviews.count()
        instance.consultant.save(update_fields = ['total_reviews'])
        
    except Exception as e:
        logger.error(f" Error Updating consultant rating on deletion: {str(e)}")