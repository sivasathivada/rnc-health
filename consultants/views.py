
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from django.db import transaction
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from .serializers import (
    ConsultantAvailabilitySerializer,
    SpecialitySerializer,
    ConsultantProfileDetailSerializer,
    ConsultantProfileCreateSerializer,
    ConsultantProfileUpdateSerializer,
    ConsultantProfileListSerializer,
    ConsulatantReviewCreateSerializer)

from .models import Speciality, ConsultantProfile, ConsultantAvailability
from .services import ConsultantService
from django.contrib.auth import  get_user_model

# write your views here

class ConsultantPagination(PageNumberPagination):
    page_size = 10
    page_size_query_description = "page_10"
    max_page_size = 50
    
@api_view(['GET'])
@permission_classes([AllowAny])
def consultant_list(request):
    """ Get list of consultants with filtering and pagination """
    
    search_query = request.GET.get('search')
    Speciality_id = request.GET.get('speciality_id')
    is_online_only = request.GET.get('online_only', '').lower() == 'true'
    is_available_only = request.GET.get('available_only', 'true').lower() == 'true'
    
    Consultants_queryset = ConsultantService.get_consultants_queryset(
    search_query = search_query,
    speciality_id = Speciality_id,
    is_online_only = is_online_only,
    is_available_only = is_available_only,
    
    )
    
    # Paginate the queryset (correct signature: queryset, request)
    paginator = ConsultantPagination()
    page = paginator.paginate_queryset(Consultants_queryset, request)
    
    if page is not None:
        serializer = ConsultantProfileListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)
    
    # Fallback without pagination
    serializer = ConsultantProfileListSerializer(
        Consultants_queryset, many=True, context={"request": request}
    )
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([AllowAny])
def consultant_detail(request, consultant_id):
    """ Get detailed consultant information """
    consultant, error = ConsultantService.get_consultant_details(consultant_id)
    
    if consultant:
        serializer = ConsultantProfileDetailSerializer(consultant, context = {'request' : request})
        return Response(serializer.data)
    else:
        return Response({'error' : error }, status=status.HTTP_404_NOT_FOUND)
    
    
@api_view(['GET'])
@permission_classes([AllowAny])
def specialities_list(request):
    """ Get list of all active specialities """
    specialities = Speciality.objects.filter(is_active = True)
    serializer = SpecialitySerializer(specialities, many = True)
    
    return Response(serializer.data)


