from django.urls import path
from .import videoaudio_views

from .views import (
    # Appointment Views
    ConsultantAppointmentListView,
    ConsultantAppointmentDetailView,
    ConsultantAppointmentUpdateView,
    ConsultantAppointmentCancelView,
    ConsultantAppointmentConfirmView,
    ConsultantAvailableSlotsView,
    PatientAppointmentCreateView,
    PatientAppointmentListView,
    ConsultantSpecificSlotListCreateView,
    ConsultantSpecificSlotDeleteView,
    # Call Session Views
    CallSessionListView,
    ConsultantCallSessionDetailView,
    # Prescription Views
    ConsultantPrescriptionListView,
    ConsultantPrescriptionDetailView,
    
)


app_name = 'consultations'


# videoaudiocalls urls
videoaudio_urls =[
    path("initiate/", videoaudio_views.initiate_call, name= "initiate_call"),
    path("sessions/<str:session_id>/start/", videoaudio_views.start_call, name ="start_call"),
    path("sessions/<str:session_id>/end/", videoaudio_views.end_call, name = "end_call"),
    
]



# Appointment URLs
appointment_urls = [
    # Patient: book new appointment
    path(
        'appointments/book/',
        PatientAppointmentCreateView.as_view(),
        name='patient-appointment-book'
    ),
    # Patient: list own appointments
    path(
        'appointments/my/',
        PatientAppointmentListView.as_view(),
        name='patient-appointment-list'
    ),
    # Consultant: list their appointments
    path(
        'appointments/',
        ConsultantAppointmentListView.as_view(),
        name='appointment-list'
    ),
    path(
        'appointments/<uuid:pk>/',
        ConsultantAppointmentDetailView.as_view(),
        name='appointment-detail'
    ),
    path(
        'appointments/<uuid:pk>/update/',
        ConsultantAppointmentUpdateView.as_view(),
        name='appointment-update'
    ),
    path(
        'appointments/<uuid:pk>/cancel/',
        ConsultantAppointmentCancelView.as_view(),
        name='appointment-cancel'
    ),
    path(
        'appointments/<uuid:pk>/confirm/',
        ConsultantAppointmentConfirmView.as_view(),
        name='appointment-confirm'
    ),
    path(
        'appointments/available-slots/',
        ConsultantAvailableSlotsView.as_view(),
        name='available-slots'
    ),
    path(
        'slots/specific/',
        ConsultantSpecificSlotListCreateView.as_view(),
        name='consultant-specific-slots'
    ),
    path(
        'slots/specific/<int:pk>/',
        ConsultantSpecificSlotDeleteView.as_view(),
        name='consultant-specific-slots-delete'
    ),
]

# Call Session URLs (Video/Audio Calls)
call_session_urls = [
    path(
        'calls/',
        CallSessionListView.as_view(),
        name='call-session-list'
    ),
    path(
        'calls/<str:session_id>/',
        ConsultantCallSessionDetailView.as_view(),
        name='call-session-detail'
    ),

]

# Prescription URLs
prescription_urls = [
    path(
        'prescriptions/',
        ConsultantPrescriptionListView.as_view(),
        name='prescription-list'
    ),
    path(
        'prescriptions/<uuid:pk>/',
        ConsultantPrescriptionDetailView.as_view(),
        name='prescription-detail'
    ),
]


# Combine all URLs
urlpatterns = appointment_urls + call_session_urls + prescription_urls+videoaudio_urls

