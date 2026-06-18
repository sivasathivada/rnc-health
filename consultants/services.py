
from django.core.cache import cache
from django.db.models import Q, Avg
from django.db import transaction
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from PIL import Image
from io import BytesIO
import uuid
import logging
from .models import ConsultantAvailability, ConsultantProfile, ConsultantReview, Speciality

logger = logging.getLogger(__name__)


class ConsultantService:
    @staticmethod
    def get_consultants_queryset(
        search_query = None,
        speciality_id = None,
        is_online_only = False,
        is_available_only = True
    ):
        
        queryset = (
            ConsultantProfile.objects.select_related("user", "speciality")
            .prefetch_related('reviews')
            .filter(user__is_active=True, user__role= "consultant")
        )
        
        if is_available_only:
            queryset = queryset.filter(is_available=True)
            
        if search_query:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search_query)
                | Q(user__last_name__icontains=search_query)
                | Q(speciality__name__icontains=search_query)
            )
        if speciality_id:
            queryset = queryset.filter(speciality_id=speciality_id)
             
        if is_online_only:
            queryset = queryset.filter(user__is_online=True)
            
        queryset = queryset.order_by('-rating', '-total_consultation', '-created_at')
        
        logger.info(f"Consultant queryset count: {queryset.count()}")
        return queryset
    
    @staticmethod
    def get_consultant_details(consultant_id):
        cache_key = f"consultant_details_{consultant_id}"
        cached_data = None
        
        # Try to get from cache (non-critical if fails)
        try:
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data, None
        except Exception:
            pass  # Cache failure is non-critical, continue to DB
        
        try:
            consultant = ConsultantProfile.objects.select_related('user',
            'speciality').prefetch_related('reviews__patient',
            'available_slots').get(id = consultant_id, user__is_active = True,
            user__role = 'consultant', is_verified = True)
            
            # Try to cache for 10 minutes (non-critical if fails)
            try:
                cache.set(cache_key, consultant, timeout= 600)
            except Exception:
                pass  # Cache set is non-critical
            
            return consultant, None
        except ConsultantProfile.DoesNotExist:
            return None, " Consultant not found "
        except Exception as e:
            logger.error(f" Error getting consultant details: {str(e)}")
            return None, str(e)
        
  
    @staticmethod
    def create_consultant_profile(user, speciality_id, license_number, **additional_data):
        if user.role != 'consultant':
            return None, " User is not a consultant"
        
        try:
            speciality = Speciality.objects.get(id = speciality_id)
            profile = ConsultantProfile.objects.create(
                user = user, 
                speciality = speciality, 
                license_number = license_number,
                **additional_data
            )
            
            return profile, None
        except Speciality.DoesNotExist:
            return None, " Speciality not Found "
        except Exception as e:
            return None, str(e)
    
    @staticmethod
    @transaction.atomic
    def update_consultant_profile(user, profile_data):
        try:
            if user.role != 'consultant':
                return None, "User is not a consultant"
            profile = ConsultantProfile.objects.select_related('user').get(user = user)
            
            #Updated fields
            for field, value in profile_data.items():
                if hasattr(profile, field):
                    setattr(profile, field, value)
            
            profile.full_clean()
            profile.save()
        
        # clear cache (non-critical if fails)
            try:
                cache.delete(f"Consultant_details_{profile.id}")
                cache.delete(f"consultant_profile_{user.id}")
            except Exception:
                pass  # Cache clear is non-critical
            return profile, None
            
        except Exception as e:
            return None, str(e)
        
    @staticmethod
    def update_consultant_avatar(user, avatar_file):
        try:
            if user.role != 'consultant':
                return None, " User is not a consultant "
            
            profile = ConsultantProfile.objects.get(user = user)
            
            if profile.avatar:
                default_storage.delete(profile.avatar.name)
        
            #process and save new avatar
            file_path, error = ConsultantService.process_and_save_avatar(avatar_file, user.id)
            
            if error:
                return None, error
            
            profile.avatar = file_path
            profile.save(update_fields=['avatar'])
            
            try:
                cache.delete(f"Comnsultant_details_{profile.id}")
            except Exception:
                pass  # Cache clear is non-critical
            
            return profile, None
        except ConsultantProfile.DoesNotExist:
            return None, " Consultant not found"
                
        except Exception as e:
            return None, str(e)
            
    @staticmethod
    def process_and_save_avatar(avatar_file, user_id):
        try:
            image = Image.open(avatar_file)
            
            # Preserve EXIF orientation before any transforms
            try:
                from PIL import ImageOps
                image = ImageOps.exif_transpose(image)
            except Exception:
                pass
            
            if image.mode in ('RGBA', 'P', 'LA', 'L'):
                image = image.convert('RGB')
            image.thumbnail((512, 512), Image.Resampling.LANCZOS)
            
            output = BytesIO()
            image.save(output, format='JPEG', quality=85, optimize=True)
            output.seek(0)  # CRITICAL FIX: reset pointer to start before reading
            
            filename = f"consultants/avatars/{user_id}_{uuid.uuid4().hex[:8]}.jpg"
            
            file_path = default_storage.save(filename, ContentFile(output.read()))
            return file_path, None
        
        except Exception as e:
            logger.error(f"Consultant avatar processing failed: {str(e)}")
            return None, f"Failed to process image: {str(e)}"
                          
    @staticmethod
    def add_review(consultant_id, patient_user, rating, review_text = "", is_verified = False):
        try:
            if patient_user.role != 'patient':
                return None, "User is not a patient"
            
            consultant = ConsultantProfile.objects.select_related('user').get(id = consultant_id,
                        user__role = "consultant")
            
            review, created = ConsultantReview.objects.update_or_create(consultant = consultant,
                            patient = patient_user, defaults = {'rating' : rating,
                                    'review_text' : review_text, 'is_verified_consultation' : is_verified })
                
            # Update consultant's total review count
            consultant.total_reviews = consultant.reviews.count()
            consultant.save(update_fields=['total_reviews'])
        
            try:
                cache.delete(f"consultant_details_{consultant_id}")
            except Exception:
                pass  # Cache clear is non-critical
        
            return review, None
        except ConsultantProfile.DoesNotExist:
            return None, 'Consultant not found'

        except Exception as e:
            return None , str(e)
    
    @staticmethod
    def availability_schedule(user, schedule_data):
        """
        Save consultant availability slots to database
        - Validates all input data
        - Converts time strings to proper time objects
        - Saves all slots atomically
        - Returns detailed error messages
        """
        from datetime import datetime, time as time_obj
        
        try:
            # 1. VALIDATION: Check user is consultant
            if user.role != 'consultant':
                error_msg = "User is not a consultant"
                logger.error(f"Availability save failed: {error_msg}")
                return None, error_msg
            
            # 2. Get consultant profile
            profile = ConsultantProfile.objects.get(user=user)
            
            # 3. VALIDATION: Check if schedule_data is empty
            if not schedule_data or not isinstance(schedule_data, list):
                error_msg = "Schedule data must be a non-empty list"
                logger.error(f"Availability save failed: {error_msg} | Received: {schedule_data}")
                return None, error_msg
            
            # 4. VALIDATION: Pre-validate all slots before saving
            validated_slots = []
            for idx, item in enumerate(schedule_data):
                try:
                    # Parse day_of_week
                    day_of_week = item.get('day_of_week')
                    if day_of_week is None:
                        logger.warning(f"Slot {idx}: Missing day_of_week")
                        continue
                    
                    day_val = int(day_of_week)
                    if not (0 <= day_val <= 6):
                        logger.warning(f"Slot {idx}: Invalid day_of_week {day_val} (must be 0-6)")
                        continue
                    
                    # Parse start_time
                    start_time_raw = item.get('start_time')
                    if not start_time_raw:
                        logger.warning(f"Slot {idx}: Missing start_time")
                        continue
                    
                    # Convert start_time (string → time object)
                    if isinstance(start_time_raw, str):
                        try:
                            # Try parsing as "HH:MM:SS" or "HH:MM"
                            if len(start_time_raw.split(':')) == 3:
                                start_time = datetime.strptime(start_time_raw, '%H:%M:%S').time()
                            else:
                                start_time = datetime.strptime(start_time_raw, '%H:%M').time()
                        except ValueError as e:
                            logger.warning(f"Slot {idx}: Invalid start_time format '{start_time_raw}': {str(e)}")
                            continue
                    elif isinstance(start_time_raw, time_obj):
                        start_time = start_time_raw
                    else:
                        logger.warning(f"Slot {idx}: Unexpected start_time type {type(start_time_raw)}")
                        continue
                    
                    # Parse end_time
                    end_time_raw = item.get('end_time')
                    if not end_time_raw:
                        logger.warning(f"Slot {idx}: Missing end_time")
                        continue
                    
                    # Convert end_time (string → time object)
                    if isinstance(end_time_raw, str):
                        try:
                            if len(end_time_raw.split(':')) == 3:
                                end_time = datetime.strptime(end_time_raw, '%H:%M:%S').time()
                            else:
                                end_time = datetime.strptime(end_time_raw, '%H:%M').time()
                        except ValueError as e:
                            logger.warning(f"Slot {idx}: Invalid end_time format '{end_time_raw}': {str(e)}")
                            continue
                    elif isinstance(end_time_raw, time_obj):
                        end_time = end_time_raw
                    else:
                        logger.warning(f"Slot {idx}: Unexpected end_time type {type(end_time_raw)}")
                        continue
                    
                    # Validate time range
                    if start_time >= end_time:
                        logger.warning(f"Slot {idx}: start_time ({start_time}) must be before end_time ({end_time})")
                        continue
                    
                    # Parse is_active
                    is_active = item.get('is_active', True)
                    if not isinstance(is_active, bool):
                        is_active = str(is_active).lower() in ['true', '1', 'yes']
                    
                    # All validations passed - store the validated data
                    validated_slots.append({
                        'day_of_week': day_val,
                        'start_time': start_time,
                        'end_time': end_time,
                        'is_active': is_active,
                    })
                    logger.info(f"Slot {idx}: Validated - Day {day_val}, {start_time}-{end_time}, Active: {is_active}")
                    
                except Exception as e:
                    logger.error(f"Slot {idx}: Unexpected error during validation: {str(e)}", exc_info=True)
                    continue
            
            # 5. CHECK: Ensure we have valid slots to save
            if not validated_slots:
                error_msg = "No valid slots found after validation"
                logger.error(f"Availability save failed: {error_msg}")
                return None, error_msg
            
            # Check for overlapping slots on the same day
            slots_by_day = {}
            for slot in validated_slots:
                day = slot['day_of_week']
                if day not in slots_by_day:
                    slots_by_day[day] = []
                slots_by_day[day].append(slot)

            for day, slots in slots_by_day.items():
                slots.sort(key=lambda x: x['start_time'])
                for i in range(len(slots) - 1):
                    current_slot = slots[i]
                    next_slot = slots[i + 1]
                    if current_slot['end_time'] > next_slot['start_time']:
                        day_name = dict(ConsultantAvailability.DAY_CHOICES).get(day, f"day {day}")
                        error_msg = f"Overlapping availability slots detected on {day_name}: {current_slot['start_time'].strftime('%H:%M')}-{current_slot['end_time'].strftime('%H:%M')} and {next_slot['start_time'].strftime('%H:%M')}-{next_slot['end_time'].strftime('%H:%M')}."
                        logger.error(f"Availability save failed: {error_msg}")
                        return None, error_msg

            logger.info(f"Proceeding to save {len(validated_slots)} validated slots for consultant {profile.id}")
            
            # 6. ATOMIC SAVE: Delete old slots and create new ones
            with transaction.atomic():
                # Clear existing slots
                old_count = ConsultantAvailability.objects.filter(consultant=profile).count()
                ConsultantAvailability.objects.filter(consultant=profile).delete()
                logger.info(f"Deleted {old_count} existing availability slots")
                
                # Create new slots in batch
                created_slots = []
                for slot_data in validated_slots:
                    slot = ConsultantAvailability(
                        consultant=profile,
                        day_of_week=slot_data['day_of_week'],
                        start_time=slot_data['start_time'],
                        end_time=slot_data['end_time'],
                        is_active=slot_data['is_active'],
                    )
                    created_slots.append(slot)
                
                # Bulk create for efficiency
                ConsultantAvailability.objects.bulk_create(created_slots)
                logger.info(f"Successfully created {len(created_slots)} availability slots in database")
                
                # Update the JSON field on profile for redundancy
                # Convert time objects to ISO format strings for JSON serialization
                json_slots = []
                for slot in validated_slots:
                    json_slots.append({
                        'day_of_week': slot['day_of_week'],
                        'start_time': slot['start_time'].isoformat() if hasattr(slot['start_time'], 'isoformat') else str(slot['start_time']),
                        'end_time': slot['end_time'].isoformat() if hasattr(slot['end_time'], 'isoformat') else str(slot['end_time']),
                        'is_active': slot['is_active'],
                    })
                profile.availability_schedule = json_slots
                profile.save(update_fields=['availability_schedule'])
                logger.info(f"Updated consultant profile availability_schedule JSON field")
                
                # Generate actual AppointmentSlot entries from the recurring availability
                # This converts weekly patterns to actual calendar dates
                try:
                    from consultations.services import generate_appointment_slots_from_availability
                    slots_generated = generate_appointment_slots_from_availability(profile, days_ahead=60)
                    logger.info(f"Generated {slots_generated} appointment slots for next 60 days")
                except Exception as e:
                    logger.warning(f"Could not generate appointment slots (non-critical): {str(e)}")
                
                # Clear the consultant detail cache so frontend sees fresh data
                try:
                    cache_key = f"consultant_details_{profile.id}"
                    cache.delete(cache_key)
                    logger.info(f"Cleared cache for consultant {profile.id}")
                except Exception as cache_err:
                    logger.warning(f"Cache clear failed (non-critical): {str(cache_err)}")
            
            # 7. VERIFICATION: Query database to confirm all saved
            final_count = ConsultantAvailability.objects.filter(consultant=profile).count()
            logger.info(f"DATABASE VERIFICATION: {final_count} slots confirmed in database")
            
            return profile, None

        except ConsultantProfile.DoesNotExist:
            error_msg = "Consultant profile not found for this user"
            logger.error(f"Availability save failed: {error_msg}")
            return None, error_msg
            
        except Exception as e:
            error_msg = f"Database error during availability save: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return None, error_msg