# Consultant - specific views (require authentication )
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_consultant_profile(request):
    ''' Create consultant profile '''
    
    if request.user.role != "consultant":
        return Response(
            {"error": "Only users with consultant role can create consultant profiles"},
            status=status.HTTP_403_FORBIDDEN)
              
    if hasattr(request.user, "consultant_profile"):
        return Response(
            {"error": "Consultant profile already exists"},
            status=status.HTTP_400_BAD_REQUEST)
            
    serializer = ConsultantProfileCreateSerializer(data = request.data)
    if serializer.is_valid():
        Speciality_id = serializer.validated_data.pop('speciality_id')
        profile, error = ConsultantService.create_consultant_profile(
            user = request.user,
            speciality_id = Speciality_id, 
            **serializer.validated_data
        )
        
        if profile:
            response_serializer = ConsultantProfileDetailSerializer(profile, context = {"request" : request})
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
            
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def consultant_profile(request):
    """ Get or update authenticated consultant's profile """
    
    if request.user.role != 'consultant':
        return Response(
            {'error': "Only consultants can access this endpoint"},
            status=status.HTTP_403_FORBIDDEN,
        )
    
    try:
        profile = request.user.consultant_profile
    except ConsultantProfile.DoesNotExist:
        return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # ── GET: return the consultant's full profile ──────────────────────────
    if request.method == 'GET':
        serializer = ConsultantProfileDetailSerializer(profile, context={'request': request})
        return Response(serializer.data)
    
    # ── PUT: update the consultant's profile ───────────────────────────────
    if request.method == 'PUT':
        if not request.data:
            return Response(
                {'error': 'No data provided for update'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = ConsultantProfileDetailSerializer(
            profile, data=request.data, partial=True, context={'request': request}
        )
        if serializer.is_valid():
            updated_profile, error = ConsultantService.update_consultant_profile(
                user=request.user,
                profile_data=serializer.validated_data
            )
            if updated_profile:
                response_serializer = ConsultantProfileDetailSerializer(
                    updated_profile, context={'request': request}
                )
                return Response(response_serializer.data)
            else:
                return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_consultant_avatar(request):
    """" Update consultant avatar """
    if request.user.role != "consultant":
        return Response(
            {"error": "Only consultants can update avatar "}, status= status.HTTP_403_FORBIDDEN,
            
        )
    if "avatar" not in request.FILES:
        return Response(
            {"error": "No avatar file provided"},
            status=status.HTTP_400_BAD_REQUEST
        )
        
    avatar_file = request.FILES['avatar']
    
    if avatar_file.size > 5 * 1024 * 1024:
        return Response({'error': 'File size too large, Maximum allowed size is 5MB'},
                        status=status.HTTP_400_BAD_REQUEST
        )
        
    if not avatar_file.content_type.startswith('image/'):
        return Response({'error': 'File must be an image'}, 
                        status=status.HTTP_400_BAD_REQUEST)
        
    profile, error = ConsultantService.update_consultant_avatar(request.user, avatar_file)
    
    if profile:
        # Build absolute URL so the frontend can display the image immediately
        avatar_url = request.build_absolute_uri(profile.avatar.url) if profile.avatar else None
        return Response({
            'message': 'Avatar updated successfully',
            'avatar_url': avatar_url
        })
    else:
        return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_consultant_review(request, consultant_id):
    """ Add a review for a consultant """
    
    if request.user.role != 'patient':
        return Response({'error': " Only patients are allowed to write review "}, 
                        status=status.HTTP_403_FORBIDDEN )
    serializer = ConsulatantReviewCreateSerializer(data = request.data)
    
    if serializer.is_valid():
        review, error = ConsultantService.add_review(consultant_id= consultant_id,
                        patient_user= request.user,
                        rating = serializer.validated_data['rating'],
                        review_text=serializer.validated_data.get('review_text', ''),
                        is_verified=False,
        )
        
        if review:
            return Response(
                {"message" : "Review added successfully"},status=status.HTTP_200_OK)
        else:
            return Response({"error": error}, status= status.HTTP_400_BAD_REQUEST)
        
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



'''
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def consultant_availability(request):
    """ Get or set consultant availability schedule"""
    
    # Allow Patients to GET, but only Consultants to POST
    if request.method == 'POST' and request.user.role != "consultant":
        return Response({"error": "Only consultants can manage availability"}, status=403)

    try:
        profile = request.user.consultant_profile
    except Exception:
        return Response({"error": 'Consultant profile not found'}, status=404)

    if request.method == 'GET':
        availability_slots = ConsultantAvailability.objects.filter(consultant=profile).order_by('day_of_week', 'start_time')
        serializer = ConsultantAvailabilitySerializer(availability_slots, many=True)
        return Response({'is_available': profile.is_available, 'availability_slots': serializer.data})

    elif request.method == 'POST':
        # FIX: Robust parsing to avoid 'list' object has no attribute 'get'
        if isinstance(request.data, list):
            schedule_data = request.data
        elif isinstance(request.data, dict):
            schedule_data = request.data.get('schedule', [request.data])
            # If 'schedule' was a single dict, wrap it in a list
            if isinstance(schedule_data, dict):
                schedule_data = [schedule_data]
        else:
            return Response({'error': 'Invalid data format'}, status=400)

        # Final check: schedule_data must be a list for the loop/service
        if not isinstance(schedule_data, list):
            return Response({'error': 'Data must be a list of slots'}, status=400)

        # Call the service to handle the DB logic
        updated_profile, error = ConsultantService.availability_schedule(request.user, schedule_data)
        
        if updated_profile:
            # Re-fetch the newly saved slots to return to the frontend
            new_slots = ConsultantAvailability.objects.filter(consultant=profile).order_by('day_of_week', 'start_time')
            serializer = ConsultantAvailabilitySerializer(new_slots, many=True)
            return Response({
                'message': 'Availability schedule updated successfully', 
                'availability': serializer.data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({'error': error or "Failed to save schedule"}, status=400)

'''

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def consultant_availability(request):
    """ Get or set consultant availability schedule """
    import logging
    logger = logging.getLogger(__name__)
    
    # 1. Identity & Profile Check
    try:
        profile = request.user.consultant_profile
    except Exception as e:
        logger.error(f"Consultant profile not found for user {request.user.id}: {str(e)}")
        return Response(
            {"error": "Consultant profile not found. Ensure you are logged in as a consultant."}, 
            status=status.HTTP_404_NOT_FOUND
        )

    # --- GET LOGIC ---
    if request.method == 'GET':
        try:
            availability_slots = ConsultantAvailability.objects.filter(
                consultant=profile
            ).order_by('day_of_week', 'start_time')
            
            serializer = ConsultantAvailabilitySerializer(availability_slots, many=True)
            logger.info(f"Retrieved {availability_slots.count()} availability slots for consultant {profile.id}")
            
            return Response({
                'is_available': profile.is_available,
                'availability_slots': serializer.data,
                'total_slots': availability_slots.count()
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error retrieving slots for consultant {profile.id}: {str(e)}", exc_info=True)
            return Response({
                'error': f"Error retrieving availability slots: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # --- POST LOGIC ---
    elif request.method == 'POST':
        logger.info(f"Availability POST request from consultant {profile.id} with data: {request.data}")
        
        # Ensure only consultants can save
        if request.user.role != "consultant":
            return Response(
                {"error": "Only users with the 'consultant' role can save availability."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # 2. Data Parsing Check
        schedule_data = request.data.get('schedule') if isinstance(request.data, dict) else request.data
        
        if not schedule_data:
            logger.warning(f"Empty schedule data received for consultant {profile.id}")
            return Response(
                {"error": "No schedule data received", 
                 "hint": "Send either a list of slots or {'schedule': [slots]}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Convert dict to list if single slot sent
        if isinstance(schedule_data, dict):
            schedule_data = [schedule_data]
        
        if not isinstance(schedule_data, list) or len(schedule_data) == 0:
            logger.warning(f"Invalid schedule data format for consultant {profile.id}: {type(schedule_data)}")
            return Response(
                {"error": "Schedule must be a non-empty list of availability slots"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Call Service Layer
        try:
            logger.info(f"Calling availability_schedule service for consultant {profile.id} with {len(schedule_data)} slots")
            updated_profile, error = ConsultantService.availability_schedule(request.user, schedule_data)
            
            if updated_profile:
                # ✅ SUCCESS: Re-fetch from DB to verify it actually saved
                saved_slots = ConsultantAvailability.objects.filter(
                    consultant=profile
                ).order_by('day_of_week', 'start_time')
                
                serializer = ConsultantAvailabilitySerializer(saved_slots, many=True)
                logger.info(f"✅ Successfully saved {saved_slots.count()} availability slots for consultant {profile.id}")
                
                return Response({
                    'message': 'Availability schedule updated successfully',
                    'status': 'success',
                    'slots_saved': saved_slots.count(),
                    'availability_slots': serializer.data,
                    'consultant_id': str(profile.id)
                }, status=status.HTTP_201_CREATED)
            else:
                # ❌ SERVICE ERROR
                logger.error(f"Service error for consultant {profile.id}: {error}")
                return Response(
                    {"error": f"Failed to save schedule: {error}", 
                     "status": "failed"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

        except Exception as e:
            # ❌ UNEXPECTED ERROR
            logger.error(f"Unexpected error during availability save for consultant {profile.id}: {str(e)}", exc_info=True)
            return Response(
                {"error": f"Server error during save: {str(e)}", 
                 "status": "error"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

'''
@api_view(['PATCH']) # Use PATCH for partial updates
@permission_classes([IsAuthenticated])
def toggle_consultant_availability(request):
    """ Set consultant online/offline status explicitly """
    
    if request.user.role != 'consultant':
        return Response({'error': "Only consultants can toggle availability"}, 
                        status=status.HTTP_403_FORBIDDEN)

    try:
        profile = request.user.consultant_profile
        
        # Get 'is_available' from request body, or default to the flip logic if not provided
        requested_status = request.data.get('is_available')
        
        if requested_status is not None:
            profile.is_available = requested_status
        else:
            profile.is_available = not profile.is_available
            
        profile.save(update_fields=['is_available'])
        
        return Response({
            'message': f'Availability set to {"online" if profile.is_available else "offline"}', 
            'is_available': profile.is_available
        }, status=status.HTTP_200_OK)        
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)




'''

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def toggle_consultant_availability(request):
    """ Toggle consultant online/offline status"""
    
    if request.user.role != 'consultant':
         return Response({'error': "only consultants can toggle availability"}, 
                        status=status.HTTP_403_FORBIDDEN)

    
    try:
        profile = request.user.consultant_profile
        profile.is_available = not profile.is_available
        profile.save(update_fields = ['is_available'])
        
        return Response({'message': f'Availability set to {"online" if profile.is_available else "offline"}', 
                        'is_available': profile.is_available})        
        
    except ConsultantProfile.DoesNotExist:
        return Response({'error': 'Consultant profile not Found' }, 
                        status=status.HTTP_404_NOT_FOUND )           

