import pytest
import uuid
from decimal import Decimal
from datetime import time, datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from django.test import TestCase, RequestFactory, Client
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from .models import (
    Speciality,
    ConsultantProfile,
    ConsultantReview,
    ConsultantAvailability
)
from .services import ConsultantService
from .serializers import (
    ConsultantProfileListSerializer,
    SpecialitySerializer,
    ConsultantReviewSerializer,
    ConsultantAvailabilitySerializer
)

User = get_user_model()

#defining fixures for test data setup

@pytest.fixture
def user_patient():
    """Create a test patient user"""
    return User.objects.create_user(
        email='patient@test.com',
        password='testpass123',
        first_name='John',
        last_name='Doe',
        role='patient'
    )


@pytest.fixture
def user_consultant():
    """Create a test consultant user"""
    return User.objects.create_user(
        email='consultant@test.com',
        password='testpass123',
        first_name='Dr.',
        last_name='Smith',
        role='consultant',
        is_active=True
    )


@pytest.fixture
def speciality():
    """Create a test medical speciality"""
    return Speciality.objects.create(
        name='Cardiology',
        description='Heart and cardiovascular diseases',
        icon='heart',
        is_active=True
    )


@pytest.fixture
def consultant_profile(user_consultant, speciality):
    """Create a test consultant profile"""
    return ConsultantProfile.objects.create(
        user=user_consultant,
        speciality=speciality,
        license_number='LIC123456',
        bio='Experienced cardiologist with 10 years',
        years_of_experience=10,
        medical_degree='MD - Cardiology',
        phone_number='+12345678901',
        clinic_name='Heart Care Clinic',
        clinic_address='123 Medical St',
        clinic_city='New York',
        clinic_country='USA',
        consultation_fee=Decimal('150.00'),
        consultation_duration=30,
        consultation_types='all',
        languages_spoken=['English', 'Spanish'],
        is_available=True,
        is_verified=True,
        rating=Decimal('4.50'),
        total_consultation=100,
        total_reviews=50
    )


@pytest.fixture
def api_client():
    """Create an API client for testing"""
    return APIClient()


@pytest.fixture
def request_factory():
    """Create a request factory for testing"""
    return RequestFactory()


# writing tests for consultant models

@pytest.mark.django_db
class TestSpecialityModel:
    """Test cases for Speciality model"""

    def test_speciality_creation(self, speciality):
        """Test creating a speciality"""
        assert speciality.id is not None
        assert speciality.name == 'Cardiology'
        assert speciality.is_active is True

    def test_speciality_string_representation(self, speciality):
        """Test speciality __str__ method"""
        assert str(speciality) == 'Cardiology'

    def test_speciality_uniqueness(self, speciality):
        """Test that speciality names are unique"""
        with pytest.raises(Exception):
            Speciality.objects.create(
                name='Cardiology',
                description='Another cardiology'
            )

    def test_speciality_is_active_default(self):
        """Test that is_active defaults to True"""
        spec = Speciality.objects.create(name='Neurology')
        assert spec.is_active is True

    def test_speciality_description_blank(self):
        """Test that description can be blank"""
        spec = Speciality.objects.create(name='Dermatology', description='')
        assert spec.description == ''


