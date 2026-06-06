from django.contrib import admin
from django.utils.html import format_html, mark_safe
from django.urls import reverse
from django.db.models import Q, Count


from .models import PatientMedicalHistory, PatientProfile




# ==================== PATIENT MEDICAL HISTORY INLINE ====================

class PatientMedicalHistoryInline(admin.TabularInline):
    
    """Inline admin for medical history records within patient profile"""
    model = PatientMedicalHistory
    extra = 1
    fields = ('record_type', 'title', 'date_occurred', 'healthcare_provider', 'created_at')
    readonly_fields = ('id', 'created_at', 'updated_at')
    can_delete = True
    
    def get_max_num(self, request, obj=None, **kwargs):
        """Limit to 5 most recent records inline"""
        return 5
    
    def get_queryset(self, request):
        """Sort by most recent records first"""
        qs = super().get_queryset(request)
        return qs.order_by('-date_occurred')


# ==================== PATIENT PROFILE ADMIN ====================

@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    """
    Admin interface for PatientProfile model.
    Provides comprehensive management of patient profiles with custom filters,
    search capabilities, and bulk actions.
    """
    
    # Display configuration
    list_display = (
        'patient_name',
        'email',
        'age_display',
        'gender',
        'blood_type',
        'phone_number',
        'medical_records_count',
        'created_at',
        'emergency_contact_badge',
    )
    
    # Filter configuration
    list_filter = (
        'gender',
        'blood_type',
        'preferred_language',
        'share_medical_history',
        'allow_emergency_access',
    )
    
    # Search configuration
    search_fields = (
        'user__full_name',
        'user__email',
        'phone_number',
        'city',
        'emergency_contact_name',
    )
    
    # Fieldsets for better organization
    fieldsets = (
        ('User Information', {
            'fields': ('id', 'user'),
            'classes': ('wide',),
        }),
        ('Personal Information', {
            'fields': (
                'avatar',
                'bio',
                'date_of_birth',
                'gender',
                'phone_number',
                'preferred_language',
            ),
            'classes': ('wide',),
        }),
        ('Address Information', {
            'fields': ('address', 'city', 'country', 'postal_code'),
            'classes': ('wide', 'collapse'),
        }),
        ('Emergency Contact', {
            'fields': (
                'emergency_contact_name',
                'emergency_contact_phone',
                'emergency_contact_relationship',
            ),
            'classes': ('wide', 'collapse'),
        }),
        ('Medical Information', {
            'fields': (
                'blood_type',
                'allergies',
                'chronic_conditions',
                'current_medications',
                'medical_notes',
            ),
            'classes': ('wide',),
            'description': 'Critical medical information for patient care',
        }),
        ('Privacy & Permissions', {
            'fields': (
                'share_medical_history',
                'allow_emergency_access',
            ),
            'classes': ('wide', 'collapse'),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('wide', 'collapse'),
        }),
    )
    
    # Inlines
    inlines = [PatientMedicalHistoryInline]
    
    # Read-only fields
    readonly_fields = ('id', 'created_at', 'updated_at', 'avatar_preview')
    
    # Ordering
    ordering = ('-created_at',)
    
    # Actions
    actions = [
        'mark_medical_history_shared',
        'mark_medical_history_private',
        'enable_emergency_access',
        'disable_emergency_access',
        'export_patient_data',
    ]
    
    # Display per page
    list_per_page = 25
    
    # ==================== Display Methods ====================
    
    def patient_name(self, obj):
        """Display patient name with link to user"""
        if obj.user:
            user_url = reverse('admin:authentication_user_change', args=[obj.user.id])
            return format_html(
                '<a href="{}">{}</a>',
                user_url,
                obj.user.full_name
            )
        return '-'
    patient_name.short_description = 'Patient Name'
    patient_name.admin_order_field = 'user__full_name'
    
    def email(self, obj):
        """Display patient email"""
        return obj.user.email if obj.user else '-'
    email.short_description = 'Email'
    email.admin_order_field = 'user__email'
    
    def age_display(self, obj):
        """Display calculated age"""
        if obj.age:
            return format_html('<strong>{} years</strong>', obj.age)
        return '-'
    age_display.short_description = 'Age'
    
    def medical_records_count(self, obj):
        """Display count of medical records"""
        count = obj.medical_history.count()
        return format_html(
            '<span style="background-color: #417690; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            count
        )
    medical_records_count.short_description = 'Medical Records'
    
    def emergency_contact_badge(self, obj):
        """Display emergency contact info as badge"""
        if obj.emergency_contact_name:
            return format_html(
                '<span title="{}: {}" style="background-color: #e74c3c; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
                obj.emergency_contact_relationship or 'Contact',
                obj.emergency_contact_phone or 'Phone not set',
                obj.emergency_contact_name[:20]
            )
        return '-'
    emergency_contact_badge.short_description = 'Emergency Contact'
    
    def avatar_preview(self, obj):
        """Display avatar preview"""
        if obj.avatar:
            return format_html(
                '<img src="{}" width="100" height="100" style="border-radius: 5px;" />',
                obj.avatar.url
            )
        return 'No avatar'
    avatar_preview.short_description = 'Avatar Preview'
    
    # ==================== Actions ====================
    
    def mark_medical_history_shared(self, request, queryset):
        """Action to enable medical history sharing"""
        updated = queryset.update(share_medical_history=True)
        self.message_user(request, f'{updated} patients marked to share medical history.')
    mark_medical_history_shared.short_description = '✓ Enable medical history sharing'
    
    def mark_medical_history_private(self, request, queryset):
        """Action to disable medical history sharing"""
        updated = queryset.update(share_medical_history=False)
        self.message_user(request, f'{updated} patients marked as private.')
    mark_medical_history_private.short_description = '✗ Disable medical history sharing'
    
    def enable_emergency_access(self, request, queryset):
        """Action to enable emergency access"""
        updated = queryset.update(allow_emergency_access=True)
        self.message_user(request, f'Emergency access enabled for {updated} patients.')
    enable_emergency_access.short_description = '🚨 Enable emergency access'
    
    def disable_emergency_access(self, request, queryset):
        """Action to disable emergency access"""
        updated = queryset.update(allow_emergency_access=False)
        self.message_user(request, f'Emergency access disabled for {updated} patients.')
    disable_emergency_access.short_description = '🔒 Disable emergency access'
    
    def export_patient_data(self, request, queryset):
        """Placeholder for data export action"""
        count = queryset.count()
        self.message_user(request, f'Export functionality for {count} patients would be initiated.')
    export_patient_data.short_description = '📥 Export patient data'
    
    # ==================== Query Optimization ====================
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('user').prefetch_related('medical_history')


