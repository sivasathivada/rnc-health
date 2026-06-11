
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import PatientProfile, PatientMedicalHistory
from authentication.serializers import UserSerializer


class PatientProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only = True)
    avatar_url = serializers.SerializerMethodField()
    age = serializers.ReadOnlyField()
    
    
    class Meta:
        model = PatientProfile
        fields = [
            'id',
            'user',
            'avatar_url',
            'bio',
            'date_of_birth',
            'age',
            'gender',
            'phone_number',
            'address', 
            'city',
            'country', 
            'postal_code', 
            'emergency_contact_name', 
            'emergency_contact_phone', 
            'emergency_contact_relationship',
            'blood_type',
            'allergies',
            'chronic_conditions',
            'current_medications',
            'medical_notes',
            'share_medical_history',
            'allow_emergency_access',
            'preferred_language',
            'created_at',
            'updated_at'
       
        ]
      
    def get_avatar_url(self, obj):
        if obj.avatar:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return None
    
class PatientProfileUpdateSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = PatientProfile
        fields = [
            'bio', 
            'date_of_birth', 
            'gender',
            'phone_number',
            'address', 
            'city',
            'country', 
            'postal_code', 
            'emergency_contact_name', 
            'emergency_contact_phone', 
            'emergency_contact_relationship',
            'blood_type',
            'allergies',
            'chronic_conditions',
            'current_medications',
            'medical_notes',
            'share_medical_history',
            'allow_emergency_access',
            'preferred_language',
        
        ]
        
    def validate_allergies(self, value):
        if not  isinstance(value, list):
            raise serializers.ValidationError("Allergies must be a list")
        return value
    
    def validate_chronic_conditions(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Chronic must be a list")
        return value
    
    def validate_current_medications(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Current medications must be a list")
        return value
    
class PatientMedicalHistorySerializer(serializers.ModelSerializer):
    
    class Meta:
        model = PatientMedicalHistory
        fields = [
            'id',
            'record_type',
            'title',
            'description',
            'date_occurred',
            'healthcare_provider',
            'attachments',
            'created_at',
            'updated_at'
        ]
        
        
class PatientMedicalHistoryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientMedicalHistory
        fields = [
            'record_type',
            'title',
            'description',
            'date_occurred',
            'healthcare_provider',
            'attachments',
        ]
        
        