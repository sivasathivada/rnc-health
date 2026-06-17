
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
import uuid
from datetime import timedelta
from consultants.models import ConsultantAvailability

User = get_user_model()

class CallSession(models.Model):
    """ Video/Audio call sessions between patients and consultants """
    
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('initiated', 'Initiated'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
        
    ]
    
    CAll_TYPE_CHOICES = [
        ("video", 'Video Call'),
        ("audio", "Audio Call"),
        
    ]
    
    QUALITY_CHOICES = [
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('failed', 'Failed'),
        ('not_tested', 'Not Tested'),
    ]
    
    CONNECTION_TYPE_CHOICES = [
        ('p2p', 'Peer-to-Peer'),
        ('relay', 'Relay (TURN)'),
        ('unknown', 'Unknown'),
    ]
    
    # Primary Key and Relations 
    id = models.UUIDField(primary_key=True, default= uuid.uuid4, editable=False)
    session_id = models.CharField(max_length=100, unique=True, db_index = True, null=True, blank=True)
    
    consultant = models.ForeignKey(User,
                                   on_delete=models.CASCADE,
                                   related_name="consultant_calls",
                                   limit_choices_to={"role" : "consultant"}
    )
    
    patient = models.ForeignKey(User,
                                   on_delete=models.CASCADE,
                                   related_name="patient_calls",
                                   limit_choices_to={"role" : "patient"}
    )
    
    
    # Calls Details 
    call_type = models.CharField(max_length=10, choices= CAll_TYPE_CHOICES, default ="video" )
    
    status = models.CharField(
        max_length=20, choices= STATUS_CHOICES, default= "initiated"
    )
    
    # Scheduling 
    scheduled_at = models.DateTimeField(null = True, blank = True)
    started_at = models.DateTimeField(null = True, blank = True)
    ended_at = models.DateTimeField( null = True, blank = True)
    duration_minutes = models.PositiveIntegerField( default=0)
    
    # Financial 
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    payment_status = models.CharField(max_length=20, default='pending')
    
    # Technical Details
    consultant_quality = models.CharField(max_length=20, blank=True)
    technical_issues = models.TextField(blank=True)
    
    # WebRTC & Connection Metrics
    connection_type = models.CharField(max_length=20, choices=CONNECTION_TYPE_CHOICES, default='unknown', blank=True)
    connection_quality = models.CharField(max_length=20, choices=QUALITY_CHOICES, default='not_tested', blank=True)
    webrtc_stats = models.JSONField(default=dict, blank=True, help_text="WebRTC connection statistics and metrics")
    offer_exchanged = models.BooleanField(default=False)
    answer_exchanged = models.BooleanField(default=False)
    ice_candidates_count = models.PositiveIntegerField(default=0)
    reconnection_attempts = models.PositiveIntegerField(default=0)
    connection_initiated_at = models.DateTimeField(null=True, blank=True)
    connection_established_at = models.DateTimeField(null=True, blank=True)
    last_ping_timestamp = models.DateTimeField(null=True, blank=True)
    
    # Notes 
    consultant_notes = models.TextField(blank=True)
    patient_feedback = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add = True)
    updated_at = models.DateTimeField(auto_now = True)
    
    
    class Meta:
        db_table = "call_sessions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["consultant", "status"]),
            models.Index(fields=["patient", "status"]),
            models.Index(fields= ["session_id"]),
            models.Index(fields=["scheduled_at"]),
            
    ]
        
    def __str__(self):
        return f" call: {self.patient.full_name} -> Dr. {self.consultant.full_name} ({self.status})"
    
    @property
    def duration_formatted(self):
        """ Return formatted duration string """
        if self.duration_minutes:
            hours = self.duration_minutes // 60
            minutes = self.duration_minutes % 60
            
            if hours:
                return f" {hours}h {minutes}m "
            return f"{minutes}m"
        return "0 minutes"
    
    def start_call(self):
        """ Mark call as Started """
        self.status = 'ongoing'
        self.started_at = timezone.now()
        self.save(update_fields = ['status', 'started_at'])
        
        
    def end_call(self):
        """ End call and calculate duration """
        
        self.status = 'completed'
        self.ended_at = timezone.now()
        
        if self.started_at:
            duration = self.ended_at - self.started_at
            self.duration_minutes = int(duration.total_seconds() / 60)
            
        self.save(update_fields=["status", "ended_at", "duration_minutes"])
        
        # Update consultant's consultation count
        try:
            consultant_profile = self.consultant.consultant_profile
            consultant_profile.increment_consultation_count()
        except :
            pass
    
    def record_offer_exchanged(self):
        """Record that WebRTC offer has been exchanged"""
        self.offer_exchanged = True
        self.connection_initiated_at = timezone.now()
        self.save(update_fields=['offer_exchanged', 'connection_initiated_at'])
    
    def record_answer_exchanged(self):
        """Record that WebRTC answer has been exchanged"""
        self.answer_exchanged = True
        self.save(update_fields=['answer_exchanged'])
    
    def record_connection_established(self):
        """Record when WebRTC connection is fully established"""
        self.connection_established_at = timezone.now()
        self.save(update_fields=['connection_established_at'])
    
    def add_ice_candidate(self):
        """Increment ICE candidate count"""
        self.ice_candidates_count += 1
        self.save(update_fields=['ice_candidates_count'])
    
    def record_reconnection_attempt(self):
        """Record a reconnection attempt"""
        self.reconnection_attempts += 1
        self.save(update_fields=['reconnection_attempts'])
    
    def update_webrtc_stats(self, stats_dict):
        """Update WebRTC statistics"""
        if self.webrtc_stats is None:
            self.webrtc_stats = {}
        self.webrtc_stats.update(stats_dict)
        self.save(update_fields=['webrtc_stats', 'last_ping_timestamp'])
    
    @property
    def connection_health(self):
        """Determine connection health based on metrics"""
        if self.connection_quality == 'excellent' and self.reconnection_attempts == 0:
            return 'Healthy'
        elif self.reconnection_attempts > 5 or self.connection_quality == 'poor':
            return 'Critical'
        elif self.reconnection_attempts > 2 or self.connection_quality == 'fair':
            return 'Warning'
        return 'Normal'
        