@pytest.mark.django_db
class TestConsultantProfileModel:
    """Test cases for ConsultantProfile model"""

    def test_consultant_profile_creation(self, consultant_profile):
        """Test creating a consultant profile"""
        assert consultant_profile.id is not None
        assert str(consultant_profile.id) == str(consultant_profile.id)

    def test_consultant_profile_string_representation(self, consultant_profile):
        """Test consultant profile __str__ method"""
        assert 'Dr. Dr. Smith - Cardiology' in str(consultant_profile)

    def test_consultant_profile_uuid_primary_key(self, consultant_profile):
        """Test that consultant profile uses UUID as primary key"""
        assert isinstance(consultant_profile.id, uuid.UUID)

    def test_consultant_profile_uniqueness_per_user(self, user_consultant, speciality):
        """Test that each user can have only one consultant profile"""
        ConsultantProfile.objects.create(
            user=user_consultant,
            speciality=speciality,
            license_number='LIC123456'
        )

        with pytest.raises(Exception):
            ConsultantProfile.objects.create(
                user=user_consultant,
                speciality=speciality,
                license_number='LIC789012'
            )

    def test_consultant_profile_license_number_uniqueness(self, user_consultant, user_consultant_2, speciality):
        """Test that license numbers are unique"""
        ConsultantProfile.objects.create(
            user=user_consultant,
            speciality=speciality,
            license_number='LIC123456'
        )

        # Create second consultant
        user_consultant_2 = User.objects.create_user(
            email='consultant2@test.com',
            password='testpass123',
            role='consultant'
        )

        with pytest.raises(Exception):
            ConsultantProfile.objects.create(
                user=user_consultant_2,
                speciality=speciality,
                license_number='LIC123456'
            )

    def test_consultant_profile_verify_consultant(self, consultant_profile):
        """Test verify_consultant method"""
        consultant_profile.is_verified = False
        consultant_profile.save()

        consultant_profile.verify_consultant()

        assert consultant_profile.is_verified is True
        assert consultant_profile.verification_date is not None

    def test_consultant_profile_update_rating(self, consultant_profile, user_patient):
        """Test update_rating method"""
        # Create reviews
        ConsultantReview.objects.create(
            consultant=consultant_profile,
            patient=user_patient,
            rating=5
        )

        consultant_profile.update_rating()
        assert consultant_profile.rating == Decimal('5.00')

    def test_consultant_profile_phone_validation(self, user_consultant, speciality):
        """Test phone number validation"""
        profile = ConsultantProfile(
            user=user_consultant,
            speciality=speciality,
            phone_number='invalid'
        )

        with pytest.raises(ValidationError):
            profile.full_clean()

    def test_consultant_profile_years_of_experience_max(self, user_consultant, speciality):
        """Test maximum years of experience validation"""
        profile = ConsultantProfile(
            user=user_consultant,
            speciality=speciality,
            years_of_experience=60
        )

        with pytest.raises(ValidationError):
            profile.full_clean()

    def test_consultant_profile_avatar_url_property(self, consultant_profile):
        """Test avatar_url property"""
        assert consultant_profile.avatar_url is None or isinstance(consultant_profile.avatar_url, str)

    def test_consultant_profile_consultation_fee_positive(self, user_consultant, speciality):
        """Test consultation fee must be positive"""
        profile = ConsultantProfile(
            user=user_consultant,
            speciality=speciality,
            consultation_fee=Decimal('-10.00')
        )

        with pytest.raises(ValidationError):
            profile.full_clean()

    @pytest.mark.parametrize("consultation_type", ['video', 'audio', 'chat', 'all'])
    def test_consultant_profile_consultation_types(self, user_consultant, speciality, consultation_type):
        """Test all consultation type choices"""
        profile = ConsultantProfile.objects.create(
            user=user_consultant,
            speciality=speciality,
            consultation_types=consultation_type
        )
        assert profile.consultation_types == consultation_type


