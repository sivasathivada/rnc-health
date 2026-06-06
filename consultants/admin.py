
from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Avg, Count
from .models import Speciality, ConsultantProfile, ConsultantReview, ConsultantAvailability

# --- SpecialtyAdmin Section ---

admin.site.register(ConsultantAvailability)

@admin.register(Speciality)
class SpecialtyAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'consultant_count', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at',)

    def consultant_count(self, obj):
        count = obj.consultants.count()
        return format_html('<span style="font-weight: bold;">{}</span>', count)
    
    consultant_count.short_description = 'Consultants'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('consultants')

# --- ConsultantReviewInline Section ---

class ConsultantReviewInline(admin.TabularInline):
    model = ConsultantReview
    extra = 0
    readonly_fields = ('created_at',)
    fields = ('patient', 'rating', 'review_text', 'created_at')

# --- ConsultantProfileAdmin Section ---

@admin.register(ConsultantProfile)
class ConsultantProfileAdmin(admin.ModelAdmin):
    list_display = ('consultant_name','speciality', 'rating_display', 'total_consultation', 'consultation_fee', 'is_verified', 'is_available', 'created_at')
    list_filter = ('speciality', 'is_verified', 'is_available', 'years_of_experience', 'created_at')
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'speciality__name', 'license_number')
    readonly_fields = ('rating', 'total_consultation', 'created_at', 'updated_at')
    list_editable = ('is_verified', 'is_available')

    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'speciality', 'bio', 'years_of_experience', 'license_number')
        }),
        ('Financial', {
            'fields': ('consultation_fee',)
        }),
        ('Profile', {
            'fields': ('avatar',)
        }),
        ('Statistics', {
            'fields': ('rating', 'total_consultation'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_verified', 'is_available')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [ConsultantReviewInline]

    def consultant_name(self, obj):
        return f"Dr. {obj.user.full_name}"
    
    consultant_name.short_description = 'Name'
    consultant_name.admin_order_field = 'user__first_name'

    def rating_display(self, obj):
        if obj.rating > 0:
            stars = '★' * int(obj.rating) + '☆' * (5 - int(obj.rating))
            return format_html('<span title="{}/5">{} ({})</span>', obj.rating, stars, obj.rating)
        return 'No ratings'
    
    rating_display.short_description = 'Rating'
    rating_display.admin_order_field = 'rating'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'speciality')

    actions = ['verify_consultants', 'unverify_consultants', 'make_available', 'make_unavailable']

    def verify_consultants(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f'{updated} consultants were successfully verified.')
    
    verify_consultants.short_description = "Verify selected consultants"

    def unverify_consultants(self, request, queryset):
        updated = queryset.update(is_verified=False)
        self.message_user(request, f'{updated} consultants were marked as unverified.')
    
    unverify_consultants.short_description = "Unverify selected consultants"

    def make_available(self, request, queryset):
        updated = queryset.update(is_available=True)
        self.message_user(request, f'{updated} consultants were marked as available.')
    
    make_available.short_description = "Mark as available"

    def make_unavailable(self, request, queryset):
        updated = queryset.update(is_available=False)
        self.message_user(request, f'{updated} consultants were marked as unavailable.')
    
    make_unavailable.short_description = "Mark as unavailable"

# --- ConsultantReviewAdmin Section ---

@admin.register(ConsultantReview)
class ConsultantReviewAdmin(admin.ModelAdmin):
    list_display = ('patient_name', 'consultant_name', 'rating_stars', 'review_preview', 'created_at')
    list_filter = ('rating', 'created_at', 'consultant__speciality')
    search_fields = ('patient__first_name', 'patient__last_name', 'consultant__user__first_name', 'consultant__user__last_name', 'review_text')
    readonly_fields = ('created_at',)

    def patient_name(self, obj):
        return obj.patient.full_name
    
    patient_name.short_description = 'Patient'
    patient_name.admin_order_field = 'patient__first_name'

    def consultant_name(self, obj):
        return f"Dr. {obj.consultant.user.full_name}"
    
    consultant_name.short_description = 'Consultant'
    consultant_name.admin_order_field = 'consultant__user__first_name'

    def rating_stars(self, obj):
        stars = '★' * obj.rating + '☆' * (5 - obj.rating)
        return format_html('<span title="{}/5">{}</span>', obj.rating, stars)
    
    rating_stars.short_description = 'Rating'

    def review_preview(self, obj):
        if obj.review_text:
            preview = obj.review_text[:50] + '...' if len(obj.review_text) > 50 else obj.review_text
            return format_html('<span title="{}">{}</span>', obj.review_text, preview)
        return 'No review text'
    
    review_preview.short_description = 'Review'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'patient', 
            'consultant__user', 
            'consultant__speciality'
        )


