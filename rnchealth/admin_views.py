from rest_framework import status, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from django.db import models
from django.db.models import Q
from django.contrib.auth import get_user_model

# Import models
from authentication.models import EmailVerificationToken
from consultants.models import ConsultantProfile, Speciality, ConsultantReview, ConsultantAvailability
from patients.models import PatientProfile, PatientMedicalHistory
from consultations.models import Appointment, CallSession, AppointmentSlot, Prescription
from payments.models import Payment, UserWallet, WalletTransaction, StripeEvent

User = get_user_model()

class IsPlatformAdmin(BasePermission):
    """Permission class to check if user is a platform admin (staff, superuser, or role='admin')"""
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            (request.user.is_staff or request.user.is_superuser or getattr(request.user, 'role', '') == 'admin')
        )

# ==================== SERIALIZERS ====================

class AdminUserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'full_name', 'role', 'is_active', 'is_staff', 'is_online', 'is_verified', 'last_seen', 'created_at']
        read_only_fields = ['id', 'is_online', 'last_seen', 'created_at', 'full_name']

class AdminSpecialitySerializer(serializers.ModelSerializer):
    consultants_count = serializers.SerializerMethodField()

    class Meta:
        model = Speciality
        fields = ['id', 'name', 'description', 'icon', 'is_active', 'created_at', 'consultants_count']
        read_only_fields = ['id', 'created_at']

    def get_consultants_count(self, obj):
        return obj.consultants.count()

class AdminConsultantProfileSerializer(serializers.ModelSerializer):
    user = AdminUserSerializer(read_only=True)
    speciality_name = serializers.CharField(source='speciality.name', read_only=True)
    speciality_id = serializers.IntegerField(source='speciality.id', read_only=True)
    speciality = serializers.PrimaryKeyRelatedField(queryset=Speciality.objects.all(), required=False, allow_null=True)

    class Meta:
        model = ConsultantProfile
        fields = [
            'id', 'user', 'speciality', 'speciality_id', 'speciality_name', 'bio', 'years_of_experience',
            'license_number', 'medical_degree', 'board_certifications', 'additional_qualifications',
            'phone_number', 'clinic_name', 'clinic_address', 'clinic_city', 'clinic_country',
            'consultation_fee', 'consultation_duration', 'consultation_types', 'languages_spoken',
            'is_available', 'rating', 'total_consultation', 'total_reviews', 'is_verified',
            'verification_date', 'is_featured', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'rating', 'total_consultation', 'total_reviews', 'verification_date', 'created_at', 'updated_at']

class AdminPatientProfileSerializer(serializers.ModelSerializer):
    user = AdminUserSerializer(read_only=True)
    age = serializers.IntegerField(read_only=True)
    medical_records_count = serializers.SerializerMethodField()

    class Meta:
        model = PatientProfile
        fields = [
            'id', 'user', 'avatar', 'bio', 'date_of_birth', 'gender', 'phone_number',
            'address', 'city', 'country', 'postal_code', 'emergency_contact_name',
            'emergency_contact_phone', 'emergency_contact_relationship', 'blood_type',
            'allergies', 'chronic_conditions', 'current_medications', 'share_medical_history',
            'allow_emergency_access', 'preferred_language', 'age', 'medical_records_count', 'created_at'
        ]
        read_only_fields = ['id', 'user', 'age', 'medical_records_count', 'created_at']

    def get_medical_records_count(self, obj):
        return obj.medical_history.count()

class AdminPatientMedicalHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientMedicalHistory
        fields = ['id', 'patient', 'record_type', 'title', 'description', 'date_occurred', 'healthcare_provider', 'attachments', 'created_at']
        read_only_fields = ['id', 'created_at']

class AdminAppointmentSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.full_name', read_only=True)
    patient_email = serializers.CharField(source='patient.email', read_only=True)
    consultant_name = serializers.SerializerMethodField()
    speciality_name = serializers.CharField(source='consultant.speciality.name', read_only=True)

    class Meta:
        model = Appointment
        fields = [
            'id', 'patient', 'patient_name', 'patient_email', 'consultant', 'consultant_name',
            'speciality_name', 'scheduled_date', 'scheduled_time', 'status', 'payment_status',
            'Appointment_type', 'reason_for_visit', 'consultation_fee'
        ]
        read_only_fields = ['id']

    def get_consultant_name(self, obj):
        if obj.consultant and obj.consultant.user:
            return f"Dr. {obj.consultant.user.full_name}"
        return "Unknown Consultant"

class AdminPaymentSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.full_name', read_only=True)
    patient_email = serializers.CharField(source='patient.email', read_only=True)
    appointment_details = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id', 'appointment', 'appointment_details', 'patient', 'patient_name', 'patient_email',
            'amount', 'Payment_method', 'status', 'transaction_id', 'created_at', 'completed_at',
            'refund_amount', 'refund_reason', 'refunded_at'
        ]

    def get_appointment_details(self, obj):
        if obj.appointment:
            c_name = f"Dr. {obj.appointment.consultant.user.full_name}" if obj.appointment.consultant else "N/A"
            return {
                "id": obj.appointment.id,
                "consultant": c_name,
                "date": str(obj.appointment.scheduled_date)
            }
        return None

class AdminUserWalletSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = UserWallet
        fields = ['user', 'user_name', 'user_email', 'balance', 'created_at', 'updated_at']

class AdminWalletTransactionSerializer(serializers.ModelSerializer):
    wallet_user = serializers.CharField(source='wallet.user.full_name', read_only=True)
    wallet_email = serializers.CharField(source='wallet.user.email', read_only=True)

    class Meta:
        model = WalletTransaction
        fields = ['id', 'wallet', 'wallet_user', 'wallet_email', 'transaction_type', 'amount', 'balance_after', 'description', 'reference', 'created_at']

class AdminEmailVerificationTokenSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = EmailVerificationToken
        fields = ['id', 'user', 'user_name', 'user_email', 'token', 'created_at', 'expires_at', 'is_used', 'is_expired']
        read_only_fields = ['id', 'token', 'created_at', 'expires_at', 'is_expired']

class AdminConsultantReviewSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.full_name', read_only=True)
    patient_email = serializers.CharField(source='patient.email', read_only=True)
    consultant_name = serializers.CharField(source='consultant.user.full_name', read_only=True)

    class Meta:
        model = ConsultantReview
        fields = ['id', 'consultant', 'consultant_name', 'patient', 'patient_name', 'patient_email', 'rating', 'review_text', 'is_verified_consultation', 'is_anonymous', 'created_at']
        read_only_fields = ['id', 'created_at']

