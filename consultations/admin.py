'''
from django.contrib import admin
from .models import CallSession, Prescription, Appointment, AppointmentSlot

admin.site.register(CallSession)
admin.site.register(Appointment)
admin.site.register(AppointmentSlot)
admin.site.register(Prescription)


'''

from django.contrib import admin
from django.utils.html import format_html, mark_safe
from django.urls import reverse
from django.db.models import Q, Count, Sum
from django.utils import timezone
from datetime import timedelta
from .models import CallSession, Prescription, Appointment, AppointmentSlot


# CALL SESSION ADMIN

@admin.register(CallSession)
class CallSessionAdmin(admin.ModelAdmin):
    """Admin interface for Call Sessions"""
    
    list_display = [
        'session_id_display',
        'consultant_name',
        'patient_name',
        'call_type_badge',
        'status_badge',
        'connection_quality_badge',
        'connection_health_badge',
        'scheduled_at_display',
        'duration_badge',
        'consultation_fee',
        'payment_status_badge',
        'created_at',
    ]
    
    list_filter = [
        'status',
        'call_type',
        'payment_status',
        'connection_quality',
        'connection_type',
        'created_at',
        'started_at',
        ('scheduled_at', admin.DateFieldListFilter),
    ]
    
    search_fields = [
        'session_id',
        'consultant__first_name',
        'consultant__last_name',
        'patient__first_name',
        'patient__last_name',
        'consultant__email',
        'patient__email',
    ]
    
    readonly_fields = [
        'id',
        'session_id',
        'timing_details',
        'financial_details',
        'technical_details_display',
        'webrtc_connection_details',
        'webrtc_stats_display',
        'notes_display',
        'created_at',
        'updated_at',
    ]
    
    fieldsets = (
        ('Session Information', {
            'fields': ('id', 'session_id', 'call_type', 'status'),
            'classes': ('wide',),
        }),
        ('Participants', {
            'fields': ('consultant', 'patient'),
            'classes': ('wide',),
        }),
        ('Scheduling & Timing', {
            'fields': ('timing_details',),
            'classes': ('wide', 'collapse'),
        }),
        ('Financial Details', {
            'fields': ('financial_details',),
            'classes': ('wide', 'collapse'),
        }),
        ('Technical Information', {
            'fields': ('consultant_quality', 'technical_details_display'),
            'classes': ('wide', 'collapse'),
        }),
        ('WebRTC & Connection Details', {
            'fields': ('connection_type', 'connection_quality', 'webrtc_connection_details', 'webrtc_stats_display'),
            'classes': ('wide', 'collapse'),
        }),
        ('Notes & Feedback', {
            'fields': ('notes_display',),
            'classes': ('wide', 'collapse'),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('wide', 'collapse'),
        }),
    )
    
    actions = [
        'mark_as_completed',
        'mark_as_cancelled',
        'mark_as_no_show',
        'export_call_reports',
        'reset_connection_stats',
    ]
    
   # change_list_template = 'admin/callsession_change_list.html'
    
    # Display methods    
    def session_id_display(self, obj):
        return format_html(
            '<span style="color: #0066cc; font-weight: bold;">{}</span>',
            obj.session_id
        )
    session_id_display.short_description = 'Session ID'
    
    def consultant_name(self, obj):
        return format_html(
            '<strong>{}</strong>',
            obj.consultant.full_name or obj.consultant.email
        )
    consultant_name.short_description = 'Consultant'
    
    def patient_name(self, obj):
        return format_html(
            '<strong>{}</strong>',
            obj.patient.full_name or obj.patient.email
        )
    patient_name.short_description = 'Patient'
    
    def call_type_badge(self, obj):
        colors = {'video': '#4CAF50', 'audio': '#2196F3'}
        color = colors.get(obj.call_type, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_call_type_display()
        )
    call_type_badge.short_description = 'Call Type'
    
    def connection_quality_badge(self, obj):
        quality_colors = {
            'excellent': '#4CAF50',
            'good': '#8BC34A',
            'fair': '#FFC107',
            'poor': '#FF9800',
            'failed': '#F44336',
            'not_tested': '#9E9E9E',
        }
        color = quality_colors.get(obj.connection_quality, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_connection_quality_display()
        )
    connection_quality_badge.short_description = 'Connection Quality'
    
    def connection_health_badge(self, obj):
        health_colors = {
            'Healthy': '#4CAF50',
            'Normal': '#2196F3',
            'Warning': '#FFC107',
            'Critical': '#F44336',
        }
        health = obj.connection_health
        color = health_colors.get(health, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            health
        )
    connection_health_badge.short_description = 'Connection Health'
    
    def status_badge(self, obj):
        colors = {
            'scheduled': '#FFC107',
            'initiated': '#2196F3',
            'ongoing': '#4CAF50',
            'completed': '#8BC34A',
            'cancelled': '#F44336',
            'no_show': '#E91E63',
        }
        color = colors.get(obj.status, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    
    def scheduled_at_display(self, obj):
        if obj.scheduled_at:
            return format_html(
                '<span title="{}">{}</span>',
                obj.scheduled_at.strftime('%Y-%m-%d %H:%M:%S'),
                obj.scheduled_at.strftime('%b %d, %H:%M')
            )
        return '-'
    scheduled_at_display.short_description = 'Scheduled At'
    
    def duration_badge(self, obj):
        if obj.duration_minutes:
            return format_html(
                '<span style="background-color: maroon; padding: 2px 6px; border-radius: 3px;">{}</span>',
                obj.duration_formatted
            )
        return '-'
    duration_badge.short_description = 'Duration'
    
    def payment_status_badge(self, obj):
        colors = {'pending': '#FFC107', 'paid': '#4CAF50', 'refunded': '#2196F3'}
        color = colors.get(obj.payment_status, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>',
            color,
            obj.payment_status.upper()
        )
    payment_status_badge.short_description = 'Payment'
    
    def timing_details(self, obj):
        return format_html(
            '<strong>Scheduled:</strong> {}<br/>'
            '<strong>Started:</strong> {}<br/>'
            '<strong>Ended:</strong> {}<br/>'
            '<strong>Duration:</strong> {} minutes',
            obj.scheduled_at or 'N/A',
            obj.started_at or 'N/A',
            obj.ended_at or 'N/A',
            obj.duration_minutes or 0
        )
    timing_details.short_description = 'Timing Details'
    
    def financial_details(self, obj):
        return format_html(
            '<strong>Consultation Fee:</strong> £{}<br/>'
            '<strong>Payment Status:</strong> {}',
            obj.consultation_fee,
            obj.get_payment_status_display()
        )
    financial_details.short_description = 'Financial Details'
    
    def technical_details_display(self, obj):
        return format_html(
            '<strong>Consultant Quality:</strong> {}<br/>'
            '<strong>Technical Issues:</strong> {}',
            obj.consultant_quality or 'N/A',
            obj.technical_issues or 'None'
        )
    technical_details_display.short_description = 'Technical Details'
    
    def webrtc_connection_details(self, obj):
        """Display WebRTC connection lifecycle information"""
        return format_html(
            '<strong>Connection Type:</strong> {}<br/>'
            '<strong>Connection Quality:</strong> {}<br/>'
            '<strong>Offer Exchanged:</strong> {}<br/>'
            '<strong>Answer Exchanged:</strong> {}<br/>'
            '<strong>ICE Candidates:</strong> {}<br/>'
            '<strong>Reconnection Attempts:</strong> {}<br/>'
            '<strong>Connection Initiated:</strong> {}<br/>'
            '<strong>Connection Established:</strong> {}<br/>'
            '<strong>Last Ping:</strong> {}',
            obj.get_connection_type_display() if obj.connection_type else 'Unknown',
            obj.get_connection_quality_display() if obj.connection_quality else 'Not Tested',
            '✓ Yes' if obj.offer_exchanged else '✗ No',
            '✓ Yes' if obj.answer_exchanged else '✗ No',
            obj.ice_candidates_count,
            obj.reconnection_attempts,
            obj.connection_initiated_at.strftime('%Y-%m-%d %H:%M:%S') if obj.connection_initiated_at else 'N/A',
            obj.connection_established_at.strftime('%Y-%m-%d %H:%M:%S') if obj.connection_established_at else 'N/A',
            obj.last_ping_timestamp.strftime('%Y-%m-%d %H:%M:%S') if obj.last_ping_timestamp else 'N/A',
        )
    webrtc_connection_details.short_description = 'WebRTC Connection Details'
    
    def webrtc_stats_display(self, obj):
        """Display WebRTC statistics in a readable format"""
        if not obj.webrtc_stats:
            return format_html('<em>No WebRTC statistics recorded</em>', "")
        
        stats_html = '<table style="width: 100%; border-collapse: collapse;">'
        for key, value in obj.webrtc_stats.items():
            # Safely format each stats item
            stats_html += f'<tr style="border-bottom: 1px solid #ddd;"><td style="padding: 5px;"><strong>{key}:</strong></td><td style="padding: 5px;">{value}</td></tr>'
        stats_html += '</table>'
        return mark_safe(stats_html)
    webrtc_stats_display.short_description = 'WebRTC Statistics'
    
    def notes_display(self, obj):
        return format_html(
            '<strong>Consultant Notes:</strong><br/>{}<br/><br/>'
            '<strong>Patient Feedback:</strong><br/>{}',
            obj.consultant_notes or 'N/A',
            obj.patient_feedback or 'N/A'
        )
    notes_display.short_description = 'Notes & Feedback'
    
    # Actions
    def mark_as_completed(self, request, queryset):
        updated = queryset.exclude(status='completed').update(status='completed')
        self.message_user(request, f'{updated} call session(s) marked as completed.')
    mark_as_completed.short_description = 'Mark selected as completed'
    
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.exclude(status='cancelled').update(status='cancelled')
        self.message_user(request, f'{updated} call session(s) marked as cancelled.')
    mark_as_cancelled.short_description = 'Mark selected as cancelled'
    
    def mark_as_no_show(self, request, queryset):
        updated = queryset.exclude(status='no_show').update(status='no_show')
        self.message_user(request, f'{updated} call session(s) marked as no show.')
    mark_as_no_show.short_description = 'Mark selected as no show'
    
    def export_call_reports(self, request, queryset):
        self.message_user(request, 'Export functionality to be implemented.')
    export_call_reports.short_description = 'Export call reports'
    
    def reset_connection_stats(self, request, queryset):
        """Reset WebRTC connection statistics for selected sessions"""
        updated = queryset.update(
            ice_candidates_count=0,
            reconnection_attempts=0,
            webrtc_stats={},
            offer_exchanged=False,
            answer_exchanged=False,
            connection_initiated_at=None,
            connection_established_at=None,
            last_ping_timestamp=None,
        )
        self.message_user(request, f'Connection stats reset for {updated} call session(s).')
    reset_connection_stats.short_description = 'Reset connection statistics'
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('consultant', 'patient')
    
# PRESCRIPTION ADMIN

@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    """Admin interface for Prescriptions"""
    
    list_display = [
        'id_display',
        'consultant_name',
        'patient_name',
        'status_badge',
        'valid_until_display',
        'medication_count',
        'created_at',
        'actions_display',
    ]
    
    list_filter = [
        'status',
        'created_at',
        ('valid_until', admin.DateFieldListFilter),
        'call_seesion__consultant',
    ]
    
    search_fields = [
        'consultant__first_name',
        'consultant__last_name',
        'patient__first_name',
        'patient__last_name',
        'diagnosis',
        'medications',
    ]
    
    readonly_fields = [
        'id',
       # 'prescription_details',
        'medication_details',
        'instructions_display',

        'created_at',
        'updated_at',
    ]
    
    fieldsets = (
        ('Prescription Information', {
            'fields': ('id', 'call_seesion', 'status'),
            'classes': ('wide',),
        }),
        ('Healthcare Professionals', {
            'fields': ('consultant', 'patient'),
            'classes': ('wide',),
        }),
        ('Medical Details', {
            'fields': ('diagnosis', 'medication_details', 'instructions_display'),
            'classes': ('wide',),
        }),
        ('Validity', {
            'fields': ('valid_until',),
            'classes': ('wide',),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('wide', 'collapse'),
        }),
    )
    
    actions = ['mark_as_active', 'mark_as_completed', 'mark_as_cancelled']
    
    def id_display(self, obj):
        return format_html(
            '<span style="color: #0066cc; font-weight: bold;">{}</span>',
            str(obj.id)[:8]
        )
    id_display.short_description = 'Prescription ID'
    
    def consultant_name(self, obj):
        return format_html('<strong>{}</strong>', obj.consultant.full_name)
    consultant_name.short_description = 'Consultant'
    
    def patient_name(self, obj):
        return format_html('<strong>{}</strong>', obj.patient.full_name)
    patient_name.short_description = 'Patient'
    
    def status_badge(self, obj):
        colors = {'active': '#4CAF50', 'completed': '#2196F3', 'cancelled': '#F44336'}
        color = colors.get(obj.status, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def valid_until_display(self, obj):
        is_expired = obj.valid_until < timezone.now()
        color = 'red' if is_expired else 'green'
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.valid_until.strftime('%b %d, %Y')
        )
        
    valid_until_display.short_description = 'Valid Until'
    
    def medication_count(self, obj):
        count = len(obj.medications) if obj.medications else 0
        return format_html(
            '<span style="background-color: #E3F2FD; padding: 2px 6px; border-radius: 3px;">{} medication(s)</span>',
            count
        )
    medication_count.short_description = 'Medications'


    def medication_details(self, obj):
        medications = obj.medications or []
        if not medications:
            return 'No medications specified'
    
        # Start the list
        items_html = []
    
        for med in medications:
            if isinstance(med, dict):
                
                # format_html here safely escapes med.get('name'), etc.
                item = format_html(
                    "<li><strong>{}: </strong>{} - {}</li>",
                    med.get('name', 'Unknown'),
                    med.get('dosage', 'N/A'),
                    med.get('frequency', 'N/A')
                    )
                items_html.append(item)
            else:
                # Safely escape plain string medications
                items_html.append(format_html("<li>{}</li>", med))
        
        # Join all safe items and wrap them in the UL tag
        # mark_safe is okay here because join() only works if all items 
        # were already marked safe by format_html
        return mark_safe('<ul style="margin: 0; padding-left: 20px;">' + "".join(items_html) + '</ul>')
    
    medication_details.short_description = 'Medications'
    
    def instructions_display(self, obj):
        return format_html(
            '<div style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</div>',
            obj.instructions or 'No instructions'
        )
    instructions_display.short_description = 'Instructions'
    
    def actions_display(self, obj):
        return format_html(
            '<a class="button" href="{}">View</a>',
            reverse('admin:consultations_prescription_change', args=[obj.pk])
        )
    actions_display.short_description = 'Actions'
    
    def mark_as_active(self, request, queryset):
        updated = queryset.update(status='active')
        self.message_user(request, f'{updated} prescription(s) marked as active.')
    mark_as_active.short_description = 'Mark as active'
    
    def mark_as_completed(self, request, queryset):
        updated = queryset.update(status='completed')
        self.message_user(request, f'{updated} prescription(s) marked as completed.')
    mark_as_completed.short_description = 'Mark as completed'
    
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'{updated} prescription(s) marked as cancelled.')
    mark_as_cancelled.short_description = 'Mark as cancelled'
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('consultant', 'patient', 'call_seesion')