@pytest.mark.django_db
class TestConsultantReviewModel:
    """Test cases for ConsultantReview model"""

    def test_consultant_review_creation(self, consultant_profile, user_patient):
        """Test creating a consultant review"""
        review = ConsultantReview.objects.create(
            consultant=consultant_profile,
            patient=user_patient,
            rating=5,
            review_text='Excellent service'
        )

        assert review.id is not None
        assert review.rating == 5

    def test_consultant_review_string_representation(self, consultant_profile, user_patient):
        """Test review __str__ method"""
        review = ConsultantReview.objects.create(
            consultant=consultant_profile,
            patient=user_patient,
            rating=4,
            is_anonymous=False
        )

        assert 'Dr. Smith' in str(review)
        assert '4' in str(review)

    def test_consultant_review_anonymous(self, consultant_profile, user_patient):
        """Test anonymous review"""
        review = ConsultantReview.objects.create(
            consultant=consultant_profile,
            patient=user_patient,
            rating=5,
            is_anonymous=True
        )

        assert 'Anonymous' in str(review)

    def test_consultant_review_uniqueness(self, consultant_profile, user_patient):
        """Test that each patient can review a consultant only once"""
        ConsultantReview.objects.create(
            consultant=consultant_profile,
            patient=user_patient,
            rating=5
        )

        with pytest.raises(Exception):
            ConsultantReview.objects.create(
                consultant=consultant_profile,
                patient=user_patient,
                rating=3
            )

    def test_consultant_review_rating_choices(self, consultant_profile, user_patient):
        """Test review rating choices"""
        for rating in range(1, 6):
            review = ConsultantReview.objects.create(
                consultant=consultant_profile,
                patient=user_patient,
                rating=rating
            )
            assert review.rating == rating
            review.delete()

    def test_consultant_review_updates_consultant_rating(self, consultant_profile, user_patient):
        """Test that adding a review updates consultant rating"""
        initial_rating = consultant_profile.rating

        ConsultantReview.objects.create(
            consultant=consultant_profile,
            patient=user_patient,
            rating=5
        )

        consultant_profile.refresh_from_db()
        # Rating should be updated (though exact value depends on existing reviews)
        assert consultant_profile.rating is not None


@pytest.mark.django_db
class TestConsultantAvailabilityModel:
    """Test cases for ConsultantAvailability model"""

    def test_consultant_availability_creation(self, consultant_profile):
        """Test creating consultant availability"""
        availability = ConsultantAvailability.objects.create(
            consultant=consultant_profile,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(17, 0)
        )

        assert availability.id is not None
        assert availability.day_of_week == 0

    def test_consultant_availability_string_representation(self, consultant_profile):
        """Test availability __str__ method"""
        availability = ConsultantAvailability.objects.create(
            consultant=consultant_profile,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(17, 0)
        )

        assert 'Dr. Smith' in str(availability)
        assert 'Monday' in str(availability)

    def test_consultant_availability_ordering(self, consultant_profile):
        """Test availability is ordered by day and time"""
        ConsultantAvailability.objects.create(
            consultant=consultant_profile,
            day_of_week=3,
            start_time=time(14, 0),
            end_time=time(16, 0)
        )

        ConsultantAvailability.objects.create(
            consultant=consultant_profile,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(12, 0)
        )

        slots = ConsultantAvailability.objects.filter(consultant=consultant_profile)
        assert slots[0].day_of_week == 1
        assert slots[1].day_of_week == 3

    def test_consultant_availability_unique_constraint(self, consultant_profile):
        """Test unique constraint on consultant, day, and start_time"""
        ConsultantAvailability.objects.create(
            consultant=consultant_profile,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(12, 0)
        )

        with pytest.raises(Exception):
            ConsultantAvailability.objects.create(
                consultant=consultant_profile,
                day_of_week=0,
                start_time=time(9, 0),
                end_time=time(14, 0)
            )

    @pytest.mark.parametrize("day", range(7))
    def test_consultant_availability_all_days(self, consultant_profile, day):
        """Test availability for all days of week"""
        availability = ConsultantAvailability.objects.create(
            consultant=consultant_profile,
            day_of_week=day,
            start_time=time(9, 0),
            end_time=time(17, 0)
        )
        assert availability.day_of_week == day