class AdminConsultantAvailabilitySerializer(serializers.ModelSerializer):
    consultant_name = serializers.CharField(source='consultant.user.full_name', read_only=True)
    day_name = serializers.CharField(source='get_day_of_week_display', read_only=True)

    class Meta:
        model = ConsultantAvailability
        fields = ['id', 'consultant', 'consultant_name', 'day_of_week', 'day_name', 'start_time', 'end_time', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']

class AdminCallSessionSerializer(serializers.ModelSerializer):
    consultant_name = serializers.CharField(source='consultant.full_name', read_only=True)
    patient_name = serializers.CharField(source='patient.full_name', read_only=True)
    connection_health = serializers.CharField(read_only=True)
    duration_formatted = serializers.CharField(read_only=True)

    class Meta:
        model = CallSession
        fields = [
            'id', 'session_id', 'consultant', 'consultant_name', 'patient', 'patient_name',
            'call_type', 'status', 'scheduled_at', 'started_at', 'ended_at', 'duration_minutes',
            'duration_formatted', 'consultation_fee', 'payment_status', 'connection_type',
            'connection_quality', 'connection_health', 'webrtc_stats', 'offer_exchanged',
            'answer_exchanged', 'ice_candidates_count', 'reconnection_attempts',
            'consultant_notes', 'patient_feedback', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class AdminPrescriptionSerializer(serializers.ModelSerializer):
    consultant_name = serializers.CharField(source='consultant.full_name', read_only=True)
    patient_name = serializers.CharField(source='patient.full_name', read_only=True)

    class Meta:
        model = Prescription
        fields = ['id', 'call_seesion', 'consultant', 'consultant_name', 'patient', 'patient_name', 'medications', 'instructions', 'diagnosis', 'status', 'valid_until', 'created_at']
        read_only_fields = ['id', 'created_at']

class AdminAppointmentSlotSerializer(serializers.ModelSerializer):
    consultant_name = serializers.CharField(source='consultant.user.full_name', read_only=True)

    class Meta:
        model = AppointmentSlot
        fields = ['id', 'consultant', 'consultant_name', 'date', 'start_time', 'end_time', 'is_available', 'is_blocked', 'created_at']
        read_only_fields = ['id', 'created_at']

class AdminStripeEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = StripeEvent
        fields = ['id', 'stripe_event_id', 'stripe_charge_id', 'event_type', 'processed', 'payload', 'created_at', 'processed_at']
        read_only_fields = ['id', 'created_at']


# ==================== VIEW ENDPOINTS ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_stats(request):
    """Retrieve comprehensive platform metrics for dashboard overview"""
    total_patients = PatientProfile.objects.count()
    total_consultants = ConsultantProfile.objects.count()
    pending_verifications = ConsultantProfile.objects.filter(is_verified=False).count()
    total_appointments = Appointment.objects.count()
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    
    # Revenue aggregation
    revenue_data = Payment.objects.filter(status='completed').aggregate(total=models.Sum('amount'))
    total_revenue = float(revenue_data['total'] or 0.0)

    # Appointments by status
    status_counts = Appointment.objects.values('status').annotate(count=models.Count('id'))
    appointments_by_status = {item['status']: item['count'] for item in status_counts}

    # Revenue by payment method
    method_counts = Payment.objects.filter(status='completed').values('Payment_method').annotate(count=models.Count('id'), total=models.Sum('amount'))
    revenue_by_method = {item['Payment_method']: {"count": item['count'], "total": float(item['total'] or 0.0)} for item in method_counts}

    # Recent items
    recent_payments = Payment.objects.order_by('-created_at')[:5]
    recent_appointments = Appointment.objects.order_by('-scheduled_date', '-scheduled_time')[:5]

    return Response({
        'total_patients': total_patients,
        'total_consultants': total_consultants,
        'pending_verifications': pending_verifications,
        'total_appointments': total_appointments,
        'total_users': total_users,
        'active_users': active_users,
        'total_revenue': total_revenue,
        'appointments_by_status': appointments_by_status,
        'revenue_by_method': revenue_by_method,
        'recent_payments': AdminPaymentSerializer(recent_payments, many=True).data,
        'recent_appointments': AdminAppointmentSerializer(recent_appointments, many=True).data,
    }, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_users(request):
    """List or create users"""
    if request.method == 'GET':
        query = request.query_params.get('q', '').strip()
        role = request.query_params.get('role', '').strip()
        is_active = request.query_params.get('is_active', '').strip()

        queryset = User.objects.all().order_by('-created_at')

        if query:
            queryset = queryset.filter(
                Q(email__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            )
        if role:
            queryset = queryset.filter(role=role)
        if is_active:
            queryset = queryset.filter(is_active=(is_active.lower() == 'true'))

        serializer = AdminUserSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        serializer = AdminUserSerializer(data=request.data)
        if serializer.is_valid():
            user = User.objects.create_user(
                email=serializer.validated_data['email'],
                password=request.data.get('password', 'TemporaryPass123!'),
                first_name=serializer.validated_data.get('first_name', ''),
                last_name=serializer.validated_data.get('last_name', ''),
                role=serializer.validated_data.get('role', 'patient'),
                is_active=serializer.validated_data.get('is_active', True),
                is_staff=serializer.validated_data.get('is_staff', False)
            )
            return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_user_detail(request, pk):
    """Modify or delete user"""
    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PATCH':
        serializer = AdminUserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        user.is_active = False
        user.save()
        return Response({"message": "User deactivated successfully"}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_consultants(request):
    """List all consultant profiles"""
    query = request.query_params.get('q', '').strip()
    is_verified = request.query_params.get('is_verified', '').strip()

    queryset = ConsultantProfile.objects.all().select_related('user', 'speciality').order_by('-created_at')

    if query:
        queryset = queryset.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(speciality__name__icontains=query) |
            Q(license_number__icontains=query)
        )
    if is_verified:
        queryset = queryset.filter(is_verified=(is_verified.lower() == 'true'))

    serializer = AdminConsultantProfileSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_consultant_detail(request, pk):
    """Update consultant profile details (verify, toggle available/featured)"""
    try:
        profile = ConsultantProfile.objects.get(pk=pk)
    except (ConsultantProfile.DoesNotExist, ValueError):
        return Response({"error": "Consultant profile not found"}, status=status.HTTP_404_NOT_FOUND)

    is_verified_before = profile.is_verified
    serializer = AdminConsultantProfileSerializer(profile, data=request.data, partial=True)
    if serializer.is_valid():
        updated_profile = serializer.save()
        if 'is_verified' in request.data and request.data['is_verified'] and not is_verified_before:
            updated_profile.verification_date = timezone.now()
            updated_profile.save(update_fields=['verification_date'])
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_patients(request):
    """List all patient profiles"""
    # Auto-create missing profiles for users with role='patient'
    from authentication.models import User
    patients_without_profile = User.objects.filter(role='patient').exclude(patient_profile__isnull=False)
    for u in patients_without_profile:
        try:
            PatientProfile.objects.get_or_create(user=u)
        except Exception:
            pass

    query = request.query_params.get('q', '').strip()

    queryset = PatientProfile.objects.all().select_related('user').order_by('-created_at')

    if query:
        queryset = queryset.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(city__icontains=query)
        )

    serializer = AdminPatientProfileSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_patient_medical_history(request, pk):
    """Retrieve medical history records of a specific patient profile"""
    try:
        patient = PatientProfile.objects.get(pk=pk)
    except (PatientProfile.DoesNotExist, ValueError):
        return Response({"error": "Patient profile not found"}, status=status.HTTP_404_NOT_FOUND)

    records = PatientMedicalHistory.objects.filter(patient=patient).order_by('-date_occurred')
    serializer = AdminPatientMedicalHistorySerializer(records, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_medical_history(request):
    """List all medical history records or create a new one"""
    if request.method == 'GET':
        query = request.query_params.get('q', '').strip()
        queryset = PatientMedicalHistory.objects.all().select_related('patient__user').order_by('-date_occurred')
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query) |
                Q(healthcare_provider__icontains=query) |
                Q(patient__user__first_name__icontains=query) |
                Q(patient__user__last_name__icontains=query)
            )
        serializer = AdminPatientMedicalHistorySerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        serializer = AdminPatientMedicalHistorySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_medical_history_detail(request, pk):
    """Update or delete a medical history record"""
    try:
        record = PatientMedicalHistory.objects.get(pk=pk)
    except PatientMedicalHistory.DoesNotExist:
        return Response({"error": "Medical history record not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PATCH':
        serializer = AdminPatientMedicalHistorySerializer(record, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        record.delete()
        return Response({"message": "Medical history record deleted"}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_appointments(request):
    """List appointments with optional search and status filter"""
    query = request.query_params.get('q', '').strip()
    status_filter = request.query_params.get('status', '').strip()

    queryset = Appointment.objects.all().select_related(
        'patient', 'consultant__user', 'consultant__speciality'
    ).order_by('-scheduled_date', '-scheduled_time')

    if query:
        queryset = queryset.filter(
            Q(patient__first_name__icontains=query) |
            Q(patient__last_name__icontains=query) |
            Q(patient__email__icontains=query) |
            Q(consultant__user__first_name__icontains=query) |
            Q(consultant__user__last_name__icontains=query)
        )
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    serializer = AdminAppointmentSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_appointment_detail(request, pk):
    """Update appointment details (status, cancellation reason)"""
    try:
        appointment = Appointment.objects.get(pk=pk)
    except Appointment.DoesNotExist:
        return Response({"error": "Appointment not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = AdminAppointmentSerializer(appointment, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_payments(request):
    """List payments"""
    queryset = Payment.objects.all().select_related('appointment__consultant__user', 'patient').order_by('-created_at')
    serializer = AdminPaymentSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_wallets(request):
    """List user wallets"""
    queryset = UserWallet.objects.all().select_related('user').order_by('-updated_at')
    serializer = AdminUserWalletSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_wallet_transactions(request):
    """List wallet transactions"""
    queryset = WalletTransaction.objects.all().select_related('wallet__user').order_by('-created_at')
    serializer = AdminWalletTransactionSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_specialities(request):
    """List or create specialities"""
    if request.method == 'GET':
        queryset = Speciality.objects.all().order_by('name')
        serializer = AdminSpecialitySerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        serializer = AdminSpecialitySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_speciality_detail(request, pk):
    """Update or soft-delete speciality"""
    try:
        speciality = Speciality.objects.get(pk=pk)
    except Speciality.DoesNotExist:
        return Response({"error": "Speciality not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PUT':
        serializer = AdminSpecialitySerializer(speciality, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        speciality.is_active = not speciality.is_active
        speciality.save()
        return Response({"message": "Speciality status toggled successfully", "is_active": speciality.is_active}, status=status.HTTP_200_OK)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_patient_detail(request, pk):
    """Modify or delete patient profile"""
    try:
        profile = PatientProfile.objects.get(pk=pk)
    except PatientProfile.DoesNotExist:
        return Response({"error": "Patient profile not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PATCH':
        serializer = AdminPatientProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        if profile.user:
            profile.user.is_active = False
            profile.user.save()
        profile.delete()
        return Response({"message": "Patient profile deleted successfully"}, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_email_tokens(request):
    """List or create verification tokens"""
    if request.method == 'GET':
        query = request.query_params.get('q', '').strip()
        queryset = EmailVerificationToken.objects.all().select_related('user').order_by('-created_at')
        if query:
            queryset = queryset.filter(user__email__icontains=query)
        serializer = AdminEmailVerificationTokenSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        serializer = AdminEmailVerificationTokenSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_email_token_detail(request, pk):
    """Update or delete email verification token"""
    try:
        token_obj = EmailVerificationToken.objects.get(pk=pk)
    except EmailVerificationToken.DoesNotExist:
        return Response({"error": "Verification token not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PATCH':
        serializer = AdminEmailVerificationTokenSerializer(token_obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        token_obj.delete()
        return Response({"message": "Verification token deleted successfully"}, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_consultant_reviews(request):
    """List or create consultant reviews"""
    if request.method == 'GET':
        query = request.query_params.get('q', '').strip()
        queryset = ConsultantReview.objects.all().select_related('consultant__user', 'patient').order_by('-created_at')
        if query:
            queryset = queryset.filter(
                Q(consultant__user__first_name__icontains=query) |
                Q(consultant__user__last_name__icontains=query) |
                Q(patient__first_name__icontains=query) |
                Q(patient__last_name__icontains=query)
            )
        serializer = AdminConsultantReviewSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        serializer = AdminConsultantReviewSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_consultant_review_detail(request, pk):
    """Update or delete review"""
    try:
        review = ConsultantReview.objects.get(pk=pk)
    except ConsultantReview.DoesNotExist:
        return Response({"error": "Review not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PATCH':
        serializer = AdminConsultantReviewSerializer(review, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        review.delete()
        return Response({"message": "Review deleted successfully"}, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_consultant_availabilities(request):
    """List or create consultant availabilities"""
    if request.method == 'GET':
        query = request.query_params.get('q', '').strip()
        queryset = ConsultantAvailability.objects.all().select_related('consultant__user').order_by('day_of_week', 'start_time')
        if query:
            queryset = queryset.filter(
                Q(consultant__user__first_name__icontains=query) |
                Q(consultant__user__last_name__icontains=query)
            )
        serializer = AdminConsultantAvailabilitySerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        serializer = AdminConsultantAvailabilitySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_consultant_availability_detail(request, pk):
    """Update or delete availability slot"""
    try:
        availability = ConsultantAvailability.objects.get(pk=pk)
    except ConsultantAvailability.DoesNotExist:
        return Response({"error": "Availability not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PATCH':
        serializer = AdminConsultantAvailabilitySerializer(availability, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        availability.delete()
        return Response({"message": "Availability rule deleted successfully"}, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_call_sessions(request):
    """List or create call sessions"""
    if request.method == 'GET':
        query = request.query_params.get('q', '').strip()
        queryset = CallSession.objects.all().select_related('consultant', 'patient').order_by('-created_at')
        if query:
            queryset = queryset.filter(
                Q(session_id__icontains=query) |
                Q(consultant__first_name__icontains=query) |
                Q(consultant__last_name__icontains=query) |
                Q(patient__first_name__icontains=query) |
                Q(patient__last_name__icontains=query)
            )
        serializer = AdminCallSessionSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        serializer = AdminCallSessionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_call_session_detail(request, pk):
    """Update or delete call session"""
    try:
        session = CallSession.objects.get(pk=pk)
    except CallSession.DoesNotExist:
        return Response({"error": "Call session not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PATCH':
        serializer = AdminCallSessionSerializer(session, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        session.delete()
        return Response({"message": "Call session deleted successfully"}, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_prescriptions(request):
    """List or create prescriptions"""
    if request.method == 'GET':
        query = request.query_params.get('q', '').strip()
        queryset = Prescription.objects.all().select_related('consultant', 'patient').order_by('-created_at')
        if query:
            queryset = queryset.filter(
                Q(consultant__first_name__icontains=query) |
                Q(consultant__last_name__icontains=query) |
                Q(patient__first_name__icontains=query) |
                Q(patient__last_name__icontains=query) |
                Q(instructions__icontains=query)
            )
        serializer = AdminPrescriptionSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        serializer = AdminPrescriptionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_prescription_detail(request, pk):
    """Update or delete prescription"""
    try:
        prescription = Prescription.objects.get(pk=pk)
    except Prescription.DoesNotExist:
        return Response({"error": "Prescription not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PATCH':
        serializer = AdminPrescriptionSerializer(prescription, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        prescription.delete()
        return Response({"message": "Prescription deleted successfully"}, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_appointment_slots(request):
    """List or create appointment slots"""
    if request.method == 'GET':
        query = request.query_params.get('q', '').strip()
        queryset = AppointmentSlot.objects.all().select_related('consultant__user').order_by('-date', '-start_time')
        if query:
            queryset = queryset.filter(
                Q(consultant__user__first_name__icontains=query) |
                Q(consultant__user__last_name__icontains=query)
            )
        serializer = AdminAppointmentSlotSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        serializer = AdminAppointmentSlotSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_appointment_slot_detail(request, pk):
    """Update or delete appointment slot"""
    try:
        slot = AppointmentSlot.objects.get(pk=pk)
    except AppointmentSlot.DoesNotExist:
        return Response({"error": "Appointment slot not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PATCH':
        serializer = AdminAppointmentSlotSerializer(slot, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        slot.delete()
        return Response({"message": "Appointment slot deleted successfully"}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_stripe_events(request):
    """List Stripe webhook events"""
    query = request.query_params.get('q', '').strip()
    queryset = StripeEvent.objects.all().order_by('-created_at')
    if query:
        queryset = queryset.filter(
            Q(stripe_event_id__icontains=query) |
            Q(event_type__icontains=query)
        )
    serializer = AdminStripeEventSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsPlatformAdmin])
def admin_analytics(request):
    """Analytics endpoint for charts — monthly appointment counts and revenue trends"""
    from django.db.models.functions import TruncMonth
    import datetime

    # Last 6 months of appointment counts — use scheduled_date (Appointment has no created_at)
    six_months_ago = timezone.now() - datetime.timedelta(days=180)
    six_months_ago_date = six_months_ago.date()
    monthly_appointments = (
        Appointment.objects
        .filter(scheduled_date__gte=six_months_ago_date)
        .annotate(month=TruncMonth('scheduled_date'))
        .values('month', 'status')
        .annotate(count=models.Count('id'))
        .order_by('month')
    )

    # Monthly revenue
    monthly_revenue = (
        Payment.objects
        .filter(status='completed', created_at__gte=six_months_ago)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=models.Sum('amount'))
        .order_by('month')
    )

    # Top specialities by appointment count
    from consultants.models import Speciality
    top_specialities = (
        Appointment.objects
        .values('consultant__speciality__name')
        .annotate(count=models.Count('id'))
        .order_by('-count')[:5]
    )

    return Response({
        'monthly_appointments': list(monthly_appointments),
        'monthly_revenue': [
            {'month': item['month'], 'total': float(item['total'] or 0)}
            for item in monthly_revenue
        ],
        'top_specialities': list(top_specialities),
        'consultant_verification_rate': {
            'verified': ConsultantProfile.objects.filter(is_verified=True).count(),
            'unverified': ConsultantProfile.objects.filter(is_verified=False).count(),
        },
        'user_role_distribution': {
            item['role']: item['count']
            for item in User.objects.values('role').annotate(count=models.Count('id'))
        },
        'payment_status_distribution': {
            item['status']: item['count']
            for item in Payment.objects.values('status').annotate(count=models.Count('id'))
        },
    }, status=status.HTTP_200_OK)
