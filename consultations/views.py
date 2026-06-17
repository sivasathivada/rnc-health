from rest_framework import generics, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
import logging
from .models import Appointment, CallSession, Prescription, AppointmentSlot
from .serializers import (
    AppointmentSerializer, AppointmentCreateSerializer, AppointmentUpdateSerializer,
    AppointmentCancelSerializer, CallSessionSerializer, AppointmentSlotSerializer,
    PrescriptionSerializer, PrescriptionCreateSerializer, PrescriptionUpdateSerializer
)
from .services import AppointmentService, PrescriptionService   # CallSessionService,
from consultants.models import ConsultantProfile

logger = logging.getLogger(__name__)


class IsConsultant(permissions.BasePermission):
    """Permission class to check if user is a consultant"""
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'role') and
            request.user.role == 'consultant'
        )


class IsPatient(permissions.BasePermission):
    """Permission class to check if user is a patient"""
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'role') and
            request.user.role == 'patient'
        )


class ConsultantAppointmentListView(generics.ListAPIView):
    """List appointments for a consultant"""
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated, IsConsultant]

    def get_queryset(self):
        consultant_profile = self.request.user.consultant_profile
        status_filter = self.request.query_params.get('status')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        return AppointmentService.get_consultant_appointments(
            consultant_profile, status_filter, date_from, date_to
        )


class ConsultantAppointmentDetailView(generics.RetrieveAPIView):
    """Get details of a specific appointment"""
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated, IsConsultant]

    def get_queryset(self):
        return Appointment.objects.filter(consultant=self.request.user.consultant_profile)


