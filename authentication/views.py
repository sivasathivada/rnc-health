from logging import exception

from django.contrib.auth.context_processors import auth
from django.contrib.messages.api import success
from django.shortcuts import render
from rest_framework import  status
from rest_framework.decorators import  api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import  Response
from rest_framework_simplejwt.tokens import  RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from django.contrib.auth import  get_user_model
from .serializers import UserRegistrationSerializer, LoginSerailizers, UserSerializer, ResendVerificationSerializer, EmailVerificationSerializer
from .services import AuthenticationService, EmailVerificationService
from django.contrib.messages import success
from .models import EmailVerificationToken



User = get_user_model()

def verify_email_page(request, token):
    """
    Serve the email verification page template
    """
    return render(request, 'verify_email.html', {'token': token})

@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """ User registration Endpoint"""
    serializer = UserRegistrationSerializer( data=request.data )
    if serializer.is_valid():
        user , error = AuthenticationService.register_user(
            email = serializer.validated_data['email'],
            password = serializer.validated_data['password'],
            first_name = serializer.validated_data['first_name'],
            last_name = serializer.validated_data['last_name'],
            role = serializer.validated_data['role']

        )
        if user:
            try:
                EmailVerificationService.send_verification_email(user)

            except Exception as e:
                return Response ({str(e)})

            auth_data, auth_error = AuthenticationService.authenticate_user(
                email = serializer.validated_data['email'],
                password = serializer.validated_data['password'],

            )

            if auth_data:
                AuthenticationService.update_user_status(auth_data['user'], is_online= True)
                return  Response({
                    'message': 'User registered successfully please check your email to verify your account ',
                    'user' : UserSerializer(auth_data['user']).data,
                    'access_token' : auth_data['access_token'],
                    'refresh_token' : auth_data['refresh_token'],

                },
                    status=status.HTTP_201_CREATED,
            )
            else:
                return Response({
                    'error' : f'Registration successful but login failed : {auth_error}'

                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response({
                'error': error,

            }, status.HTTP_400_BAD_REQUEST)
    return  Response(serializer.errors, status = status.HTTP_400_BAD_REQUEST)

@api_view(['Post'])
@permission_classes([AllowAny])
def login(request):
    serializer = LoginSerailizers(data = request.data)
    if serializer.is_valid():
        auth_data, error = AuthenticationService.authenticate_user(
            email = serializer.validated_data['email'],
            password = serializer.validated_data['password'],

        )

        if auth_data:
            AuthenticationService.update_user_status(auth_data['user'], is_online = True)

            return  Response(
                {
                    'message': 'Login successful',
                    'user' : UserSerializer(auth_data['user']).data,
                    'access_token' : auth_data['access_token'],
                    'refresh_token' : auth_data['refresh_token'],

            }, status = status.HTTP_200_OK,)
        else:
            return  Response({
                'error' : error,

            }, status= status.HTTP_401_UNAUTHORIZED)
    return Response(serializer.errors, status = status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    try:
        refresh_token = request.data.get['refresh_token'],
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except (TokenError, InvalidToken):
                pass
        AuthenticationService.update_user_status(request.user, is_online = False)

        return  Response({
            'message' : 'Logout successful',

        },
            status= status.HTTP_200_OK,
        )
    except Exception as e:
        AuthenticationService.update_user_status(request.user, is_online = False)
        return  Response({
            'message': 'logged out successfully',

        }, status= status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def validate_token(request):
    try:
        user = request.user
        # Mark user as online since they have a valid token and are actively using the app
        AuthenticationService.update_user_status(user, is_online=True)

        return Response({
            'valid': True,
            'user': UserSerializer(user).data,
            'message': 'Token is valid'
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'valid': False, 'error': 'Token validation failed', 'message': str(e)
        }, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    return  Response({
        'user' : UserSerializer(request.user).data
    }, status=status.HTTP_200_OK
    )

@api_view(['POST'])
@permission_classes([AllowAny])
def token_refresh_custom(request):
    try:
        refresh_token = request.data.get['refresh_token']

        if not refresh_token:
            return  Response({
                'error' : 'Refresh token required'

            }, status= status.HTTP_400_BAD_REQUEST)
        try:
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)

            user_id = refresh.payload.get('user_id')
            user = User.objects.get(id = user_id)

            AuthenticationService.update_user_status(user, is_online = True)

            return  Response({
                'access' : access_token,
                'user' : UserSerializer(user).data,

            }, status= status.HTTP_200_OK)

        except (TokenError, InvalidToken, User.DoesNotExist) as e:
            return Response({
                'error' : 'Invalid refresh token',
                'message' : str(e)

            }, status= status.HTTP_401_UNAUTHORIZED)
    except Exception as e:
        return  Response({
            'error' : 'Token refresh failed',
            'message': str(e)

        },status= status.HTTP_500_INTERNAL_SERVER_ERROR,)

'''
@api_view(['POST'])
@permission_classes([AllowAny])
def verify_email(request,token):
    serializer = EmailVerificationSerializer(data = request.data)
    if serializer.is_valid():
        token = serializer.validated_data['token']
        user, error = EmailVerificationService.verify_email_token(token)
        if user:
            return Response({
                'message': 'Email verified successfully',
                'user': UserSerializer(user).data,
                'verified': True,

            }, status=status.HTTP_200_OK)

        else:
            return Response({
                'error': error, 'verified': False,

            }, status=status.HTTP_400_BAD_REQUEST)
            
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    '''
    

@api_view(['GET'])
@permission_classes([AllowAny])
def verify_email_details(request, token):
    """
    GET endpoint to fetch user details from verification token
    Used to display user information on the verification page
    """
    try:
        verification_token = EmailVerificationToken.objects.get(token=token)
        
        if not verification_token.is_valid:
            if verification_token.is_expired:
                error_msg = "Verification link has expired. Please request a new verification email."
            else:
                error_msg = "Verification link has already been used."
            return Response({
                'error': error_msg,
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = verification_token.user
        return Response({
            'user': UserSerializer(user).data,
            'verified': user.is_verified,
        }, status=status.HTTP_200_OK)
        
    except EmailVerificationToken.DoesNotExist:
        return Response({
            'error': 'Invalid or expired verification link',
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({
            'error': f'Failed to fetch verification details: {str(e)}',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_email(request, token):
    # We use 'token' directly from the function argument (the URL)
    user, error = EmailVerificationService.verify_email_token(token)

    if user:
        return Response({
            'message': 'Email verified successfully',
            'user': UserSerializer(user).data,
            'verified': True,
        }, status=status.HTTP_200_OK)

    # If 'user' is None, return the error message from your service
    return Response({
        'error': error,
        'verified': False,
    }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def resend_verification_email(request):
    serializer = ResendVerificationSerializer(data = request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']

        try:
            user = User.objects.get(email = email)
            success, message = EmailVerificationService.resend_verification_email(user)

            if success:
                return  Response({
                    'message' : message,
                    'email_sent' : True,
                }, status=status.HTTP_200_OK)

            else:
                return Response({
                    'error': message,
                    'email_sent' : False
                }, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({
                'error': 'User this email does not exist',
                'email_sent' : False
            }, status=status.HTTP_404_NOT_FOUND)

    return  Response(serializer.errors, status = status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_verification_email_authenticated(request):
    user = request.user

    if user.is_verified:
        return Response({
            'error' : 'Email is already verified',
            'email_sent' : False

        }, status=status.HTTP_400_BAD_REQUEST)

    success, message = EmailVerificationService.resend_verification_email(user)
    if success:
        return Response({
            'message' : message,
            'email_sent' : True
        }, status=status.HTTP_200_OK)

    else:
        return  Response({
            'error': message,
            'email_sent' : False

        }, status=status.HTTP_400_BAD_REQUEST)



 