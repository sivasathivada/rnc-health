#from dis import specialized
#from email.policy import default

from django.template.context_processors import request
from rest_framework import  serializers
from django.contrib.auth import get_user_model
from .models import ConsultantProfile, ConsultantReview, ConsultantAvailability, Speciality
from authentication.serializers import  UserSerializer

User = get_user_model()

class SpecialitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Speciality
        fields = ['id', 'name', 'description','icon']

'''
class ConsultantAvailabilitySerializer(serializers.ModelSerializer):
    
    day_name = serializers.CharField( source = 'get_day_of_week_display', read_only = True)

    class Meta:
        model = ConsultantAvailability
        fields = ['id', 'day_of_week', 'day_name', 'start_time', 'end_time']
   
    def validate(self, attrs):
        # If 'day_name' somehow slipped into attrs, remove it 
        # so it doesn't get passed to the model constructor
        attrs.pop('day_name', None)
        return attrs 
    '''
    
class ConsultantAvailabilitySerializer(serializers.ModelSerializer):
    # Change this from CharField to SerializerMethodField
    day_name = serializers.SerializerMethodField()
    start_time = serializers.TimeField(format='%H:%M:%S')
    end_time = serializers.TimeField(format='%H:%M:%S')

    class Meta:
        model = ConsultantAvailability
        fields = ['id', 'day_of_week','day_name','start_time', 'end_time', "is_active"]

    def get_day_name(self, obj):
        # This calls the built-in Django 'get_FOO_display' method
        return obj.get_day_of_week_display()
    
    def to_representation(self, instance):
        """Convert time objects to strings for JSON serialization"""
        data = super().to_representation(instance)
        # Ensure time fields are strings
        if hasattr(instance.start_time, 'isoformat'):
            data['start_time'] = instance.start_time.isoformat()
        if hasattr(instance.end_time, 'isoformat'):
            data['end_time'] = instance.end_time.isoformat()
        return data
    
    def validate(self, attrs):
        """
        Validate availability slot data:
        - day_of_week must be 0-6
        - start_time must be before end_time
        """
        if 'day_of_week' in attrs:
            day = attrs['day_of_week']
            if not isinstance(day, int) or not (0 <= day <= 6):
                raise serializers.ValidationError({
                    'day_of_week': f"day_of_week must be an integer between 0-6 (0=Monday, 6=Sunday), got {day}"
                })
        
        if 'start_time' in attrs and 'end_time' in attrs:
            start = attrs['start_time']
            end = attrs['end_time']
            
            if start >= end:
                raise serializers.ValidationError({
                    'time_range': f"start_time ({start}) must be before end_time ({end})"
                })
        
        return attrs
    
    
class ConsultantReviewSerializer(serializers.ModelSerializer):
    patient_name = serializers.SerializerMethodField()

    class Meta:
        model = ConsultantReview
        fields = ['id',
                  'patient_name',
                  'rating',
                  'review_text',
                  'created_at',
                  'is_verified_consultation',
                  'is_anonymous',
        ]

    def get_patient_name(self, obj):
        if obj.is_anonymous:
            return  'Anonymous'
        return obj.patient.full_name

class ConsultantProfileListSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only = True)
    speciality = SpecialitySerializer(read_only = True)
    avatar_url = serializers.SerializerMethodField()

    rating = serializers.DecimalField(max_digits=3, decimal_places=2, coerce_to_string = False, default= 0.0)
    consultation_fee = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False, default= 0.0)
    years_of_experience = serializers.IntegerField(default=0)
    consultation_duration = serializers.IntegerField(default = 30 )
    total_consultations = serializers.IntegerField(default= 0)
    total_reviews = serializers.IntegerField(default= 0)

    class Meta:
        model = ConsultantProfile
        fields = ['id',
                  'user',
                  'speciality',
                  'bio',
                  'years_of_experience',
                  'consultation_fee',
                  'avatar_url',
                  'rating',
                  'total_consultations',
                  'total_reviews',
                  'consultation_fee',
                  'consultation_duration',
                  'consultation_types',
                  'is_verified',
                  'is_available',
                  'is_featured',
        ]

    def get_avatar_url(self, obj):
        if obj.avatar:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            # Fallback: build absolute URL manually
            from django.conf import settings
            return f"{settings.MEDIA_URL}{obj.avatar.name}"
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)

        data['rating'] = float(instance.rating or 0.0)
        data['consultation_fee'] = float(instance.consultation_fee or 0.00)
        data['years_of_experience'] = float(instance.years_of_experience or 0.00)
        data['consultation_duration'] = int(instance.consultation_duration or 0.00)
        data['total_consultation'] = int(instance.total_consultation or 0.00)
        data['total_reviews'] = int(instance.total_reviews or 0.00)

        data['board_certifications'] = [str(x) for x in (instance.board_certifications or []) if x]
        data['additional_qualifications'] = [
            str(x) for x in (instance.additional_qualifications or []) if x
        ]
        data["languages_spoken"] = [
            str(x) for x in (instance.languages_spoken or []) if x
        ]
        data['consultation_types'] = instance.consultation_types or 'all'

        return data


