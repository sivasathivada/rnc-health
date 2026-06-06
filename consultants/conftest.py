"""
Pytest configuration for consultants app models, views, serializers
Contains shared fixtures and test configuration

"""

import os
import sys
import django
import pytest
from pathlib import Path

# Add the project root to the Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rnchealth.settings')

# Setup Django before importing models
django.setup()

from django.contrib.auth import get_user_model
from consultants.models import Speciality, ConsultantProfile

User = get_user_model()


@pytest.fixture
def user_consultant_2():
    """Create a second test consultant user for uniqueness tests"""
    return User.objects.create_user(
        email='consultant2@test.com',
        password='testpass123',
        first_name='Dr.',
        last_name='Johnson',
        role='consultant',
        is_active=True
    )


@pytest.fixture
def specialist_profile(user_consultant_2):
    """Create a second specialist profile for filtering tests"""
    speciality = Speciality.objects.create(
        name='Neurology',
        description='Nervous system and brain',
        is_active=True
    )
    return ConsultantProfile.objects.create(
        user=user_consultant_2,
        speciality=speciality,
        license_number='NEU789012',
        bio='Expert in neurological disorders',
        years_of_experience=12,
        consultation_fee=200.00,
        is_verified=True,
        rating=4.75
    )


@pytest.fixture(scope='session')
def django_db_setup():
    """
    Override django db setup to use test database for all tests
    """
    pass


@pytest.fixture
def db_setup(db):
    """
    Setup database for each test
    """
    pass