# ==================== PATIENT MEDICAL HISTORY ADMIN ====================

@admin.register(PatientMedicalHistory)
class PatientMedicalHistoryAdmin(admin.ModelAdmin):
    """
    Admin interface for PatientMedicalHistory model.
    Manages medical records with filtering and search capabilities.
    """
    
    # Display configuration
    list_display = (
        'record_type_badge',
        'title',
        'patient_link',
        'date_occurred',
        'healthcare_provider',
        'days_ago',
        'created_at',
    )
    
    # Filter configuration
    list_filter = (
        'record_type',
        'date_occurred',
    )
    
    # Search configuration
    search_fields = (
        'title',
        'description',
        'healthcare_provider',
        'patient__user__first_name',
        'patient__user__last_name',
        'patient__user__email',
    )
    
    # Fieldsets for better organization
    fieldsets = (
        ('Record Information', {
            'fields': ('id', 'record_type', 'title'),
            'classes': ('wide',),
        }),
        ('Patient Information', {
            'fields': ('patient',),
            'classes': ('wide',),
        }),
        ('Medical Details', {
            'fields': (
                'description',
                'date_occurred',
                'healthcare_provider',
                'attachments',
            ),
            'classes': ('wide',),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('wide', 'collapse'),
        }),
    )
    
    # Read-only fields
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    # Ordering
    ordering = ('-date_occurred', '-created_at')
    
    # Actions
    actions = [
        'mark_as_diagnosis',
        'mark_as_procedure',
        'mark_as_surgery',
        'duplicate_record',
    ]
    
    # Display per page
    list_per_page = 50
    
    # Enable date hierarchy
    date_hierarchy = 'date_occurred'
    
    # ==================== Display Methods ====================
    
    def record_type_badge(self, obj):
        """Display record type as badge with color"""
        colors = {
            'diagnosis': '#3498db',      # Blue
            'procedure': '#2ecc71',      # Green
            'surgery': '#e74c3c',        # Red
            'hospitalization': '#f39c12', # Orange
            'vaccination': '#9b59b6',    # Purple
            'test_result': '#1abc9c',    # Teal
            'other': '#95a5a6',          # Gray
        }
        color = colors.get(obj.record_type, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 5px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_record_type_display()
        )
    record_type_badge.short_description = 'Type'
    record_type_badge.admin_order_field = 'record_type'
    
    def patient_link(self, obj):
        """Display patient name with link"""
        if obj.patient and obj.patient.user:
            patient_url = reverse('admin:patients_patientprofile_change', args=[obj.patient.id])
            return format_html(
                '<a href="{}">{}</a>',
                patient_url,
                obj.patient.user.full_name
            )
        return '-'
    patient_link.short_description = 'Patient'
    patient_link.admin_order_field = 'patient__user__full_name'
    
    def days_ago(self, obj):
        """Display how many days ago the record was created"""
        from django.utils import timezone
        from datetime import timedelta
        
        days = (timezone.now() - obj.created_at).days
        if days == 0:
            return mark_safe('<span style="color: green; font-weight: bold;">Today</span>')
        elif days < 7:
            return format_html('<span style="color: orange;">{} days ago</span>', days)
        else:
            return f'{days} days ago'
    days_ago.short_description = 'Created'
    
    # ==================== Actions ====================
    
    def mark_as_diagnosis(self, request, queryset):
        """Action to mark records as diagnosis"""
        updated = queryset.update(record_type='diagnosis')
        self.message_user(request, f'{updated} records marked as diagnosis.')
    mark_as_diagnosis.short_description = '🔍 Mark as Diagnosis'
    
    def mark_as_procedure(self, request, queryset):
        """Action to mark records as procedure"""
        updated = queryset.update(record_type='procedure')
        self.message_user(request, f'{updated} records marked as procedure.')
    mark_as_procedure.short_description = '🏥 Mark as Procedure'
    
    def mark_as_surgery(self, request, queryset):
        """Action to mark records as surgery"""
        updated = queryset.update(record_type='surgery')
        self.message_user(request, f'{updated} records marked as surgery.')
    mark_as_surgery.short_description = '⚕️ Mark as Surgery'
    
    def duplicate_record(self, request, queryset):
        """Placeholder for duplicate action"""
        count = queryset.count()
        self.message_user(request, f'Duplicate functionality for {count} records would be initiated.')
    duplicate_record.short_description = '📋 Duplicate Selected Records'
    
    # ==================== Query Optimization ====================
    
    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related('patient', 'patient__user')
