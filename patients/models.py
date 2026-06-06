from django.db import models

# Create your models here.



from django.db import models
#from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator
from django.utils import timezone
import uuid
from django.conf import settings

#User = get_user_model()



class PatientProfile(models.Model):
    ''' Patient-specific profile information '''
    
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('others', 'Other'),
        ('prefer_not_to_say', 'm Prefer not to say'),
        
    ]
    
    BLOOD_TYPE_CHOICES =[
        ('A+', 'A Positive'),
        ('A-', 'A Negative'),
        ('B+', 'B Positive'),
        ('B-', 'B Negative'),
        ('AB+', 'AB Positive'),
        ('AB-', 'AB Negative'),
        ('O+', 'O Positive'),
        ('O-', 'O Negative'),
        ('unknown', 'Unknown'),
        
    ]
    
    id = models.UUIDField(primary_key= True, default=uuid.uuid4, editable=False)
    #user = models.OneToOneField(User,  on_delete=models.CASCADE,
    user = models.OneToOneField(
    settings.AUTH_USER_MODEL,
    on_delete=models.CASCADE,
    related_name='patient_profile',
    limit_choices_to={'role': 'patient'}
   
   )
   
    avatar = models.ImageField(upload_to= 'patients/avatars/', blank=True, null = True)
    bio = models.TextField(max_length = 500, blank = True)
    date_of_birth = models.DateTimeField(blank = True, null = True)
    gender = models.CharField(max_length=20, choices = GENDER_CHOICES, blank=True)

    phone_regex = RegexValidator(
        regex = r'^\+?1?\d{9,15}$',
        message = " Phone number must be entered in format: + '99999999' , Up to 15 digits allowed." 
    )
    
    phone_number = models.CharField(validators=[phone_regex], max_length=16, blank=True)
    address = models.TextField(max_length=300, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = models.CharField(validators=[phone_regex], max_length=17, blank=True)
    emergency_contact_relationship = models.CharField(max_length=50, blank = True)
    
     
    blood_type = models.CharField(max_length=10, choices=BLOOD_TYPE_CHOICES, blank =True)
    allergies = models.JSONField(default=list, blank=True, help_text='list of allergies')
    chronic_conditions = models.JSONField(default=list, blank=True, help_text='list of chronic  conditions')
    current_medications = models.JSONField(default=list, blank=True, help_text= 'list of current medications')
    medical_notes = models.TextField(blank=True, help_text='Additional medical information')
    
    share_medical_history = models.BooleanField(default=True)
    allow_emergency_access = models.BooleanField(default=True)
    preferred_language = models.CharField(max_length=10, default='en')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'patient_profiles'
        verbose_name = 'Patient Profile'
        verbose_name_plural = "Patient Profiles"
        indexes = [
            models.Index(fields = ['user']),
            models.Index(fields=['created_at']),
            
        ]
    
    def __str__(self):
       return f"{self.user.full_name} - Patient Profile"
       
    @property
    def avatar_url(self):
        if self.avatar:
           return self.avatar.url
        return None
        
    @property
    def age(self):
        if self.date_of_birth:
            today = timezone.now().date()
            return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        return None
        
    def clean(self):
        if self.user and self.user.role != 'patient':
            from django.core.exceptions import ValidationError
            raise ValidationError("User must have 'patient' role")
            
class PatientMedicalHistory(models.Model):
    ''' detailed medical history records for patients'''
    
    RECORD_TYPE_CHOICES = [
        ('diagnosis', 'Diagnosis'),
        ('procedure', 'Medical Procedure'),
        ('surgery', 'Surgery'),
        ('hospitalization', 'Hospitalization'),
        ('vaccination', 'Vaccination'),
        ('test_result', 'Test Result'),
        ('other', 'Other'),
        
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name= 'medical_history')
    
    record_type = models.CharField(max_length=20, choices= RECORD_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    date_occurred = models.DateField()
    healthcare_provider = models.CharField(max_length=200, blank=True)
    
    attachments = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'patient_medical_history'
        ordering = ['-date_occurred', '-created_at']
        verbose_name = 'Patient Medical History'
        verbose_name_plural = "Patient Medical History"
        
    
    def __str__(self):
        return f"{self.patient.user.full_name} - {self.title}"
        
  