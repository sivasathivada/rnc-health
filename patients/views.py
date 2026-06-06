from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError, NotFound

from .serializers import(
    PatientMedicalHistoryCreateSerializer,
    PatientMedicalHistorySerializer,
    PatientProfileSerializer,
    PatientProfileUpdateSerializer, 
)

from .models import PatientProfile, PatientMedicalHistory

from .services import (
    PatientProfileService,
    PatientMedicalHistoryService,
    PatientStatisticsService,
    PatientSearchService,
)


class PatientProfilePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

#Patient Profile views

class PatientProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing patient profiles.
    
    Endpoints:
    - GET /patients/ - List all patients (authenticated users)
    - POST /patients/ - Create a new patient profile
    - GET /patients/{id}/ - Retrieve a specific patient profile
    - PUT /patients/{id}/ - Update a patient profile
    - PATCH /patients/{id}/ - Partially update a patient profile
    - DELETE /patients/{id}/ - Delete a patient profile
    - GET /patients/{id}/medical-history/ - Get patient's medical history
    """
    
    queryset = PatientProfile.objects.all()
    serializer_class = PatientProfileSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PatientProfilePagination
    
    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action in ['update', 'partial_update']:
            return PatientProfileUpdateSerializer
        return PatientProfileSerializer
    
    def get_queryset(self):
        """Filter patients based on user permissions"""
        return PatientProfileService.get_patients_for_user(self.request.user)
    
    def perform_create(self, serializer):
        """Create a patient profile for the authenticated user"""
        validated_data = serializer.validated_data
        patient = PatientProfileService.create_patient_profile(
            self.request.user, 
            validated_data
        )
    
    def perform_update(self, serializer):
        """Update patient profile"""
        patient = serializer.instance
        PatientProfileService.update_patient_profile(
            patient, 
            serializer.validated_data
        )
    
    def perform_destroy(self, instance):
        """Delete patient profile"""
        PatientProfileService.delete_patient_profile(instance)
    
    @action(detail=True, methods=['get'])
    def medical_history(self, request, pk=None):
        """Get medical history for a specific patient"""
        try:
            patient = PatientProfileService.get_patient_by_id(pk)
            record_type = request.query_params.get('record_type')
            
            if record_type:
                medical_records = PatientMedicalHistoryService.get_medical_records_by_type(
                    patient, 
                    record_type
                )
            else:
                medical_records = PatientMedicalHistoryService.get_patient_medical_history(patient)
            
            serializer = PatientMedicalHistorySerializer(medical_records, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except NotFound as e:
            return Response({"error": str(e.detail)}, status=status.HTTP_404_NOT_FOUND)
        except PatientProfile.DoesNotExist:
            return Response(
                {"error": "Patient not found"},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user's patient profile"""
        try:
            patient_profile = PatientProfileService.get_patient_by_user(request.user)
            serializer = self.get_serializer(patient_profile, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except NotFound as e:
            return Response({"error": str(e.detail)}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Get a summary of patient profile"""
        try:
            patient = PatientProfileService.get_patient_by_id(pk)
            summary_data = PatientProfileService.get_patient_summary(patient)
            return Response(summary_data, status=status.HTTP_200_OK)
        except NotFound as e:
            return Response({"error": str(e.detail)}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'], url_path='profile/avatar')
    def update_avatar(self, request):
        """Upload/update patient profile avatar"""
        if request.user.role != 'patient':
            return Response({"error": "Only patients can update avatar"}, status=status.HTTP_403_FORBIDDEN)
        if 'avatar' not in request.FILES:
            return Response({"error": "No avatar file provided"}, status=status.HTTP_400_BAD_REQUEST)
        avatar_file = request.FILES['avatar']
        
        if avatar_file.size > 5 * 1024 * 1024:
            return Response({"error": "File size too large. Maximum size is 5MB"}, status=status.HTTP_400_BAD_REQUEST)
            
        if not avatar_file.content_type.startswith('image/'):
            return Response({"error": "File must be an image"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            patient_profile = PatientProfileService.get_patient_by_user(request.user)
            updated_profile, error = PatientProfileService.update_patient_avatar(patient_profile, avatar_file)
            if updated_profile:
                # Build absolute URL so the frontend can use it directly
                avatar_url = request.build_absolute_uri(updated_profile.avatar.url) if updated_profile.avatar else None
                return Response({
                    "message": "Avatar updated successfully",
                    "avatar_url": avatar_url
                }, status=status.HTTP_200_OK)
            else:
                return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
        except NotFound as e:
            return Response({"error": str(e.detail)}, status=status.HTTP_404_NOT_FOUND)


# ==================== MEDICAL HISTORY VIEWS ====================

class PatientMedicalHistoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing patient medical history records.
    
    Endpoints:
    - GET /medical-history/ - List all medical history records
    - POST /medical-history/ - Create a new medical record
    - GET /medical-history/{id}/ - Retrieve a specific record
    - PUT /medical-history/{id}/ - Update a medical record
    - PATCH /medical-history/{id}/ - Partially update a record
    - DELETE /medical-history/{id}/ - Delete a medical record
    """
    
    serializer_class = PatientMedicalHistorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PatientProfilePagination
    
    def get_serializer_class(self):
        """Use different serializers for create vs retrieve"""
        if self.action == 'create':
            return PatientMedicalHistoryCreateSerializer
        return PatientMedicalHistorySerializer
    
    def get_queryset(self):
        """Filter medical history based on user permissions"""
        return PatientMedicalHistoryService.get_medical_records_for_user(self.request.user)
    
    def perform_create(self, serializer):
        """Create a medical history record for the patient"""
        try:
            patient_profile = PatientProfileService.get_patient_by_user(self.request.user)
            PatientMedicalHistoryService.create_medical_record(
                patient_profile,
                serializer.validated_data
            )
        except NotFound as e:
            raise ValidationError(detail=str(e.detail))
    
    def perform_update(self, serializer):
        """Update medical history record"""
        record = serializer.instance
        PatientMedicalHistoryService.update_medical_record(
            record,
            serializer.validated_data
        )
    
    def perform_destroy(self, instance):
        """Delete medical history record"""
        PatientMedicalHistoryService.delete_medical_record(instance)
        instance.delete()
    
    @action(detail=False, methods=['get'])
    def by_type(self, request):
        """Filter medical records by record_type"""
        record_type = request.query_params.get('type')
        
        if not record_type:
            return Response(
                {"error": "Please provide 'type' query parameter"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        records = PatientMedicalHistoryService.get_all_medical_records_by_type(record_type)
        
        if not records.exists():
            return Response(
                {"message": f"No records found for type: {record_type}"},
                status=status.HTTP_200_OK
            )
        
        page = self.paginate_queryset(records)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(records, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent medical records (last 10)"""
        try:
            patient = PatientProfileService.get_patient_by_user(request.user)
            recent_records = PatientMedicalHistoryService.get_recent_medical_records(patient, limit=10)
            serializer = self.get_serializer(recent_records, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except NotFound as e:
            return Response({"error": str(e.detail)}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['get'])
    def details(self, request, pk=None):
        """Get detailed information about a specific medical record"""
        try:
            record = PatientMedicalHistoryService.get_medical_record_by_id(pk)
            serializer = self.get_serializer(record)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except NotFound as e:
            return Response({"error": str(e.detail)}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'], url_path='upload-document')
    def upload_document(self, request):
        """Upload a medical document/attachment"""
        if request.user.role != 'patient':
            return Response({"error": "Only patients can upload documents"}, status=status.HTTP_403_FORBIDDEN)
        if 'document' not in request.FILES:
            return Response({"error": "No document file provided"}, status=status.HTTP_400_BAD_REQUEST)
        doc_file = request.FILES['document']
        
        if doc_file.size > 10 * 1024 * 1024:
            return Response({"error": "File size too large. Maximum size is 10MB"}, status=status.HTTP_400_BAD_REQUEST)
            
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        import uuid
        import os
        
        try:
            ext = os.path.splitext(doc_file.name)[1]
            filename = f"patients/documents/{request.user.id}_{uuid.uuid4().hex[:8]}{ext}"
            file_path = default_storage.save(filename, ContentFile(doc_file.read()))
            
            return Response({
                "message": "Document uploaded successfully",
                "file_name": doc_file.name,
                "file_path": file_path,
                "file_url": request.build_absolute_uri(default_storage.url(file_path))
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# FUNCTION-BASED VIEWS

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def patient_statistics(request):
    """Get statistics about patients and their medical records"""
    
    # Check if user has permission to view statistics
    if not request.user.is_staff and not hasattr(request.user, 'consultant_profile'):
        return Response(
            {"error": "You don't have permission to view statistics"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    stats = PatientStatisticsService.get_platform_statistics()
    return Response(stats, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_patients(request):
    """Search patients by name, email, or phone number"""
    
    # Check if user has permission to search
    if not request.user.is_staff and not hasattr(request.user, 'consultant_profile'):
        return Response(
            {"error": "You don't have permission to search patients"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    query = request.query_params.get('q', '').strip()
    
    try:
        patients = PatientSearchService.search_patients(query)
        
        if not patients.exists():
            return Response(
                {"message": "No patients found matching your search"},
                status=status.HTTP_200_OK
            )
        
        serializer = PatientProfileSerializer(patients, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except ValidationError as e:
        return Response(
            {"error": str(e.detail)},
            status=status.HTTP_400_BAD_REQUEST
        )
        