# APPOINTMENT ADMIN

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    """Admin interface for Appointments"""
    
    list_display = [
        'id_display',
        'consultant_name',
        'patient_name',
        'appointment_type_badge',
        'status_badge',
        'scheduled_datetime_display',
        'duration_display',
        'payment_status_badge',
    ]
    
    list_filter = [
        'status',
        'Appointment_type',
        'payment_status',
        ('scheduled_date', admin.DateFieldListFilter),
        # 'created_at',
    ]
    
    search_fields = [
        'patient__first_name',
        'patient__last_name',
        'consultant__user__first_name',
        'consultant__user__last_name',
        'reason_for_visit',
        'patient__email',
    ]
    
    readonly_fields = [
        'id',
        #'appointment_details',
        #'scheduling_details',
        'patient_information',
        'cancellation_details',
        'call_session_link',
        #'created_at',
        #'updated_at',
    ]
    
    fieldsets = (
        ('Appointment Information', {
            'fields': ('id', 'Appointment_type', 'status'),
            'classes': ('wide',),
        }),
        ('Participants', {
            'fields': ('consultant', 'patient'),
            'classes': ('wide',),
        }),
        ('Scheduling', {
            'fields': ('scheduled_date', 'scheduled_time', 'duration_minutes'),
            'classes': ('wide',),
        }),
        ('Reason & Notes', {
            'fields': ('reason_for_visit', 'patient_information'),
            'classes': ('wide',),
        }),
        ('Payment', {
            'fields': ('consultation_fee', 'payment_status'),
            'classes': ('wide',),
        }),
        ('Related Call Session', {
            'fields': ('call_session_link',),
            'classes': ('wide', 'collapse'),
        }),
        ('Cancellation Details', {
            'fields': ('cancellation_details',),
            'classes': ('wide', 'collapse'),
        }),
     #   ('Metadata', {
            #'fields': ('created_at', 'updated_at'),
           # 'classes': ('wide', 'collapse'),
       # }),
    )
    
    actions = [
        'mark_as_confirmed',
        'mark_as_completed',
        'mark_as_no_show',
        'mark_as_cancelled',
    ]
    
    date_hierarchy = 'scheduled_date'
    
    def id_display(self, obj):
        return format_html(
            '<span style="color: #0066cc; font-weight: bold;">{}</span>',
            str(obj.id)[:8]
        )
    id_display.short_description = 'Appointment ID'
    
    def consultant_name(self, obj):
        return format_html(
            '<strong>{}</strong>',
            obj.consultant.user.full_name
        )
    consultant_name.short_description = 'Consultant'
    """
    def patient_name(self, obj):
    # Add a print statement to see what obj.patient.full_name actually is
    # print(f"DEBUG: {type(obj.patient.full_name)}") 
    
        name = str(obj.patient.full_name) # Explicitly cast to string
        return format_html('<strong>{}</strong>', name)

    patient_name.short_description = 'Patient'
    
    """
    def patient_name(self, obj):
        return format_html(
            '<strong>{}</strong>',
            obj.patient.full_name
        )
    patient_name.short_description = 'Patient'
    
    
    def appointment_type_badge(self, obj):
        colors = {'video': '#4CAF50', 'audio': '#2196F3', 'in_person': '#FF9800'}
        color = colors.get(obj.Appointment_type, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_Appointment_type_display()
        )
    appointment_type_badge.short_description = 'Type'
    
    def status_badge(self, obj):
        colors = {
            'pending': '#FFC107',
            'confirmed': '#4CAF50',
            'cancelled': '#F44336',
            'completed': '#2196F3',
            'no_show': '#E91E63',
        }
        color = colors.get(obj.status, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def scheduled_datetime_display(self, obj):
        return format_html(
            '<strong>{}</strong><br/><span style="color: #666;">{}</span>',
            obj.scheduled_date,
            obj.scheduled_time
        )
    scheduled_datetime_display.short_description = 'Date & Time'
    
    def duration_display(self, obj):
        return format_html(
            '<span style="background-color: #E3F2FD; padding: 2px 6px; border-radius: 3px;">{} min</span>',
            obj.duration_minutes
        )
    duration_display.short_description = 'Duration'
    
    def payment_status_badge(self, obj):
        colors = {'pending': '#FFC107', 'paid': '#4CAF50', 'refunded': '#2196F3'}
        color = colors.get(obj.payment_status, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>',
            color,
            obj.payment_status.upper()
        )
    payment_status_badge.short_description = 'Payment'
   
    def patient_information(self, obj):
        return format_html(
            '<strong>Patient Notes:</strong><br/>{}<br/><br/>'
            '<strong>Reason for Visit:</strong><br/>{}',
            obj.patient_notes or 'N/A',
            obj.reason_for_visit or 'N/A'
        )
    patient_information.short_description = 'Patient Information'
    
    def cancellation_details(self, obj):
        if obj.status == 'cancelled':
            return format_html(
                '<strong>Cancelled By:</strong> {}<br/>'
                '<strong>Cancelled At:</strong> {}',
                obj.cancelled_by.full_name if obj.cancelled_by else 'Unknown',
                obj.cancelled_at or 'N/A'
            )
        return 'Not cancelled'
    cancellation_details.short_description = 'Cancellation Details'
    
    def call_session_link(self, obj):
        if obj.call_session:
            url = reverse('admin:consultations_callsession_change', args=[obj.call_session.pk])
            return format_html(
                '<a href="{}">{}</a>',
                url,
                obj.call_session.session_id
            )
        return 'No call session yet'
    call_session_link.short_description = 'Related Call Session'
    
    # Actions
    def mark_as_confirmed(self, request, queryset):
        updated = queryset.filter(status='pending').update(status='confirmed')
        self.message_user(request, f'{updated} appointment(s) confirmed.')
    mark_as_confirmed.short_description = 'Mark as confirmed'
    
    def mark_as_completed(self, request, queryset):
        updated = queryset.exclude(status='completed').update(status='completed')
        self.message_user(request, f'{updated} appointment(s) marked as completed.')
    mark_as_completed.short_description = 'Mark as completed'
    
    def mark_as_no_show(self, request, queryset):
        updated = queryset.update(status='no_show')
        self.message_user(request, f'{updated} appointment(s) marked as no show.')
    mark_as_no_show.short_description = 'Mark as no show'
    
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.exclude(status='cancelled').update(status='cancelled')
        self.message_user(request, f'{updated} appointment(s) cancelled.')
    mark_as_cancelled.short_description = 'Mark as cancelled'
    
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('consultant', 'patient', 'cancelled_by', 'call_session')


# APPOINTMENT SLOT ADMIN

@admin.register(AppointmentSlot)
class AppointmentSlotAdmin(admin.ModelAdmin):
    """Admin interface for Appointment Slots"""
    
    list_display = [
        'id_display',
        'consultant_name',
        'date_display',
        'time_range_display',
        'availability_badge',
        'blocked_badge',
        'created_at',
    ]
    
    list_filter = [
        'is_available',
        'is_blocked',
        ('date', admin.DateFieldListFilter),
        'created_at',
    ]
    
    search_fields = [
        'consultant__user__first_name',
        'consultant__user__last_name',
        'consultant__speciality__name',
    ]
    
    readonly_fields = [
        'id',
        'slot_details',
        'created_at',
    ]
    
    fieldsets = (
        ('Slot Information', {
            'fields': ('id', 'consultant', 'date'),
            'classes': ('wide',),
        }),
        ('Time Details', {
            'fields': ('start_time', 'end_time'),
            'classes': ('wide',),
        }),
        ('Availability', {
            'fields': ('is_available', 'is_blocked'),
            'classes': ('wide',),
        }),
        ('Details', {
            'fields': ('slot_details',),
            'classes': ('wide',),
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('wide', 'collapse'),
        }),
    )
    
    actions = ['mark_as_available', 'mark_as_unavailable', 'mark_as_blocked', 'unblock_slots']
    
    date_hierarchy = 'date'
    
    def id_display(self, obj):
        return format_html(
            '<span style="color: #0066cc; font-weight: bold;">{}</span>',
            str(obj.id)[:8]
        )
    id_display.short_description = 'Slot ID'
    
    def consultant_name(self, obj):
        return format_html(
            '<strong>{}</strong>',
            obj.consultant.user.full_name
        )
    consultant_name.short_description = 'Consultant'
    
    def date_display(self, obj):
        return obj.date.strftime('%a, %b %d, %Y')
    date_display.short_description = 'Date'
    
    def time_range_display(self, obj):
        return format_html(
            '<strong>{} - {}</strong>',
            obj.start_time.strftime('%H:%M'),
            obj.end_time.strftime('%H:%M')
        )
    time_range_display.short_description = 'Time Range'
    
    def availability_badge(self, obj):
        color = 'green' if obj.is_available else 'red'
        status = 'Available' if obj.is_available else 'Booked'
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            status
        )
    availability_badge.short_description = 'Availability'
    
    def blocked_badge(self, obj):
        if obj.is_blocked:
            return format_html(
                '<span style="background-color: #F44336; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',"Blocked"
            )
        return format_html(
            '<span style="background-color: #2196F3; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',"Open"
        )
    blocked_badge.short_description = 'Status'
    
    def slot_details(self, obj):
        return format_html(
            '<strong>Consultant:</strong> {}<br/>'
            '<strong>Date:</strong> {}<br/>'
            '<strong>Time:</strong> {} - {}<br/>'
            '<strong>Available:</strong> {}<br/>'
            '<strong>Blocked:</strong> {}',
            obj.consultant.user.full_name,
            obj.date,
            obj.start_time,
            obj.end_time,
            'Yes' if obj.is_available else 'No',
            'Yes' if obj.is_blocked else 'No'
        )
    slot_details.short_description = 'Slot Details'
    
    # Actions
    def mark_as_available(self, request, queryset):
        updated = queryset.update(is_available=True)
        self.message_user(request, f'{updated} slot(s) marked as available.')
    mark_as_available.short_description = 'Mark as available'
    
    def mark_as_unavailable(self, request, queryset):
        updated = queryset.update(is_available=False)
        self.message_user(request, f'{updated} slot(s) marked as unavailable.')
    mark_as_unavailable.short_description = 'Mark as unavailable'
    
    def mark_as_blocked(self, request, queryset):
        updated = queryset.update(is_blocked=True)
        self.message_user(request, f'{updated} slot(s) blocked.')
    mark_as_blocked.short_description = 'Block slots'
    
    def unblock_slots(self, request, queryset):
        updated = queryset.update(is_blocked=False)
        self.message_user(request, f'{updated} slot(s) unblocked.')
    unblock_slots.short_description = 'Unblock slots'
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('consultant', 'consultant__user')
