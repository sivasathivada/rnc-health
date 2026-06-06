from django.urls import path
from . import admin_views

urlpatterns = [
    # Dashboard stats
    path('stats/', admin_views.admin_stats, name='admin-stats'),
    path('analytics/', admin_views.admin_analytics, name='admin-analytics'),

    # Users
    path('users/', admin_views.admin_users, name='admin-users'),
    path('users/<int:pk>/', admin_views.admin_user_detail, name='admin-user-detail'),

    # Consultants
    path('consultants/', admin_views.admin_consultants, name='admin-consultants'),
    path('consultants/<uuid:pk>/', admin_views.admin_consultant_detail, name='admin-consultant-detail'),

    # Specialities
    path('specialities/', admin_views.admin_specialities, name='admin-specialities'),
    path('specialities/<int:pk>/', admin_views.admin_speciality_detail, name='admin-speciality-detail'),

    # Consultant Availabilities
    path('consultant-availabilities/', admin_views.admin_consultant_availabilities, name='admin-consultant-availabilities'),
    path('consultant-availabilities/<uuid:pk>/', admin_views.admin_consultant_availability_detail, name='admin-consultant-availability-detail'),

    # Consultant Reviews
    path('consultant-reviews/', admin_views.admin_consultant_reviews, name='admin-consultant-reviews'),
    path('consultant-reviews/<uuid:pk>/', admin_views.admin_consultant_review_detail, name='admin-consultant-review-detail'),

    # Patients
    path('patients/', admin_views.admin_patients, name='admin-patients'),
    path('patients/<uuid:pk>/', admin_views.admin_patient_detail, name='admin-patient-detail'),
    path('patients/<uuid:pk>/medical-history/', admin_views.admin_patient_medical_history, name='admin-patient-medical-history'),

    # Medical History (global CRUD)
    path('medical-history/', admin_views.admin_medical_history, name='admin-medical-history'),
    path('medical-history/<uuid:pk>/', admin_views.admin_medical_history_detail, name='admin-medical-history-detail'),

    # Appointments
    path('appointments/', admin_views.admin_appointments, name='admin-appointments'),
    path('appointments/<uuid:pk>/', admin_views.admin_appointment_detail, name='admin-appointment-detail'),

    # Appointment Slots
    path('appointment-slots/', admin_views.admin_appointment_slots, name='admin-appointment-slots'),
    path('appointment-slots/<int:pk>/', admin_views.admin_appointment_slot_detail, name='admin-appointment-slot-detail'),

    # Call Sessions
    path('call-sessions/', admin_views.admin_call_sessions, name='admin-call-sessions'),
    path('call-sessions/<uuid:pk>/', admin_views.admin_call_session_detail, name='admin-call-session-detail'),

    # Prescriptions
    path('prescriptions/', admin_views.admin_prescriptions, name='admin-prescriptions'),
    path('prescriptions/<uuid:pk>/', admin_views.admin_prescription_detail, name='admin-prescription-detail'),

    # Payments & Wallets
    path('payments/', admin_views.admin_payments, name='admin-payments'),
    path('wallets/', admin_views.admin_wallets, name='admin-wallets'),
    path('wallet-transactions/', admin_views.admin_wallet_transactions, name='admin-wallet-transactions'),

    # Email Verification Tokens
    path('verification-tokens/', admin_views.admin_email_tokens, name='admin-email-tokens'),
    path('verification-tokens/<int:pk>/', admin_views.admin_email_token_detail, name='admin-email-token-detail'),

    # Stripe Events
    path('stripe-events/', admin_views.admin_stripe_events, name='admin-stripe-events'),
]
