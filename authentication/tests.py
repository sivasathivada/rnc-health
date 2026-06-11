from unittest.mock import patch
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

User = get_user_model()

class GoogleLoginTests(APITestCase):
    def setUp(self):
        self.url = reverse('google_login')

    @patch('requests.get')
    def test_google_login_new_user_success(self, mock_get):
        # Mock successful tokeninfo response from Google
        mock_response = mock_get.return_value
        mock_response.ok = True
        mock_response.json.return_value = {
            'email': 'newuser@example.com',
            'given_name': 'John',
            'family_name': 'Doe',
            'aud': 'fake-client-id',
            'iss': 'https://accounts.google.com',
            'email_verified': True
        }

        # Override GOOGLE_CLIENT_ID setting to match the mock
        with self.settings(GOOGLE_CLIENT_ID='fake-client-id'):
            response = self.client.post(self.url, {'token': 'valid-google-token', 'role': 'patient'}, secure=True)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access_token', response.data)
        self.assertIn('refresh_token', response.data)
        self.assertEqual(response.data['user']['email'], 'newuser@example.com')
        self.assertEqual(response.data['user']['first_name'], 'John')
        self.assertEqual(response.data['user']['last_name'], 'Doe')

        # Check user database record
        user = User.objects.get(email='newuser@example.com')
        self.assertTrue(user.is_verified)
        self.assertEqual(user.role, 'patient')

    @patch('requests.get')
    def test_google_login_existing_user_success(self, mock_get):
        # Create an existing user
        existing_user = User.objects.create_user(
            email='existing@example.com',
            password='oldpassword',
            first_name='Jane',
            last_name='Smith',
            role='consultant'
        )

        mock_response = mock_get.return_value
        mock_response.ok = True
        mock_response.json.return_value = {
            'email': 'existing@example.com',
            'given_name': 'Jane',
            'family_name': 'Smith',
            'aud': 'fake-client-id',
            'iss': 'https://accounts.google.com',
            'email_verified': True
        }

        with self.settings(GOOGLE_CLIENT_ID='fake-client-id'):
            response = self.client.post(self.url, {'token': 'valid-google-token'}, secure=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access_token', response.data)
        self.assertIn('refresh_token', response.data)
        self.assertEqual(response.data['user']['email'], 'existing@example.com')
        self.assertEqual(response.data['user']['role'], 'consultant')

    @patch('requests.get')
    def test_google_login_invalid_token(self, mock_get):
        # Mock failed verification
        mock_response = mock_get.return_value
        mock_response.ok = False

        response = self.client.post(self.url, {'token': 'invalid-token'}, secure=True)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_google_login_missing_token(self):
        response = self.client.post(self.url, {}, secure=True)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)


