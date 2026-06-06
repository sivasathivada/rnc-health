from django.contrib import admin

# Register your models here.

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.db.models import Count
from .models import User, EmailVerificationToken
from django.utils.safestring import mark_safe

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'full_name', 'role', 'is_online_status', 'is_active', 'is_staff',
                    'last_seen', 'created_at', 'is_verified')
    list_filter = ('role', 'is_active', 'is_staff', 'is_online', 'created_at')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at', 'last_login')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'role')}),
        ('Status', {'fields': ('is_online', 'last_seen', 'is_active', 'is_staff',
                               'is_superuser', 'is_verified')}),
        ('Permissions', {'fields': ('groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'role', 'password1', 'password2'),
        }),
    )

    def is_online_status(self, obj):
        if obj.is_online:
            return mark_safe('<span style="color: green;">●</span> Online')
        return mark_safe('<span style="color: red;">●</span> Offline')
    is_online_status.short_description = 'Status'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related()

    actions = ['make_active', 'make_inactive']

    def make_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} users were successfully marked as active.')
    make_active.short_description = "Mark selected users as active"

    def make_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} users were successfully marked as inactive.')
    make_inactive.short_description = "Mark selected users as inactive"


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token_preview', 'is_used', 'is_expired_status', 'created_at',
                    'expires_at','is_expired')
    list_filter = ('is_used', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name')
    ordering = ('-created_at',)
    readonly_fields = ('token', 'created_at', 'is_expired_status')

    def token_preview(self, obj):
        return f"{str(obj.token)[:8]}..."
    token_preview.short_description = "Token Preview"

    def is_expired_status(self, obj):
        if obj.is_expired:
            return mark_safe('<span style="color: red;">Expired</span>')
        return mark_safe('<span style="color: green;">Valid</span>')
    is_expired_status.short_description = "Status"

    actions = ['mark_tokens_used']

    def mark_tokens_used(self, request, queryset):
        count = queryset.filter(is_used=False).update(is_used=True)
        self.message_user(request, f'{count} tokens marked as used.')
    mark_tokens_used.short_description = "Mark selected tokens as used"