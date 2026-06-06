
from django.contrib import admin
from django.urls import path, include
from django.conf import  settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('authentication.urls')),
    path('api/v1/consultants/', include('consultants.urls')),
    path('api/v1/patients/', include('patients.urls')),
    path('api/v1/book-appointment/', include('consultations.urls')),
    path('api/v1/payments/', include('payments.urls')),
    path('api/v1/admin/', include('rnchealth.admin_urls')),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root= settings.MEDIA_ROOT)