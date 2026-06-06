"""
Factory definitions for testing using factory-boy
Provides reusable factory patterns for creating test data
Using faker module to generate realistic data for testing
"""

import factory
from factory import Faker, SubFactory
from datetime import time
from decimal import Decimal

from django.contrib.auth import get_user_model
from consultants.models import (
    Speciality,
    ConsultantProfile,
    ConsultantReview,
    ConsultantAvailability
)

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    """Factory for creating User instances"""

    class Meta:
        model = User

    email = Faker('email')
    first_name = Faker('first_name')
    last_name = Faker('last_name')
    role = 'patient'
    is_active = True
    password = factory.django.Password('defaultpassword123')

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override the default _create to use create_user"""
        manager = cls._get_manager(model_class)
        return manager.create_user(*args, **kwargs)


class ConsultantUserFactory(UserFactory):
    """Factory for creating Consultant User instances"""

    role = 'consultant'
    is_active = True


class PatientUserFactory(UserFactory):
    """Factory for creating Patient User instances"""

    role = 'patient'
    is_active = True


class SpecialityFactory(factory.django.DjangoModelFactory):
    """Factory for creating Speciality instances"""

    class Meta:
        model = Speciality

    name = factory.Sequence(lambda n: f"Speciality {n}")
    description = Faker('paragraph', nb_sentences=3)
    icon = factory.Faker('word')
    is_active = True


class ConsultantProfileFactory(factory.django.DjangoModelFactory):
    """Factory for creating ConsultantProfile instances"""

    class Meta:
        model = ConsultantProfile
        skip_postgen_save = True

    user = SubFactory(ConsultantUserFactory)
    speciality = SubFactory(SpecialityFactory)
    
    # Basic info
    license_number = factory.Sequence(lambda n: f"LIC{n:06d}")
    bio = Faker('paragraph', nb_sentences=2)
    years_of_experience = factory.Faker('random_int', min=1, max=40)
    
    # Qualifications
    medical_degree = factory.Faker('word')
    board_certifications = factory.LazyFunction(
        lambda: ['Board Certification 1', 'Board Certification 2']
    )
    additional_qualifications = factory.LazyFunction(
        lambda: ['Qualification 1', 'Qualification 2']
    )
    
    # Contact details
    phone_number = factory.Faker('phone_number')
    clinic_name = Faker('company')
    clinic_address = Faker('address')
    clinic_city = Faker('city')
    clinic_country = Faker('country')
    
    # Professional details
    consultation_fee = factory.Faker('pydecimal', left_digits=3, right_digits=2, positive=True)
    consultation_duration = factory.Faker('random_int', min=15, max=60)
    consultation_types = 'all'
    
    # Languages
    languages_spoken = factory.LazyFunction(
        lambda: ['English', 'Spanish', 'French']
    )
    
    # Availability
    is_available = True
    availability_schedule = factory.LazyFunction(
        lambda: {
            'monday': ['09:00-12:00', '14:00-17:00'],
            'tuesday': ['09:00-12:00', '14:00-17:00'],
        }
    )
    
    # Stats
    rating = factory.Faker('pydecimal', left_digits=1, right_digits=2, min_value=0, max_value=5)
    total_consultation = factory.Faker('random_int', min=0, max=1000)
    total_reviews = factory.Faker('random_int', min=0, max=500)
    
    # Verification
    is_verified = True
    is_featured = False


class ConsultantReviewFactory(factory.django.DjangoModelFactory):
    """Factory for creating ConsultantReview instances"""

    class Meta:
        model = ConsultantReview

    consultant = SubFactory(ConsultantProfileFactory)
    patient = SubFactory(PatientUserFactory)
    
    rating = factory.Faker('random_int', min=1, max=5)
    review_text = Faker('paragraph', nb_sentences=3)
    is_verified_consultation = factory.Faker('pybool')
    is_anonymous = False


class ConsultantAvailabilityFactory(factory.django.DjangoModelFactory):
    """Factory for creating ConsultantAvailability instances"""

    class Meta:
        model = ConsultantAvailability

    consultant = SubFactory(ConsultantProfileFactory)
    day_of_week = factory.Faker('random_int', min=0, max=6)
    start_time = factory.LazyFunction(lambda: time(9, 0))
    end_time = factory.LazyFunction(lambda: time(17, 0))
    is_active = True


# Batch factories
class ConsultantProfileBatchFactory:
    """Batch factory for creating multiple consultant profiles"""

    @staticmethod
    def create_batch(count=5, **kwargs):
        """Create multiple consultant profiles"""
        return [
            ConsultantProfileFactory(**kwargs)
            for _ in range(count)
        ]

    @staticmethod
    def create_with_reviews(consultant_count=3, reviews_per_consultant=5):
        """Create consultants with reviews"""
        consultants = []
        for _ in range(consultant_count):
            consultant = ConsultantProfileFactory()
            for _ in range(reviews_per_consultant):
                ConsultantReviewFactory(consultant=consultant)
            consultants.append(consultant)
        return consultants

    @staticmethod
    def create_with_availability(consultant_count=3):
        """Create consultants with availability slots"""
        consultants = []
        for _ in range(consultant_count):
            consultant = ConsultantProfileFactory()
            for day in range(7):
                ConsultantAvailabilityFactory(
                    consultant=consultant,
                    day_of_week=day
                )
            consultants.append(consultant)
        return consultants