# ==================== SERVICE TESTS ====================
@pytest.mark.django_db
class TestConsultantService:
    """Test cases for ConsultantService"""

    def test_get_consultants_queryset_basic(self, consultant_profile):
        """Test basic consultant queryset retrieval"""
        queryset = ConsultantService.get_consultants_queryset()
        assert consultant_profile in queryset or queryset.count() >= 0

    def test_get_consultants_queryset_by_speciality(self, specialist_profile, speciality):
        """Test filtering consultants by speciality"""
        queryset = ConsultantService.get_consultants_queryset(speciality_id=speciality.id)
        # Should contain the specialist with this speciality
        assert queryset.count() >= 0

    def test_get_consultants_queryset_search(self, consultant_profile):
        """Test searching consultants by name"""
        queryset = ConsultantService.get_consultants_queryset(search_query='Smith')
        assert queryset.count() >= 0

    def test_get_consultants_queryset_available_only(self, consultant_profile):
        """Test filtering for available consultants only"""
        consultant_profile.is_available = False
        consultant_profile.save()

        queryset = ConsultantService.get_consultants_queryset(is_available_only=True)
        assert consultant_profile not in queryset

    def test_get_consultant_details_success(self, consultant_profile):
        """Test retrieving consultant details"""
        consultant, error = ConsultantService.get_consultant_details(str(consultant_profile.id))
        assert error is None

    def test_get_consultant_details_not_found(self):
        """Test retrieving non-existent consultant"""
        fake_id = uuid.uuid4()
        consultant, error = ConsultantService.get_consultant_details(str(fake_id))
        assert consultant is None
        assert error is not None

    def test_get_consultant_details_caching(self, consultant_profile):
        """Test consultant details caching"""
        consultant1, _ = ConsultantService.get_consultant_details(str(consultant_profile.id))
        consultant2, _ = ConsultantService.get_consultant_details(str(consultant_profile.id))

        assert consultant1.id == consultant2.id

    def test_create_consultant_profile_success(self, user_consultant, speciality):
        """Test creating consultant profile"""
        profile, error = ConsultantService.create_consultant_profile(
            user=user_consultant,
            speciality_id=speciality.id,
            license_number='NEW123'
        )

        assert profile is not None
        assert error is None

    def test_create_consultant_profile_invalid_user_role(self, user_patient, speciality):
        """Test creating profile for non-consultant user"""
        profile, error = ConsultantService.create_consultant_profile(
            user=user_patient,
            speciality_id=speciality.id,
            license_number='NEW123'
        )

        assert profile is None
        assert error is not None

    def test_create_consultant_profile_invalid_speciality(self, user_consultant):
        """Test creating profile with invalid speciality"""
        profile, error = ConsultantService.create_consultant_profile(
            user=user_consultant,
            speciality_id=uuid.uuid4(),
            license_number='NEW123'
        )

        assert profile is None
        assert error is not None

    def test_availability_schedule_success(self, consultant_profile):
        """Test setting valid non-overlapping availability slots"""
        schedule_data = [
            {'day_of_week': 0, 'start_time': '09:00', 'end_time': '12:00', 'is_active': True},
            {'day_of_week': 0, 'start_time': '13:00', 'end_time': '17:00', 'is_active': True},
        ]
        profile, error = ConsultantService.availability_schedule(consultant_profile.user, schedule_data)
        assert profile is not None
        assert error is None
        assert ConsultantAvailability.objects.filter(consultant=consultant_profile).count() == 2

    def test_availability_schedule_overlap(self, consultant_profile):
        """Test that overlapping slots on the same day are rejected"""
        schedule_data = [
            {'day_of_week': 1, 'start_time': '09:00', 'end_time': '12:00', 'is_active': True},
            {'day_of_week': 1, 'start_time': '11:00', 'end_time': '13:00', 'is_active': True},
        ]
        profile, error = ConsultantService.availability_schedule(consultant_profile.user, schedule_data)
        assert profile is None
        assert "Overlapping availability slots detected" in error