class Prescription(models.Model):
    """" Digital prescriptions from consultations"""
    
    STATUS_CHOICES =[
        ('active', "Active"),
        ("completed", "completed"),
        ("cancelled", "Cancelled"),
    
    ]
    
    id = models.UUIDField(primary_key=True, default= uuid.uuid4, editable=False)
    call_seesion = models.ForeignKey(CallSession, on_delete=models.CASCADE ,
                                    related_name = "prescriptions")
    
    consultant = models.ForeignKey(User,on_delete=models.CASCADE, 
                                   related_name="issued_prescriptions")
    
    patient = models.ForeignKey(User, on_delete= models.CASCADE, 
                                related_name="received_prescriptions")
    
    medications = models.JSONField(default = list)
    instructions = models.TextField()
    diagnosis = models.CharField(max_length=20, choices= STATUS_CHOICES, default= 'active')
    status = models.CharField(max_length = 20, choices = STATUS_CHOICES, default='active' )
    valid_until = models.DateTimeField()
    
    created_at = models.DateTimeField(auto_now_add= True)
    updated_at = models.DateTimeField(auto_now= True)
    
    class Meta:
        db_table = 'prescriptions'
        ordering = ['-created_at']
        
    def __str__(self):
        return f"Prescription for {self.patient.full_name} by Dr. {self.consultant.full_name}"
    
    