class ConsultantProfileDetailSerializer(ConsultantProfileListSerializer):
    recent_reviews = ConsultantReviewSerializer( source = 'reviews', many= True, read_only = True)
    availability_slots = ConsultantAvailabilitySerializer(many=True, read_only=True)
    license_number = serializers.CharField(required = True, allow_blank = True , allow_null = True)
    medical_degree = serializers.CharField(required = True, allow_blank = True, allow_null = True)
    phone_number = serializers.CharField(required= True, allow_blank = True, allow_null = True)
    clinic_name = serializers.CharField(required = False, allow_blank = True, allow_null = True)
    clinic_address = serializers.CharField(required = False, allow_blank= True, allow_null= True)
    clinic_city = serializers.CharField(required = False, allow_blank = True, allow_null = True)
    clinic_country = serializers.CharField(required = False, allow_blank = True, allow_null = True)

    class Meta(ConsultantProfileListSerializer.Meta):
        fields = ConsultantProfileListSerializer.Meta.fields + [
            'license_number',
            'medical_degree',
            'board_certifications',
            'additional_qualifications',
            'phone_number',
            'clinic_name',
            'clinic_address',
            'clinic_city',
            'clinic_country',
            'languages_spoken',
            'availability_slots',
            'availability_schedule',
            'recent_reviews',
            'languages_spoken',
            'verification_date',

        ]

class ConsultantProfileUpdateSerializer(serializers.ModelSerializer):
    availability_slots = ConsultantAvailabilitySerializer(many = True , required = False)
    consultation_fee = serializers.DecimalField(max_digits = 10, decimal_places=2, required = False, default = 0.0)
    years_of_experience = serializers.IntegerField(required = False, default=0.0)
    consultation_duration = serializers.IntegerField(required= False, default= 0)

    class Meta:
        model = ConsultantProfile
        fields = [
            
            'bio',
            'years_of_experience',
            'medical_degree',
            'board_certifications',
            'additional_qualifications',
            'phone_number',
            'clinic_name',
            'clinic_address',
            'clinic_city',
            'clinic_country',
            'languages_spoken',
            'availability_slots',
            'consultation_fee',
            'consultation_duration',
            'consultation_types',
            'is_available',

        ]

    def validate_consultation_fee(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Consultation fee cannot be negative")
        
        return value or 0.0
    
    def validate_years_of_experience(self, value):
        if value is not None and (value < 0 or value > 50):
            raise serializers.ValidationError(" Years of experience must be between 0 to 50 ")
        return value or 0
    
    def to_representation(self, instance):
        data = super(). to_representation(instance)
        data['consultation_fee'] = float(instance.consultation_fee or 0.0)
        data['years_of_experience'] = int(instance.years_of_experience or 0)
        data['consultation_duration'] = int(instance.consultation_duration or 30)
        
        return data
    
class ConsultantProfileCreateSerializer(serializers.ModelSerializer):
    speciality_id = serializers.IntegerField(write_only = True)
    consultation_fee = serializers.DecimalField(max_digits= 10, decimal_places=2, default = 0.00)
    years_of_experience = serializers.IntegerField(default = 30)
    
    class Meta:
        model = ConsultantProfile
        fields = [
            'speciality_id',
            'license_number',
            'bio',
            'years_of_experience',
            'medical_degree',
            'board_certifications',
            'additional_qualifications',
            'phone_number',
            'clinic_name',
            'clinic_address',
            'clinic_city',
            'clinic_country',
            'consultation_fee',
            'consultation_duration',
            'consultation_types',
            'languages_spoken',
            
        ]

class ConsulatantReviewCreateSerializer(serializers.ModelSerializer):
    rating = serializers.IntegerField(min_value = 1, max_value = 5)
    
    class Meta:
        model = ConsultantReview
        fields = ["rating", "review_text", "is_anonymous"]
        
    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating Must be between 1 and 5")
        return value
