
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import models
import logging
from consultants.models import ConsultantProfile
from .serializers import CallSessionSerializer, CallInitiateRequestSerializer
from .models import Appointment, CallSession



logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_call(request):
    """ Start a new video/audio call request """
    
    print(f"Incoming Data: {request.data}")
    if request.user.role not in ['patient', 'consultant']:
        return Response({'error' : 'Only patients or consultants can initiate call'},
                status=status.HTTP_403_FORBIDDEN)
    serializer = CallInitiateRequestSerializer(data = request.data)
        
    if not serializer.is_valid():
        logger.error(f"Initiate Call Validation Failed: {serializer.errors}")
        return Response(serializer.errors,
                status = status.HTTP_400_BAD_REQUEST)
        
    call_type = serializer.validated_data.get('call_type', 'video')
    from .services import ConsultationService
    
    if request.user.role == 'patient':
        consultant_id = serializer.validated_data.get('consultant_id')
        if not consultant_id:
            return Response({'error': 'consultant_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            consultant_profile = ConsultantProfile.objects.select_related('user').get(
                id=consultant_id,
                user__role='consultant',
                user__is_active=True,
                is_verified=True
            )
            if not consultant_profile.is_available:
                return Response({'error' : "Consultant is currently offline"}, 
                            status=status.HTTP_400_BAD_REQUEST)
        except ConsultantProfile.DoesNotExist:
            return Response({'error': 'consultant not found or not available'},
                            status=status.HTTP_404_NOT_FOUND,
                        )
        call_session, error = ConsultationService.initiate_call(
                            consultant_id = consultant_id,
                            patient_user = request.user,
                            call_type = call_type,
                            initiated_by_role = 'patient'
                        )
    else:
        patient_id = serializer.validated_data.get('patient_id')
        if not patient_id:
            return Response({'error': 'patient_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            consultant_profile = request.user.consultant_profile
        except ConsultantProfile.DoesNotExist:
            return Response({'error': 'Consultant profile not found'}, status=status.HTTP_404_NOT_FOUND)
        call_session, error = ConsultationService.initiate_call(
                            consultant_id = consultant_profile.id,
                            patient_user = patient_id,
                            call_type = call_type,
                            initiated_by_role = 'consultant'
                        )
    
    if call_session:
        response_serializer = CallSessionSerializer(call_session)
        return Response(response_serializer.data, status = status.HTTP_201_CREATED)
    else:
        print(f"Service Logic Error: {error}")
        return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
    
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_call(request, session_id):
    """ Start call - Transition from Ringing to Active call """
    try:
        call_session = CallSession.objects.get(session_id = session_id)
        
        if request.user not in [call_session.consultant, call_session.patient]:
            return Response({'error': 'Access denied - you are not of this consultation'},
                            status=status.HTTP_403_FORBIDDEN)
    
        if call_session.status == 'ongoing':
            serializer = CallSessionSerializer(call_session)
            return Response(serializer.data)
        
        
        elif call_session.status not in ['initiated', 'scheduled']:
            return Response({'error': f"Cannot start call in {call_session.status} status"},
                status=status.HTTP_400_BAD_REQUEST)
  
        from .services import ConsultationService
        
        call_session, error = ConsultationService.start_call(session_id, request.user)
    
        if call_session:
            serializer = CallSessionSerializer(call_session)
            return Response(serializer.data)
        else:
            return Response({'error': error}, 
                            status=status.HTTP_400_BAD_REQUEST)
            
    except CallSession.DoesNotExist:
        return Response({'error' : f"Call session with  ID {session_id} not found .Please ensure you have initiated the call profile "}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({'error': 'An Unexpected error occured. please try again.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,)
        
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def end_call(request, session_id):
    """ End call = Terminate an ongoing Consultation """
    consultant_notes = request.data.get('consultant_notes', '')
    patient_feedback = request.data.get('patient_feedback', '')
    
    from .services import ConsultationService
    
    call_session, error = ConsultationService.end_call(session_id = session_id, user = request.user,
            consultant_notes=consultant_notes, patient_feedback=patient_feedback)

    if call_session:
            serializer = CallSessionSerializer(call_session)
            return Response(serializer.data)
    else:
        return Response({'error': error}, 
                        status=status.HTTP_400_BAD_REQUEST)