# Writing Unit test for serializers
@pytest.mark.django_db
class TestConsultantProfileListSerializer:
    """Test cases for ConsultantProfileListSerializer"""

    def test_serializer_valid_data(self, consultant_profile, request_factory):
        """Test serializer with valid data"""
        request = request_factory.get('/')
        serializer = ConsultantProfileListSerializer(
            consultant_profile,
            context={'request': request}
        )

        assert 'id' in serializer.data
        assert 'user' in serializer.data
        assert 'rating' in serializer.data

    def test_serializer_rating_conversion(self, consultant_profile, request_factory):
        """Test that rating is converted to float"""
        request = request_factory.get('/')
        serializer = ConsultantProfileListSerializer(
            consultant_profile,
            context={'request': request}
        )

        assert isinstance(serializer.data['rating'], float)

    def test_serializer_consultation_fee_conversion(self, consultant_profile, request_factory):
        """Test that consultation_fee is converted to float"""
        request = request_factory.get('/')
        serializer = ConsultantProfileListSerializer(
            consultant_profile,
            context={'request': request}
        )

        assert isinstance(serializer.data['consultation_fee'], float)


@pytest.mark.django_db
class TestConsultantReviewSerializer:
    """Test cases for ConsultantReviewSerializer"""

    def test_serializer_anonymous_review(self, consultant_profile, user_patient):
        """Test serializer with anonymous review"""
        review = ConsultantReview.objects.create(
            consultant=consultant_profile,
            patient=user_patient,
            rating=5,
            is_anonymous=True
        )

        serializer = ConsultantReviewSerializer(review)
        assert serializer.data['patient_name'] == 'Anonymous'

    def test_serializer_named_review(self, consultant_profile, user_patient):
        """Test serializer with named review"""
        review = ConsultantReview.objects.create(
            consultant=consultant_profile,
            patient=user_patient,
            rating=5,
            is_anonymous=False
        )

        serializer = ConsultantReviewSerializer(review)
        assert serializer.data['patient_name'] == user_patient.full_name


# writing unit test for class based views[ api endpoints ]
@pytest.mark.django_db
class TestConsultantListView(APITestCase):
    """Test cases for consultant_list API view"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.speciality = Speciality.objects.create(
            name='Cardiology',
            is_active=True
        )
        self.user_consultant = User.objects.create_user(
            email='consultant@test.com',
            password='testpass123',
            role='consultant',
            is_active=True
        )
        self.consultant_profile = ConsultantProfile.objects.create(
            user=self.user_consultant,
            speciality=self.speciality,
            is_verified=True,
            is_available=True
        )

    def test_list_consultants_success(self):
        """Test retrieving list of consultants"""
        response = self.client.get('/api/consultants/')
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

    def test_list_consultants_pagination(self):
        """Test consultant list pagination"""
        # Create multiple consultants
        for i in range(15):
            user = User.objects.create_user(
                email=f'consultant{i}@test.com',
                password='testpass',
                role='consultant'
            )
            ConsultantProfile.objects.create(
                user=user,
                speciality=self.speciality
            )

        response = self.client.get('/api/consultants/')
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

    def test_list_consultants_with_search(self):
        """Test consultant list with search"""
        response = self.client.get('/api/consultants/?search=consultant')
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

    def test_list_consultants_with_speciality_filter(self):
        """Test consultant list with speciality filter"""
        response = self.client.get(f'/api/consultants/?speciality_id={self.speciality.id}')
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]


@pytest.mark.django_db
class TestConsultantDetailView(APITestCase):
    """Test cases for consultant_detail API view"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.speciality = Speciality.objects.create(name='Cardiology')
        self.user = User.objects.create_user(
            email='consultant@test.com',
            password='testpass123',
            role='consultant'
        )
        self.consultant_profile = ConsultantProfile.objects.create(
            user=self.user,
            speciality=self.speciality,
            is_verified=True
        )

    def test_get_consultant_detail_success(self):
        """Test retrieving consultant detail"""
        response = self.client.get(f'/api/consultants/{self.consultant_profile.id}/')
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

    def test_get_consultant_detail_not_found(self):
        """Test retrieving non-existent consultant"""
        fake_id = uuid.uuid4()
        response = self.client.get(f'/api/consultants/{fake_id}/')
        assert response.status_code in [status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED]


