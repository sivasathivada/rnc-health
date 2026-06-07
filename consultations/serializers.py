
from rest_framework import serializers
from .models import CallSession, Prescription , Appointment, AppointmentSlot
from consultants.serializers import ConsultantProfileCreateSerializer
from rest_framework.exceptions import ValidationError
from consultants.models import ConsultantProfile


class CallInitiateRequestSerializer(serializers.Serializer):
    consultant_id = serializers.UUIDField(required=False)
    patient_id = serializers.UUIDField(required=False)
    call_type = serializers.ChoiceField(choices = CallSession.CAll_TYPE_CHOICES, default = 'video')


class CallSessionSerializer(serializers.ModelSerializer):
    consultant_name = serializers.CharField( source = "consultant.full_name", read_only = True)
    patient_name = serializers.CharField(source = 'patient.full_name', read_only = True)
    consultant_id = serializers.UUIDField(source = "consultant.id", read_only = True)
    patient_id = serializers.UUIDField(read_only = True)
    duration_formatted = serializers.ReadOnlyField()
    consultation_fee = serializers.DecimalField(
        max_digits=10, decimal_places=2, coerce_to_string=False
    )
    
    class Meta:
        model = CallSession
        fields = [
            
            "id",
            "session_id",
            "patient_id",
            "consultant_id",
            "consultant_name",
            "patient_name",
            "call_type",
            "status",
            "scheduled_at",
            "started_at",
            "ended_at",
            "duration_minutes",
            "duration_formatted",
            "consultation_fee",
            "payment_status",
            "consultant_notes",
            "patient_feedback",
            "created_at",
                       
        ]


    def to_representation(self, instance):
        data = super().to_representation(instance)
        if 'consultation_fee' in data and data['consultation_fee'] is not None:
            
            data['consultation_fee'] = float(data["consultation_fee"])
        return data
            


class AppointmentSlotSerializer(serializers.ModelSerializer):
    """ Serializers for available appointments slots """
    
    class Meta:
        model = AppointmentSlot
        fields = ['id', 'date', 'start_time', 'end_time', 'is_available', 'is_blocked']
        


class AppointmentCreateSerializer(serializers.ModelSerializer):
    """ Serializer for creating appointments """
    consultant_id = serializers.UUIDField(write_only = True)
    scheduled_date = serializers.DateField()
    scheduled_time = serializers.TimeField()
    
    class Meta:
        model = Appointment
        fields = [
            'consultant_id',
            'scheduled_date',
            'scheduled_time',
            'duration_minutes',
            'reason_for_visit',
            'patient_notes'
        ]
    
    def validate(self, data):
        from django.utils import timezone
        from consultants.models import ConsultantProfile
        
        try:
            consultant = ConsultantProfile.objects.get(
                id = data['consultant_id'],
                is_verified = True,
                is_available = True,
        )
            
        except ConsultantProfile.DoesNotExist:
            raise serializers.ValidationError(
                {"consultant_id": "Consultant not found or Unavailable"}
            )
            
        
        scheduled_datetime = timezone.datetime.combine(
            data["scheduled_date"],
            data['scheduled_time'],
            tzinfo= timezone.get_current_timezone(),
            
            )
        
        if scheduled_datetime < timezone.now():
            raise serializers.ValidationError(
                {" Scheduled_date ": "Cannot book appointments in the past time"}
            )
        conflicts = Appointment.objects.filter(
            consultant = consultant, 
            scheduled_date = data['scheduled_date'], 
            scheduled_time = data['scheduled_time'], 
            status__in = ['pending', 'confirmed'],
            
        )
        
        if conflicts:
            raise serializers.ValidationError(
                {"scheduled_time": "THis time slot is already booked"}
                
            )
        
        return data
    
class AppointmentConsultantInfoSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source = "user.full_name", read_only = True)
    specialization = serializers.CharField(source = "speciality.name", read_only = True)
    profile_picture = serializers.ImageField(source = 'avatar', read_only = True,
                                             allow_null =  True)
    
    class Meta:
        model = ConsultantProfile
        fields = ["id", "full_name", "specialization", "profile_picture"]
        
