# Writing api's for backend we can consume those api's to the front end

from operator import truediv
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import User
from rest_framework import serializers

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only = True, min_length=8)
    password_confirmation = serializers.CharField(write_only= True, min_length=8)
    
    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'role', 'password','password_confirmation']
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirmation']:
            raise serializers.validationError("Password don't Match")
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirmation')
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    has_verified_email = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name', 'role', 'is_online', 'last_seen',
            'is_active', 'is_verified', 'has_verified_email', 'email_verified_at', 'created_at', 'updated_at'
        ]

    def get_has_verified_email(self, obj):
        return  obj.is_verified

class LoginSerailizers(serializers.ModelSerializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['email', 'password',]
    

class EmailVerificationSerializer(serializers.Serializer):
    token = serializers.UUIDField()

class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()

 