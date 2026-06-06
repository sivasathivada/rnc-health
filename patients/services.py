
from django.db.models import Q, Count
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError, NotFound
import uuid
from django.core.cache import cache
from PIL import Image
from io import BytesIO
import logging

from .models import PatientProfile, PatientMedicalHistory

logger = logging.getLogger(__name__)



class PatientProfileService:
    """Service class for managing patient profiles"""
    
    @staticmethod
    def get_patient_by_id(patient_id):
        """
        Retrieve a single patient by ID.
        
        Args:
            patient_id: UUID of the patient
            
        Returns:
            PatientProfile instance
            
        Raises:
            PatientProfile.DoesNotExist: If patient not found
        """
        try:
            return PatientProfile.objects.select_related('user').get(id=patient_id)
        except PatientProfile.DoesNotExist:
            raise NotFound(detail="Patient profile not found")
    
    @staticmethod
    def get_patient_by_user(user):
        """
        Retrieve patient profile for a specific user.
        
        Args:
            user: User instance
            
        Returns:
            PatientProfile instance
            
        Raises:
            PatientProfile.DoesNotExist: If patient profile doesn't exist for user
        """
        try:
            return PatientProfile.objects.select_related('user').get(user=user)
        except PatientProfile.DoesNotExist:
            raise NotFound(detail="Patient profile not found for this user")
    
    @staticmethod
    def get_all_patients():
        """
        Retrieve all patient profiles.
        
        Returns:
            QuerySet of all PatientProfile instances
        """
        return PatientProfile.objects.select_related('user').all()
    
    @staticmethod
    def get_patients_for_user(user):
        """
        Get patients accessible by the user (respects permissions).
        
        Args:
            user: Authenticated user instance
            
        Returns:
            QuerySet of patients accessible to user
        """
        # If user is a patient, they can only see their own profile
        if hasattr(user, 'patient_profile'):
            return PatientProfile.objects.filter(user=user).select_related('user')
        
        # If user is admin/consultant, they can see all patients
        if user.is_staff or hasattr(user, 'consultant_profile'):
            return PatientProfile.objects.all().select_related('user')
        
        return PatientProfile.objects.none()
    
    @staticmethod
    def create_patient_profile(user, validated_data):
        """
        Create a new patient profile for a user.
        
        Args:
            user: User instance (must have 'patient' role)
            validated_data: Dictionary of validated data
            
        Returns:
            Created PatientProfile instance
            
        Raises:
            ValidationError: If user already has profile or doesn't have patient role
        """
        if hasattr(user, 'patient_profile'):
            raise ValidationError(detail="Patient profile already exists for this user")
        
        if user.role != 'patient':
            raise ValidationError(detail="Only users with 'patient' role can create a patient profile")
        
        patient_profile, created = PatientProfile.objects.create(user=user, **validated_data)
        
        if created:
            logger.info(f"Created new patients profile for users{user.id}")
        
        return patient_profile

    
    @staticmethod
    def update_patient_profile(patient, validated_data):
        """
        Update an existing patient profile.
        
        Args:
            patient: PatientProfile instance to update
            validated_data: Dictionary of validated data
            
        Returns:
            Updated PatientProfile instance
        """
        for field, value in validated_data.items():
            setattr(patient, field, value)
        
        patient.full_clean()
        patient.save()
        return patient
    
    @staticmethod
    def delete_patient_profile(patient):
        """
        Delete a patient profile and associated data.
        
        Args:
            patient: PatientProfile instance to delete
        """
        patient_id = patient.id
        patient.delete()
        return {"message": f"Patient profile {patient_id} deleted successfully"}
    
    @staticmethod
    def update_patient_avatar(patient, avatar_file):
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        from PIL import Image
        from io import BytesIO
        import uuid
        try:
            if patient.avatar:
                try:
                    default_storage.delete(patient.avatar.name)
                except Exception:
                    pass
            
            # Process and save new avatar
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
            
            filename = f"patients/avatars/{patient.user.id}_{uuid.uuid4().hex[:8]}.jpg"
            file_path = default_storage.save(filename, ContentFile(output.read()))
            
            patient.avatar = file_path
            patient.save(update_fields=['avatar'])
            return patient, None
        except Exception as e:
            logger.error(f"Patient avatar update failed: {str(e)}")
            return None, str(e)
            
    @staticmethod
    def get_patient_summary(patient):
        """
        Get a summary of patient profile.
        
        Args:
            patient: PatientProfile instance
            
        Returns:
            Dictionary containing patient summary
        """
        summary_data = {
            'id': patient.id,
            'user': patient.user.full_name if patient.user else None,
            'email': patient.user.email if patient.user else None,
            'age': patient.age,
            'gender': patient.gender,
            'blood_type': patient.blood_type,
            'allergies': patient.allergies,
            'chronic_conditions': patient.chronic_conditions,
            'current_medications': patient.current_medications,
            'medical_records_count': patient.medical_history.count(),
            'avatar_url': patient.avatar_url,
            'created_at': patient.created_at,
            'updated_at': patient.updated_at,
        }
        return summary_data