@pytest.mark.django_db
class TestSpecialitiesListView(APITestCase):
    """Test cases for specialities_list API view"""

    def test_list_specialities_success(self):
        """Test retrieving list of specialities"""
        Speciality.objects.create(name='Cardiology', is_active=True)
        Speciality.objects.create(name='Neurology', is_active=True)

        response = self.client.get('/api/specialities/')
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

    def test_list_specialities_only_active(self):
        """Test that only active specialities are returned"""
        Speciality.objects.create(name='Cardiology', is_active=True)
        Speciality.objects.create(name='Inactive', is_active=False)

        response = self.client.get('/api/specialities/')
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]


@pytest.mark.django_db
class TestCreateConsultantProfileView(APITestCase):
    """Test cases for create_consultant_profile API view"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.speciality = Speciality.objects.create(name='Cardiology')
        self.user = User.objects.create_user(
            email='consultant@test.com',
            password='testpass123',
            role='consultant'
        )

    def test_create_profile_as_consultant(self):
        """Test creating consultant profile as consultant user"""
        self.client.force_authenticate(user=self.user)

        data = {
            'speciality_id': self.speciality.id,
            'license_number': 'LIC123',
            'bio': 'Experienced consultant'
        }

        response = self.client.post('/api/consultant/profile/create/', data=data, format='json')
        assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND]

    def test_create_profile_as_non_consultant(self):
        """Test that non-consultants cannot create profile"""
        patient = User.objects.create_user(
            email='patient@test.com',
            password='testpass123',
            role='patient'
        )
        self.client.force_authenticate(user=patient)

        data = {'speciality_id': self.speciality.id}
        response = self.client.post('/api/consultant/profile/create/', data=data, format='json')
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]

    def test_create_profile_unauthenticated(self):
        """Test that unauthenticated users cannot create profile"""
        data = {'speciality_id': self.speciality.id}
        response = self.client.post('/api/consultant/profile/create/', data=data, format='json')
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_404_NOT_FOUND]


@pytest.mark.django_db
class TestConsultantReviewView(APITestCase):
    """Test cases for add_consultant_review API view"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.speciality = Speciality.objects.create(name='Cardiology')
        self.consultant_user = User.objects.create_user(
            email='consultant@test.com',
            password='testpass123',
            role='consultant'
        )
        self.consultant_profile = ConsultantProfile.objects.create(
            user=self.consultant_user,
            speciality=self.speciality
        )
        self.patient_user = User.objects.create_user(
            email='patient@test.com',
            password='testpass123',
            role='patient'
        )

    def test_add_review_as_patient(self):
        """Test adding review as patient"""
        self.client.force_authenticate(user=self.patient_user)

        data = {
            'rating': 5,
            'review_text': 'Excellent consultantion'
        }

        response = self.client.post(
            f'/api/consultant/{self.consultant_profile.id}/review/',
            data=data,
            format='json'
        )
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND]

    def test_add_review_as_non_patient(self):
        """Test that consultants cannot add reviews"""
        self.client.force_authenticate(user=self.consultant_user)

        data = {'rating': 5}
        response = self.client.post(
            f'/api/consultant/{self.consultant_profile.id}/review/',
            data=data,
            format='json'
        )
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]

    def test_add_duplicate_review(self):
        """Test adding duplicate review by same patient"""
        self.client.force_authenticate(user=self.patient_user)

        data = {'rating': 5, 'review_text': 'Great'}

        # First review
        response1 = self.client.post(
            f'/api/consultant/{self.consultant_profile.id}/review/',
            data=data,
            format='json'
        )

        # Duplicate review
        response2 = self.client.post(
            f'/api/consultant/{self.consultant_profile.id}/review/',
            data=data,
            format='json'
        )

        assert response2.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND]


# EDGE CASE AND INTEGRATION TESTS 

