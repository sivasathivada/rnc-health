import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from patients.models import PatientProfile, PatientMedicalHistory

User = get_user_model()

class PatientUploadTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Create Patient User
        self.patient_user = User.objects.create_user(
            email='patient@test.com',
            password='testpassword123',
            first_name='John',
            last_name='Doe',
            role='patient',
            is_active=True
        )
        self.patient_profile = PatientProfile.objects.create(
            user=self.patient_user,
            gender='male',
            phone_number='+1234567890'
        )
        
        # Create Consultant User
        self.consultant_user = User.objects.create_user(
            email='consultant@test.com',
            password='testpassword123',
            first_name='Dr. Jane',
            last_name='Smith',
            role='consultant',
            is_active=True
        )
        
    def test_patient_avatar_upload_success(self):
        self.client.force_authenticate(user=self.patient_user)
        
        # Create a mock image file
        image_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        avatar_file = SimpleUploadedFile("avatar.png", image_content, content_type="image/png")
        
        response = self.client.post(
            '/api/v1/patients/profile/avatar/',
            {'avatar': avatar_file},
            format='multipart'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert 'avatar_url' in response.data
        self.patient_profile.refresh_from_db()
        assert self.patient_profile.avatar is not None
        assert self.patient_profile.avatar.name.startswith('patients/avatars/')

    def test_patient_avatar_upload_size_validation(self):
        self.client.force_authenticate(user=self.patient_user)
        
        # Create a file that is too large (6MB)
        large_content = b'0' * (6 * 1024 * 1024)
        avatar_file = SimpleUploadedFile("large.png", large_content, content_type="image/png")
        
        response = self.client.post(
            '/api/v1/patients/profile/avatar/',
            {'avatar': avatar_file},
            format='multipart'
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'File size too large' in response.data['error']

    def test_patient_avatar_upload_non_image_validation(self):
        self.client.force_authenticate(user=self.patient_user)
        
        # Create a plain text file
        doc_file = SimpleUploadedFile("test.txt", b"plain text content", content_type="text/plain")
        
        response = self.client.post(
            '/api/v1/patients/profile/avatar/',
            {'avatar': doc_file},
            format='multipart'
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'File must be an image' in response.data['error']

    def test_patient_avatar_upload_role_validation(self):
        # Authenticate as consultant
        self.client.force_authenticate(user=self.consultant_user)
        
        image_content = b'\x89PNG...'
        avatar_file = SimpleUploadedFile("avatar.png", image_content, content_type="image/png")
        
        response = self.client.post(
            '/api/v1/patients/profile/avatar/',
            {'avatar': avatar_file},
            format='multipart'
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_patient_document_upload_success(self):
        self.client.force_authenticate(user=self.patient_user)
        
        # Create a mock document file
        doc_content = b'%PDF-1.4 test pdf content'
        doc_file = SimpleUploadedFile("report.pdf", doc_content, content_type="application/pdf")
        
        response = self.client.post(
            '/api/v1/patients/medical-history/upload-document/',
            {'document': doc_file},
            format='multipart'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert 'file_url' in response.data
        assert response.data['file_name'] == 'report.pdf'
        assert 'patients/documents/' in response.data['file_path']

    def test_patient_document_upload_size_validation(self):
        self.client.force_authenticate(user=self.patient_user)
        
        # Create a file that is too large (11MB)
        large_content = b'0' * (11 * 1024 * 1024)
        doc_file = SimpleUploadedFile("large.pdf", large_content, content_type="application/pdf")
        
        response = self.client.post(
            '/api/v1/patients/medical-history/upload-document/',
            {'document': doc_file},
            format='multipart'
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'File size too large' in response.data['error']
