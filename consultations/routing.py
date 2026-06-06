from django.urls import re_path
from .import consumers

websocket_urlpatterns= [
    # ws://api.localhost:port/ws/consultations/${user_id}?token=${jwtToken}
    re_path(r'ws/notifications/(?P<user_id>\w+)/$', 
            consumers.ConsultationConsumer.as_asgi()),
]