class ConsultantAppointmentUpdateView(generics.UpdateAPIView):
    """Update an appointment"""
    serializer_class = AppointmentUpdateSerializer
    permission_classes = [permissions.IsAuthenticated, IsConsultant]

    def get_queryset(self):
        return Appointment.objects.filter(consultant=self.request.user.consultant_profile)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            appointment = AppointmentService.update_appointment(
                instance, serializer.validated_data, request.user
            )
            response_serializer = AppointmentSerializer(appointment)
            return Response(response_serializer.data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ConsultantAppointmentCancelView(APIView):
    """Cancel an appointment"""
    permission_classes = [permissions.IsAuthenticated, IsConsultant]

    def post(self, request, pk):
        try:
             appointment = Appointment.objects.get(
                pk=pk,
                consultant=request.user.consultant_profile
            )
        except Appointment.DoesNotExist:
            return Response(
                {"error": "Appointment not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = AppointmentCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            AppointmentService.cancel_appointment(
                appointment, request.user, serializer.validated_data.get('cancellation_reason', '')
            )
            return Response({"message": "Appointment cancelled successfully"})
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ConsultantAppointmentConfirmView(APIView):
    """Confirm a pending appointment"""
    permission_classes = [permissions.IsAuthenticated, IsConsultant]

    def post(self, request, pk):
        try:
            # First, try to find the appointment at all
            try:
                appointment = Appointment.objects.get(pk=pk)
            except Appointment.DoesNotExist:
                logger.warning(f"Appointment with ID {pk} not found")
                return Response(
                    {"error": "Appointment not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Verify consultant owns this appointment
            if appointment.consultant != request.user.consultant_profile:
                logger.warning(f"Consultant {request.user.id} attempted to confirm appointment not owned by them")
                return Response(
                    {"error": "You do not have permission to modify this appointment"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Check if appointment is in pending status (case-insensitive for backwards compatibility)
            if appointment.status.lower() != 'pending':
                logger.warning(f"Cannot confirm appointment {pk} - status is '{appointment.status}', not 'pending'")
                return Response(
                    {"error": f"Cannot confirm appointment in '{appointment.status}' status. Only 'pending' appointments can be confirmed."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Confirm the appointment
            appointment = AppointmentService.confirm_appointment(appointment)
            serializer = AppointmentSerializer(appointment)
            logger.info(f"Appointment {pk} confirmed by consultant {request.user.id}")
            return Response(serializer.data)
            
        except ValidationError as e:
            logger.error(f"Validation error confirming appointment: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error confirming appointment {pk}: {str(e)}", exc_info=True)
            return Response(
                {"error": "An unexpected error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


from django.shortcuts import get_object_or_404

class ConsultantAvailableSlotsView(generics.ListAPIView):
    """Get available time slots for a consultant (Accessible by Patients and consultant)"""
    serializer_class = AppointmentSlotSerializer
    # Don't restrict to IsPatient only, allow consultants to view their own slots for testing
    permission_classes = [permissions.IsAuthenticated] 

    def get_queryset(self):
        # 1. Try to get consultant_id from URL params (for Patients)
        # 2. Fallback to the logged-in user's profile (for Consultants testing their own slots)
        consultant_id = self.request.query_params.get('consultant_id')
        date = self.request.query_params.get('date')

        if not date:
            logger.warning("No date provided in query params")
            return AppointmentSlot.objects.none()

        try:
            date_obj = timezone.datetime.strptime(date, '%Y-%m-%d').date()
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid date format: {date}. Expected YYYY-MM-DD. Error: {e}")
            return AppointmentSlot.objects.none()

        consultant = None
        if consultant_id:
            # Patient View: Fetch slots for the specific consultant requested
            try:
                # Try UUID lookup first (since ConsultantProfile uses UUID as PK)
                consultant = ConsultantProfile.objects.get(id=consultant_id)
            except ConsultantProfile.DoesNotExist:
                logger.warning(f"Consultant with ID {consultant_id} not found")
                return AppointmentSlot.objects.none()
        else:
            # Consultant View: Fallback to self
            if hasattr(self.request.user, 'consultant_profile'):
                consultant = self.request.user.consultant_profile
            else:
                logger.warning(f"User {self.request.user.id} does not have consultant profile")
                return AppointmentSlot.objects.none()

        if not consultant:
            return AppointmentSlot.objects.none()

        # Use your service to get the slots
        slots = AppointmentService.get_available_slots(consultant, date_obj)
        logger.info(f"Retrieved {slots.count()} available slots for consultant {consultant.id} on {date_obj}")
        return slots

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "available_slots": serializer.data
        })


class PatientAppointmentCreateView(generics.CreateAPIView):
    """Allow patients to book appointments with verified consultants"""
    serializer_class = AppointmentCreateSerializer
    permission_classes = [permissions.IsAuthenticated, IsPatient]

    def perform_create(self, serializer):
        serializer.save(patient=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
            appointment = serializer.instance
            response_serializer = AppointmentSerializer(appointment)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PatientAppointmentListView(generics.ListAPIView):
    """List appointments for the logged-in patient"""
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated, IsPatient]

    def get_queryset(self):
        status_filter = self.request.query_params.get('status')
        qs = Appointment.objects.filter(patient=self.request.user).select_related(
            'consultant', 'consultant__user', 'consultant__speciality'
        ).order_by('-scheduled_date', '-scheduled_time')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

class CallSessionListView(generics.ListAPIView):
    """List call sessions for the logged in user"""
    serializer_class = CallSessionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    from .services import ConsultationService
    def get_queryset(self):
        user = self.request.user
        status_filter = self.request.query_params.get('status')

        if hasattr(user, 'role') and user.role == 'consultant':
            consultant_profile = user.consultant_profile
            return self.ConsultationService.get_consultant_call_sessions(consultant_profile, status_filter)
        elif hasattr(user, 'role') and user.role == 'patient':
            from .models import CallSession
            queryset = CallSession.objects.filter(patient=user)
            if status_filter:
                queryset = queryset.filter(status=status_filter)
            return queryset.order_by('-created_at')
        return CallSession.objects.none()


class ConsultantCallSessionDetailView(generics.RetrieveAPIView):
    """Get details of a specific call session"""
    serializer_class = CallSessionSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'session_id'
    lookup_url_kwarg = 'session_id'

    def get_queryset(self):
        from django.db.models import Q
        return CallSession.objects.filter(
            Q(consultant=self.request.user) | Q(patient=self.request.user)
        )
'''

class ConsultantCallSessionStartView(APIView):
    """Start a call session"""
    permission_classes = [permissions.IsAuthenticated, IsConsultant]

    def post(self, request, pk):
        try:
            call_session = CallSession.objects.get(
                pk=pk,
                consultant=request.user
            )
        except CallSession.DoesNotExist:
            return Response(
                {"error": "Call session not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        try: 
            call_session = CallSessionService.start_call_session(call_session, request.user)
            serializer = CallSessionSerializer(call_session)
            return Response(serializer.data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ConsultantCallSessionEndView(APIView):
    """End a call session"""
    permission_classes = [permissions.IsAuthenticated, IsConsultant]

    def post(self, request, pk):
        try:
            call_session = CallSession.objects.get(
                pk=pk,
                consultant=request.user
            )
        except CallSession.DoesNotExist:
            return Response(
                {"error": "Call session not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        notes = request.data.get('consultant_notes', '')

        try:
            call_session = CallSessionService.end_call_session(call_session, request.user, notes)
            serializer = CallSessionSerializer(call_session)
            return Response(serializer.data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

'''

class ConsultantPrescriptionListView(generics.ListCreateAPIView):
    """List and create prescriptions for a consultant"""
    permission_classes = [permissions.IsAuthenticated, IsConsultant]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return PrescriptionCreateSerializer
        return PrescriptionSerializer

    def get_queryset(self):
        consultant = self.request.user
        status_filter = self.request.query_params.get('status')

        return PrescriptionService.get_consultant_prescriptions(consultant, status_filter)

    def perform_create(self, serializer):
        serializer.save()


class ConsultantPrescriptionDetailView(generics.RetrieveUpdateAPIView):
    """Get and update prescription details"""
    permission_classes = [permissions.IsAuthenticated, IsConsultant]
    serializer_class = PrescriptionUpdateSerializer

    def get_queryset(self):
        return Prescription.objects.filter(consultant=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = PrescriptionSerializer(instance)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            prescription = PrescriptionService.update_prescription(
                instance, request.user, serializer.validated_data
            )
            response_serializer = PrescriptionSerializer(prescription)
            return Response(response_serializer.data)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ConsultantSpecificSlotListCreateView(generics.ListCreateAPIView):
    """View to allow consultants to list and create specific-date appointment slots"""
    serializer_class = AppointmentSlotSerializer
    permission_classes = [permissions.IsAuthenticated, IsConsultant]

    def get_queryset(self):
        queryset = AppointmentSlot.objects.filter(consultant=self.request.user.consultant_profile)
        date = self.request.query_params.get('date')
        if date:
            queryset = queryset.filter(date=date)
        return queryset.order_by('date', 'start_time')

    def perform_create(self, serializer):
        serializer.save(consultant=self.request.user.consultant_profile)


class ConsultantSpecificSlotDeleteView(generics.DestroyAPIView):
    """View to allow consultants to delete a specific appointment slot"""
    serializer_class = AppointmentSlotSerializer
    permission_classes = [permissions.IsAuthenticated, IsConsultant]

    def get_queryset(self):
        return AppointmentSlot.objects.filter(consultant=self.request.user.consultant_profile)
