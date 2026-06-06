
from django.contrib import admin
from django.urls import path, include
from django.conf import  settings
from django.conf.urls.static import static
from django.views.generic import RedirectView   # Use this if you want to redirect to an app path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='admin/', permanent=True)),

    path('api/auth/', include('authentication.urls')),
    path('api/v1/consultants/', include('consultants.urls')),
    path('api/v1/patients/', include('patients.urls')),
    path('api/v1/book-appointment/', include('consultations.urls')),
    path('api/v1/payments/', include('payments.urls')),
    path('api/v1/admin/', include('rnchealth.admin_urls')),
    path('', RedirectView.as_view(url='admin/', permanent=True)),

]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root= settings.MEDIA_ROOT)