# MEDICAL HISTORY SERVICE

class PatientMedicalHistoryService:
    """Service class for managing patient medical history"""
    
    @staticmethod
    def get_medical_record_by_id(record_id):
        """
        Retrieve a single medical history record by ID.
        
        Args:
            record_id: UUID of the medical record
            
        Returns:
            PatientMedicalHistory instance
            
        Raises:
            PatientMedicalHistory.DoesNotExist: If record not found
        """
        try:
            return PatientMedicalHistory.objects.select_related('patient__user').get(id=record_id)
        except PatientMedicalHistory.DoesNotExist:
            raise NotFound(detail="Medical record not found")
    
    @staticmethod
    def get_all_medical_records():
        """
        Retrieve all medical history records.
        
        Returns:
            QuerySet of all PatientMedicalHistory instances
        """
        return PatientMedicalHistory.objects.select_related('patient__user').all()
    
    @staticmethod
    def get_medical_records_for_user(user):
        """
        Get medical records accessible by the user (respects permissions).
        
        Args:
            user: Authenticated user instance
            
        Returns:
            QuerySet of medical records accessible to user
        """
        # If user is a patient, they can only see their own records
        if hasattr(user, 'patient_profile'):
            return PatientMedicalHistory.objects.filter(
                patient=user.patient_profile
            ).select_related('patient__user')
        
        # If user is admin/consultant, they can see all records
        if user.is_staff or hasattr(user, 'consultant_profile'):
            return PatientMedicalHistory.objects.all().select_related('patient__user')
        
        return PatientMedicalHistory.objects.none()
    
    @staticmethod
    def get_patient_medical_history(patient):
        """
        Get all medical history records for a specific patient.
        
        Args:
            patient: PatientProfile instance
            
        Returns:
            QuerySet of medical records for the patient
        """
        return PatientMedicalHistory.objects.filter(
            patient=patient
        ).select_related('patient__user').order_by('-date_occurred')
    
    @staticmethod
    def create_medical_record(patient, validated_data):
        """
        Create a new medical history record.
        
        Args:
            patient: PatientProfile instance
            validated_data: Dictionary of validated data
            
        Returns:
            Created PatientMedicalHistory instance
        """
        medical_record = PatientMedicalHistory.objects.create(
            patient=patient,
            **validated_data
        )
        return medical_record
    
    @staticmethod
    def update_medical_record(record, validated_data):
        """
        Update an existing medical history record.
        
        Args:
            record: PatientMedicalHistory instance to update
            validated_data: Dictionary of validated data
            
        Returns:
            Updated PatientMedicalHistory instance
        """
        for field, value in validated_data.items():
            setattr(record, field, value)
        
        record.save()
        return record
    
    @staticmethod
    def delete_medical_record(record):
        """
        Delete a medical history record.
        
        Args:
            record: PatientMedicalHistory instance to delete
        """
        record_id = record.id
        record.delete()
        return {"message": f"Medical record {record_id} deleted successfully"}
    
    @staticmethod
    def get_medical_records_by_type(patient, record_type):
        """
        Get medical records filtered by record type.
        
        Args:
            patient: PatientProfile instance
            record_type: String representing the record type
            
        Returns:
            QuerySet of filtered medical records
        """
        return PatientMedicalHistory.objects.filter(
            patient=patient,
            record_type=record_type
        ).select_related('patient__user').order_by('-date_occurred')
    
    @staticmethod
    def get_all_medical_records_by_type(record_type):
        """
        Get all medical records of a specific type (admin view).
        
        Args:
            record_type: String representing the record type
            
        Returns:
            QuerySet of medical records of the type
        """
        return PatientMedicalHistory.objects.filter(
            record_type=record_type
        ).select_related('patient__user').order_by('-date_occurred')
    
    @staticmethod
    def get_recent_medical_records(patient, limit=10):
        """
        Get recent medical records for a patient.
        
        Args:
            patient: PatientProfile instance
            limit: Maximum number of records to return (default: 10)
            
        Returns:
            List of recent medical records
        """
        return PatientMedicalHistory.objects.filter(
            patient=patient
        ).select_related('patient__user').order_by('-date_occurred')[:limit]