class AppointmentSerializer(serializers.ModelSerializer):
    consultant = AppointmentConsultantInfoSerializer(read_only=True)
    patient_name = serializers.CharField(source = 'patient.full_name', read_only = True )
    patient_id = serializers.UUIDField(source = "patient.id", read_only = True)
    scheduled_datetime = serializers.DateTimeField(read_only = True)
    end_time = serializers.DateTimeField(read_only = True)
    is_past = serializers.BooleanField(read_only = True)
    can_start = serializers.BooleanField(read_only = True)
    
    call_session = serializers.SerializerMethodField()
    consultation_fee = serializers.DecimalField(max_digits=10, 
                    decimal_places=2, coerce_to_string=False)
    
    class Meta:
        model = Appointment 
        fields = [
            "id",
            "consultant",
            "patient_name",
            "patient_id",
          #  "appointment_type",
            "status",
            "scheduled_date",
            "scheduled_time",
            "scheduled_datetime",
            "end_time",
            "duration_minutes",
            "reason_for_visit",
            "patient_notes",
           # "consultant_notes",
            "consultation_fee",
            "payment_status",
            "is_past",
            "can_start",
            "call_session",
        #   "cancellation_reason",
            "cancelled_at",
        #    "created_at",
            
        ]
        
    def get_call_session(self, obj):
        if obj.call_session:
            return str(obj.call_session.session_id)
        return None
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        
        data['consultation_fee'] = float(data.get("consultation_fee") or 0.0 )
        data["duration-minutes"] = int(data.get("duration_minutes") or 30 )
        data['patient_notes'] = data.get('patient_notes') or ""
        data['consultant_notes'] = data.get('consultant_notes') or ''
        data["reason_for_visit"] = data.get('reason_for_visit') or ''
        
        data['is_past'] = bool(data.get("is_past", False))
        data['can_start'] = bool(data.get("can_start", False))
        
        return data
    

class AppointmentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = [
            "scheduled_date",
            "scheduled_time",
            "duration_minutes",
            "reason_for_visit",
            "patient_notes",
            "consultant_notes",
            
        ]
        
    def validate(self, data):
        instance = self.instance
        
        if instance.status in ['completed', 'cancelled']:
            raise serializers.ValidationError(f"Cannot update {instance.status} appointments")
        
        if 'scheduled_date' in data or 'scheduled_time' in data:
            scheduled_date = data.get('scheduled_date', instance.scheduled_date)
            scheduled_time = data.get('scheduled_time', instance.scheduled_time)
            
            conflicts = Appointment.objects.filter(
                consultant = instance.consultant,
                scheduled_date = scheduled_date,
                scheduled_time = scheduled_time,
                status__in = ['pending', 'confirmed']
                
            ).exclude(id = instance.id).exists()
            
            if conflicts:
                raise serializers.ValidationError("This time slot is already booked ")
        return data
    
class AppointmentCancelSerializer(serializers.Serializer):
    cancellation_reason = serializers.CharField( 
        max_length = 500, required = False, allow_blank = True)


class PrescriptionSerializer(serializers.ModelSerializer):
    """Serializer for prescriptions"""
    consultant_name = serializers.CharField(source="consultant.full_name", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    session_id = serializers.CharField(source="call_session.session_id", read_only=True)

    class Meta:
        model = Prescription
        fields = [
            "id",
           # "call_session",
            "session_id",
            "consultant",
            "consultant_name",
            "patient",
            "patient_name",
            "medications",
            "instructions",
            "diagnosis",
            "status",
            "valid_until",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PrescriptionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating prescriptions"""
    call_session_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Prescription
        fields = [
            "call_session_id",
            "medications",
            "instructions",
            "diagnosis",
            "valid_until",
        ]

    def validate_call_session_id(self, value):
        try:
            call_session = CallSession.objects.get(
                id=value,
                consultant=self.context['request'].user,
                status='completed'
            )
            return call_session
        except CallSession.DoesNotExist:
            raise serializers.ValidationError("Call session not found or not completed")

    def create(self, validated_data):
        call_session = validated_data.pop('call_session_id')
        return Prescription.objects.create(
            call_session=call_session,
            consultant=self.context['request'].user,
            patient=call_session.patient,
            **validated_data
        )


class PrescriptionUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating prescriptions"""

    class Meta:
        model = Prescription
        fields = [
            "medications",
            "instructions",
            "diagnosis",
            "status",
            "valid_until",
        ]
        

        
        
            
            
            