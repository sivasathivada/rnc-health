from django.contrib.auth import get_user_model
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.utils import timezone
import uuid



User = get_user_model()


class Speciality(models.Model):
    ''' Medical specialities '''

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = 'specialities'
        db_table = 'specialities'
        ordering = ['name']
        
    def __str__(self):
        return self.name
    
class ConsultantProfile(models.Model):
    ''' Consultant-specific profile information  '''
    
    CONSULTATION_TYPE_CHOICES = [
        ('video', 'Video Consultant'),
        ('audio', 'Audio Only'),
        ('chat', ' Text Chat'),
        ('all', 'All Types'),
        
    ]
    id = models.UUIDField(primary_key= True, default= uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name ='consultant_profile', limit_choices_to= {'role' : 'consultant'})
    speciality = models.ForeignKey(Speciality, on_delete=models.PROTECT, null=True,blank=True, related_name='consultants')
    
    avatar = models.ImageField(upload_to = 'consultants/avatars/', blank= True, null = True)
    bio = models.TextField(max_length=100, blank=True)
    years_of_experience = models.PositiveBigIntegerField(default=0, validators=[MaxValueValidator(50)])
    
    license_number = models.CharField(max_length=100, unique = True, null=True, blank=True)
    medical_degree = models.CharField(max_length=200, blank=True)
    board_certifications = models.JSONField(default=list, blank=True )
    additional_qualifications = models.JSONField(default=list, blank=True)
    
    phone_regex = RegexValidator(
        regex = r'^\+?1?\d{9,15}$',
        message = " Phone number must be entered in format: '+ 99999999' , Up to 15 digits allowed." 
    )      
    
    #contact details
    phone_number = models.CharField(validators=[phone_regex], max_length=17, blank=True)
    clinic_name = models.CharField(max_length=200, blank=True)
    clinic_address = models.TextField(max_length=300, blank=True)
    clinic_city = models.CharField(max_length=100, blank=True)
    clinic_country = models.CharField(max_length = 100, blank=True)
    
    #professional details
    consultation_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0)]
    )
    consultation_duration = models.PositiveIntegerField(
        default=30,
        help_text='default consultaion duration in minutes')

    consultation_types = models.CharField(
        max_length=10,
        choices= CONSULTATION_TYPE_CHOICES,
        default= 'all'
    )

    # languages
    languages_spoken = models.JSONField(default=list, blank=True)

    #Available Schedule
    is_available = models.BooleanField(default=True)
    availability_schedule = models.JSONField(
        default=dict,
        blank=True,
        help_text='Weekly Schedule with in time slots '
    )

    # Statistics
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )

    total_consultation = models.PositiveIntegerField(default=0)
    total_reviews = models.PositiveIntegerField(default=0)


    is_verified = models.BooleanField(default=False)
    verification_date = models.DateTimeField(blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'consultant_profiles'
        verbose_name = 'Consultant Profile'
        verbose_name_plural = 'Consultant Profiles'
        indexes = [
            models.Index(fields= ['user']),
            models.Index(fields= ['speciality']),
            models.Index(fields= ['is_verified', 'is_available']),
            models.Index(fields= ['created_at']),
            models.Index(fields= ['rating']),
        
        ]
        
    def __str__(self):
        
        return f'Dr. {self.user.full_name} - {self.speciality.name if self.speciality else "No Speciality"}'
    
    @property
    def avatar_url(self):
        if self.avatar:
            return self.avatar.url
        return None
    
    def verify_consultant(self):
        ''' Mark Consultant as verified'''

        self.is_verified = True
        self.verification_date = timezone.now()
        self.save(update_fields=['is_verified', 'verification_date'])
        
    def update_rating(self):
        from django.db.models import Avg
        result = self.reviews.aggregate(rating_avg=Avg('rating'))
        avg_rating = result['rating_avg']
    
        '''avg_rating = self.reviews.aggregate(Avg('rating'))['rating__avg']'''
        
        if avg_rating:
            self.rating = round(avg_rating, 2)
            self.save(update_fields=['rating'])
     
    def clean(self):
        if self.user and self.user.role != 'consultant':
            from django.core.exceptions import ValidationError
            raise ValidationError(" User must have 'consultant' role")
        
class ConsultantReview(models.Model):
    """ Reviews and ratings for consultants"""
                   
    RATING_CHOICES = [(i, f"{i} star{'s' if i !=1 else '' }") for i in range(1, 6)]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consultant = models.ForeignKey(ConsultantProfile, on_delete=models.CASCADE, related_name='reviews')
    patient = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to= {'role' : 'patient'})
    
    rating = models.IntegerField(choices=RATING_CHOICES)
    review_text = models.TextField(max_length=100, blank=True)
    
    is_verified_consultation = models.BooleanField(default=False)
    is_anonymous = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'consultant_reviews'
        unique_together = ['consultant', 'patient']
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['consultant', 'rating']),
            models.Index(fields=['created_at']),
        
        ]  
        
    def __str__(self):
        patient_name = 'Anonymous' if self.is_anonymous else self.patient.full_name
        return f"{patient_name} -> Dr. {self.consultant.user.full_name} ({self.rating} *)"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.consultant.update_rating()
        
class ConsultantAvailability(models.Model):
    ''' Specific availability slots for consultants '''
    
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
        
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consultant = models.ForeignKey(ConsultantProfile, on_delete=models.CASCADE, related_name='availability_slots')
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'consultant_availability'
        unique_together = ['consultant', 'day_of_week', 'start_time']
        ordering = ['day_of_week', 'start_time']
        
    def __str__(self):
        return f"Dr. {self.consultant.user.full_name} - {self.get_day_of_week_display()} {self.start_time}-{self.end_time}"
    