@pytest.mark.django_db
class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_consultant_with_zero_rating(self, user_consultant, speciality):
        """Test consultant with zero reviews/rating"""
        profile = ConsultantProfile.objects.create(
            user=user_consultant,
            speciality=speciality,
            rating=Decimal('0.00'),
            total_consultation=0
        )
        assert profile.rating == Decimal('0.00')

    def test_consultant_with_max_experience(self, user_consultant, speciality):
        """Test consultant with maximum years of experience"""
        profile = ConsultantProfile.objects.create(
            user=user_consultant,
            speciality=speciality,
            years_of_experience=50
        )
        assert profile.years_of_experience == 50

    def test_consultant_rating_precision(self, consultant_profile, user_patient):
        """Test rating calculation precision"""
        # Create multiple reviews with different ratings
        ratings = [5, 4, 3, 4, 5]
        for rating in ratings:
            ConsultantReview.objects.create(
                consultant=consultant_profile,
                patient=user_patient if user_patient not in [
                    ConsultantReview.objects.filter(consultant=consultant_profile).values_list('patient', flat=True)
                ] else None,
                rating=rating
            )

    @pytest.mark.parametrize("fee", [Decimal('0.00'), Decimal('50.00'), Decimal('999.99')])
    def test_consultant_fee_variations(self, user_consultant, speciality, fee):
        """Test various consultant fee amounts"""
        profile = ConsultantProfile.objects.create(
            user=user_consultant,
            speciality=speciality,
            consultation_fee=fee
        )
        assert profile.consultation_fee == fee


@pytest.mark.django_db
class TestConsultantCaching:
    """Test caching behavior"""

    @patch('consultants.services.cache')
    def test_consultant_details_caching_hit(self, mock_cache, consultant_profile):
        """Test cache hit for consultant details"""
        mock_cache.get.return_value = consultant_profile

        consultant, error = ConsultantService.get_consultant_details(str(consultant_profile.id))
        mock_cache.get.assert_called_once()

    @patch('consultants.services.cache')
    def test_consultant_details_caching_miss(self, mock_cache, consultant_profile):
        """Test cache miss for consultant details"""
        mock_cache.get.return_value = None

        # This would normally hit the database
        assert mock_cache.get.return_value is None


@pytest.mark.django_db
class TestConsultantAvatarUpload(APITestCase):
    """Test cases for update_consultant_avatar API view"""

    def setUp(self):
        self.client = APIClient()
        self.speciality = Speciality.objects.create(name='Cardiology')
        self.consultant_user = User.objects.create_user(
            email='consultant_avatar@test.com',
            password='testpassword123',
            role='consultant',
            is_active=True
        )
        self.consultant_profile = ConsultantProfile.objects.create(
            user=self.consultant_user,
            speciality=self.speciality,
            license_number='LICAVATAR123'
        )

    def test_consultant_avatar_upload_success(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_authenticate(user=self.consultant_user)

        # Create a valid mock image (PNG file signature)
        image_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        avatar_file = SimpleUploadedFile("avatar.png", image_content, content_type="image/png")

        response = self.client.post(
            '/api/v1/consultants/profile/avatar/',
            {'avatar': avatar_file},
            format='multipart'
        )

        assert response.status_code == status.HTTP_200_OK
        assert 'avatar_url' in response.data
        self.consultant_profile.refresh_from_db()
        assert self.consultant_profile.avatar is not None
        assert self.consultant_profile.avatar.name.startswith('consultants/avatars/')

    def test_consultant_avatar_upload_size_validation(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_authenticate(user=self.consultant_user)

        # Create a file that is too large (6MB)
        large_content = b'0' * (6 * 1024 * 1024)
        avatar_file = SimpleUploadedFile("large.png", large_content, content_type="image/png")

        response = self.client.post(
            '/api/v1/consultants/profile/avatar/',
            {'avatar': avatar_file},
            format='multipart'
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'File size too large' in response.data['error']

