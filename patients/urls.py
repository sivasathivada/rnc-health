from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PatientProfileViewSet,
    PatientMedicalHistoryViewSet,
    patient_statistics,
    search_patients,
)

router = DefaultRouter()
router.register(r'medical-history', PatientMedicalHistoryViewSet, basename='medical-history')
router.register(r'', PatientProfileViewSet, basename='patient-profile')

app_name = 'patients'

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
    
    # Custom endpoints
    path('statistics/', patient_statistics, name='patient-statistics'),
    path('search/', search_patients, name='search-patients'),
]