class Appointment(models.Model):
    """ Scheduled appointments between patients and consultants """
    STATUS_CHOICES = [
        ('pending', 'Pending_confirmation'),
        ('confirmed', 'confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
        ('no_show', "No Show"),
        
    ]
    APPOINTMENT_TYPE_CHOICES = [
        ('video', 'Video Consultation'),
        ('audio', 'Auido Consultation'),
        ('in_person', 'In-Person Visit'),
    ]
    
    id = models.UUIDField(primary_key=True, default= uuid.uuid4, editable=False)
    
    consultant = models.ForeignKey('consultants.ConsultantProfile',
                                   on_delete=models.CASCADE,
                                   related_name="appointments",
                                
    )
    
    patient = models.ForeignKey(User,
                                   on_delete=models.CASCADE,
                                   related_name="patient_appointments",
                                   limit_choices_to={"role" : "patient"}
    )
    
    Appointment_type = models.CharField(max_length=20,
                                        choices=APPOINTMENT_TYPE_CHOICES, default= 'video')
    
    status = models.CharField(max_length=20, choices= STATUS_CHOICES, default= 'pending')
    
    scheduled_date = models.DateField()
    scheduled_time = models.TimeField()
    
    duration_minutes = models.PositiveIntegerField(
        default=30, validators=[MinValueValidator(15)])
    
    reason_for_visit = models.TextField(max_length=500)
    patient_notes = models.TextField(blank = True, help_text= "Additional_information")
    
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2, null=False, blank=True)
    
    payment_status = models.CharField(
        max_length=20,
        choices= [('pending', 'Pending'), ('paid', 'Paid'), ('refunded','Refunded')],
        default="pending"
    )
    
    call_session = models.OneToOneField(
        "CallSession",
        on_delete=models.SET_NULL,
        null = True,
        blank=True,
        related_name="appointment",
    )
    
    cancelled_by = models.ForeignKey(User, on_delete=models.SET_NULL, 
                null = True, blank = True, related_name = "cancelled_appointments")
    cancelled_at = models.DateTimeField(null = True, blank = True)
    
    class Meta:
        db_table = "appointments"
        ordering = ['scheduled_date', 'scheduled_time']
        indexes = [
            models.Index(fields=['consultant','scheduled_date']),
            models.Index(fields=['patient', 'scheduled_date', 'status']),
            models.Index(fields=["scheduled_date", 'scheduled_time']),
            models.Index(fields=['status']),
            
        ]
        unique_together = [['consultant', "scheduled_date", "scheduled_time"]] 
        
    def __str__(self):
        return f"{self.patient.full_name} -> {self.consultant.user.full_name} ({self.scheduled_date} {self.scheduled_time})"                            
    
    
    def save(self, *args, **kwargs):
        
        # Only populate the fee if it hasn't been set yet
        if not self.consultation_fee and self.consultant:
            self.consultation_fee = self.consultant.consultation_fee
        
        super().save(*args, **kwargs)
    
    
    @property
    def scheduled_datetime(self):
        return timezone.datetime.combine(
            self.scheduled_date,
            self.scheduled_time,
            tzinfo= timezone.get_current_timezone(),
            
        )
    
    @property       
    def end_time(self):

        start = self.scheduled_datetime
        return start + timedelta(minutes= self.duration_minutes)
    
    @property
    def is_past(self):
        return self.scheduled_datetime < timezone.now()
    
    @property
    def can_start(self):
        now = timezone.now()
        start = self.scheduled_datetime
        return (start - timezone.timedelta(minutes=5)) <= now <= start + timezone.timedelta(minutes = 30)
    
    def clean(self):
        """ Validate appointment booking """
        if self.scheduled_datetime < timezone.now():
            raise ValidationError(" Cannot scheduled appointments in the past")
        
        from consultants.models import ConsultantAvailability
        day_of_week = self.scheduled_date.weekday()
        
        available = ConsultantAvailability.objects.filter(
            consultant = self.consultant,
            day_of_week = day_of_week, 
            start_time__lte = self.scheduled_time, 
            end_time__gte=self.scheduled_time, 
            is_active = True
        
        ).exists()
        
        if not available:
            raise ValidationError("Consultant is not available at this time")
        
    def confirm(self):
        self.status = 'confirmed'
        self.save(update_fields=['status',  ]) #"updated_at"
        
    def cancel(self, cancelled_by_user, reason = ''):
        
        self.status = "cancelled"
        self.cancelled_by = cancelled_by_user
        self.cancellation_reason = reason
        self.cancelled_at = timezone.now()
        self.save(
            
            update_fields = [
                'status',
                'cancelled_by', 
               # 'cancellation_reason',
                'cancelled_at', 
               # 'updated_at',
                ]
        )
            
            
    @property
    def appointment_type(self):
        """Safe fallback property to avoid AttributeError when accessing lowercase appointment_type"""
        return self.Appointment_type

    def create_call_session(self):
        if self.call_session:
            return self.call_session
       
        session_id = str(uuid.uuid4())
        call_session = CallSession.objects.create(
            session_id = session_id,
            consultant = self.consultant.user,
            patient = self.patient,
            call_type = "video",
            scheduled_at = self.scheduled_datetime,
            consultation_fee = self.consultation_fee,
            status = "scheduled"
        )
        self.call_session = call_session
        self.save(update_fields=['call_session'])
        
        return self.call_session
    
    def mark_completed(self):
        self.status = "completed"
        self.save(update_fields=["call_session"])
        
        return self.call_session
    
    def mark_completed(self):
        self.status = 'completed'
        self.save(update_fields=['status', 'updated_at'])
        
        self.consultant.increment_consultation_count()
        
        
class AppointmentSlot(models.Model):
    """ Available time slots for booking """
    
    consultant = models.ForeignKey(
        'consultants.ConsultantProfile',
        on_delete = models.CASCADE, 
        related_name= "available_slots"
    )
        
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
        
    is_available = models.BooleanField(default = True)
    is_blocked = models.BooleanField(default = False)
        
    created_at = models.DateTimeField(auto_now_add = True)
        
    class Meta:
        db_table = "appointment_slots"
        unique_together = [['consultant', "date", "start_time"]]
        indexes = [
            
            models.Index(fields= ["consultant", "date", "is_available"])
                
        ]
            
    def __str__(self):
        return f" Dr. {self.consultant.user.full_name} - {self.date} {self.start_time} -- {self.end_time}"
        