# PATIENT STATISTICS SERVICE

class PatientStatisticsService:
    """Service class for patient and medical statistics"""
    
    @staticmethod
    def get_platform_statistics():
        """
        Get overall platform statistics.
        
        Returns:
            Dictionary containing comprehensive statistics
        """
        total_patients = PatientProfile.objects.count()
        total_records = PatientMedicalHistory.objects.count()
        
        # Records by type
        records_by_type = {}
        for choice_value, choice_label in PatientMedicalHistory.RECORD_TYPE_CHOICES:
            count = PatientMedicalHistory.objects.filter(record_type=choice_value).count()
            records_by_type[choice_label] = count
        
        # Average medical records per patient
        avg_records = total_records / total_patients if total_patients > 0 else 0
        
        stats = {
            'total_patients': total_patients,
            'total_medical_records': total_records,
            'average_records_per_patient': round(avg_records, 2),
            'records_by_type': records_by_type,
            'timestamp': timezone.now(),
        }
        
        return stats
    
    @staticmethod
    def get_patient_statistics(patient):
        """
        Get statistics for a specific patient.
        
        Args:
            patient: PatientProfile instance
            
        Returns:
            Dictionary containing patient-specific statistics
        """
        medical_records = patient.medical_history.all()
        
        # Count records by type
        records_by_type = {}
        for choice_value, choice_label in PatientMedicalHistory.RECORD_TYPE_CHOICES:
            count = medical_records.filter(record_type=choice_value).count()
            if count > 0:
                records_by_type[choice_label] = count
        
        stats = {
            'patient_id': patient.id,
            'total_records': medical_records.count(),
            'records_by_type': records_by_type,
            'oldest_record': medical_records.order_by('date_occurred').first().date_occurred if medical_records.exists() else None,
            'newest_record': medical_records.order_by('-date_occurred').first().date_occurred if medical_records.exists() else None,
        }
        
        return stats


# PATIENT SEARCH SERVICE 

class PatientSearchService:
    """Service class for patient search functionality"""
    
    @staticmethod
    def search_patients(query):
        """
        Search patients by name, email, phone number, or city.
        
        Args:
            query: Search string (minimum 2 characters recommended)
            
        Returns:
            QuerySet of matching PatientProfile instances
            
        Raises:
            ValidationError: If query is empty
        """
        if not query or not query.strip():
            raise ValidationError(detail="Please provide a search query")
        
        query = query.strip()
        
        patients = PatientProfile.objects.filter(
            Q(user__full_name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(phone_number__icontains=query) |
            Q(city__icontains=query)
        ).select_related('user').distinct()
        
        return patients
    
    @staticmethod
    def search_medical_records(query):
        """
        Search medical records by title, description, or healthcare provider.
        
        Args:
            query: Search string
            
        Returns:
            QuerySet of matching PatientMedicalHistory instances
            
        Raises:
            ValidationError: If query is empty
        """
        if not query or not query.strip():
            raise ValidationError(detail="Please provide a search query")
        
        query = query.strip()
        
        records = PatientMedicalHistory.objects.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(healthcare_provider__icontains=query)
        ).select_related('patient__user').distinct()
        
        return records
    
    @staticmethod
    def get_patients_by_blood_type(blood_type):
        """
        Get all patients with a specific blood type.
        
        Args:
            blood_type: Blood type string (e.g., 'A+', 'O-')
            
        Returns:
            QuerySet of patients with the specified blood type
        """
        return PatientProfile.objects.filter(
            blood_type=blood_type
        ).select_related('user')
    
    @staticmethod
    def get_patients_with_allergy(allergy):
        """
        Get all patients with a specific allergy.
        
        Args:
            allergy: Allergy name
            
        Returns:
            QuerySet of patients with the allergy
        """
        return PatientProfile.objects.filter(
            allergies__contains=allergy
        ).select_related('user')
    
    @staticmethod
    def get_patients_by_age_range(min_age, max_age):
        """
        Get patients within a specific age range.
        
        Args:
            min_age: Minimum age
            max_age: Maximum age
            
        Returns:
            List of patients within age range
        """
        patients = PatientProfile.objects.select_related('user').all()
        
        filtered_patients = [
            p for p in patients 
            if p.age and min_age <= p.age <= max_age
        ]
        
        return filtered_patients
