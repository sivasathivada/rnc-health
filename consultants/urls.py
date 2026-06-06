
from django.urls import path
from .import views


app_name = 'consultants'

urlpatterns = [
    
    # Public Consultants End points
    
    path('', views.consultant_list , name ='consultant_list'),
    path('<uuid:consultant_id>/', views.consultant_detail , name = 'consultant_detail'),
    path('specialities/', views.specialities_list , name = 'specialities_list'),


    # Consultant management endpoints (authenticated)
    path('profile/create/', views.create_consultant_profile, name = 'create_consultant_profile'),
    path('profile/', views.consultant_profile, name = 'consultant_profile'),
    path('profile/avatar/', views.update_consultant_avatar, name = 'update_consultant_avatar'),
    path('profile/availability/', views.consultant_availability, name='consultant_availability'),
    path('profile/toggle-availability/', views.toggle_consultant_availability, name = 'toggle_consultant_availability'),


    # Reviews endpoints
    path('<uuid:consultant_id>/reviews/',views.add_consultant_review, name = 'add_consultant_review'),

]
