
import json
import jwt
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model

#from .models import CallSession
from .notification_service import NotificationService, NotificationType
from .call_session_service import CallSessionService
from .tasks import (
    log_call_event,
    persist_call_metrics,
    send_connection_quality_alert,
)

logger = logging.getLogger(__name__)

User = get_user_model()

class ConsultationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time consultation management.
    Handles incoming/outgoing calls, WebRTC signaling, and connection management.
    """
    
    # Connection settings
    HEARTBEAT_INTERVAL = 30  # seconds
    CONNECTION_TIMEOUT = 300  # seconds

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically binds the model to the instance once on boot
        from .models import CallSession
        self.CallSession = CallSession
    
    
    async def notification_message(self, event):
        """
        Route incoming_call notifications to proper handler.
        This is called when group_send uses type='notification_message'.
        """
        notification_type = event.get('notification_type')
        
        # Route to specific handler based on notification type
        if notification_type == 'incoming_call':
            await self.incoming_call(event)
        elif notification_type == 'call_accepted':
            await self.call_accepted(event)
        elif notification_type == 'call_declined':
            await self.call_declined(event)
        elif notification_type == 'call_ended':
            await self.call_ended(event)
        else:
            # Default: just forward as-is
            await self.send(text_data=json.dumps(event))
    
    async def auto_join_call_room(self, event):
        """
        Auto-join party to call room after accepting call.
        Ensures both parties are in the room and ready for WebRTC signaling.
        """
        try:
            session_id = event.get('session_id')
            call_room = event.get('call_room')
            
            if not session_id or not call_room:
                logger.warning(f"Missing session_id or call_room in auto_join event")
                return
            
            # Join the call room
            self.active_call_room = call_room
            await self.channel_layer.group_add(call_room, self.channel_name)
            
            # Get other participant's ID
            call_session = await self.get_call_session(session_id)
            other_user_id = None
            other_user = None
            if call_session:
                other_user_id = (
                    call_session.patient_id
                    if self.user.id == call_session.consultant_id
                    else call_session.consultant_id
                )
                other_user = (
                    call_session.patient
                    if self.user.id == call_session.consultant_id
                    else call_session.consultant
                )
            
            # Send confirmation to current user that they joined the room (matches handle_join_call_room)
            await self.send_json({
                'type': 'joined_call_room',
                'session_id': session_id,
                'message': 'Joined call room - ready for WebRTC signaling',
                'other_participant_id': str(other_user_id) if other_user_id else None,
            })
            
            # Send participant_joined notification to the other party (matches handle_join_call_room)
            if other_user_id:
                await self.channel_layer.group_send(
                    f"user_{other_user_id}",
                    {
                        'type': 'participant_joined',
                        'session_id': session_id,
                        'participant_id': str(self.user.id),
                        'participant_name': getattr(self.user, 'full_name', str(self.user)),
                        'timestamp': timezone.now().isoformat(),
                    }
                )
            
            # Also send participant_joined representing the other party back to this user
            # so they know the partner is already here
            if other_user:
                await self.send_json({
                    'type': 'participant_joined',
                    'session_id': session_id,
                    'participant_id': str(other_user.id),
                    'participant_name': getattr(other_user, 'full_name', str(other_user)),
                    'timestamp': timezone.now().isoformat(),
                })
            
            # Send confirmation to client that room has been joined
            await self.send_json({
                'type': 'ready_for_webrtc',
                'session_id': session_id,
                'message': 'Auto-joined call room, ready for peer connection',
                'call_room': call_room,
                'timestamp': timezone.now().isoformat(),
            })
            
            logger.info(f"User {self.user_id} auto-joined call room for session {session_id}")
        
        except Exception as e:
            logger.error(f"Error in auto_join_call_room: {str(e)}", exc_info=True)

    
    async def connect(self):
        """
        Handle WebSocket connection with JWT authentication.
        Verifies user identity and adds to user-specific group.
        """
        try:
            # Extract user ID from URL
            self.user_id = self.scope.get("url_route", {}).get("kwargs", {}).get("user_id")
            if not self.user_id:
                logger.warning("No user_id in connection URL")
                await self.close(code=4001, reason="Missing user_id")
                return
            
            # Extract and validate JWT token
            query_string = self.scope.get("query_string", b"").decode()
            query_params = parse_qs(query_string)
            token = query_params.get('token', [None])[0]
            
            if not token:
                logger.warning(f"No token provided for user {self.user_id}")
                await self.close(code=4001, reason="Missing authentication token")
                return
            
            # Authenticate user
            self.user = await self.authenticate_user(token)
            if not self.user:
                logger.warning(f"Authentication failed for user {self.user_id}")
                await self.close(code=4003, reason="Authentication failed")
                return
            
            if str(self.user.id) != str(self.user_id):
                logger.warning(f"User ID mismatch: {self.user.id} vs {self.user_id}")
                await self.close(code=4003, reason="User ID mismatch")
                return
            
            # Initialize consumer state
            self.user_group_name = f"user_{self.user_id}"
            self.active_call_room = None
            self.active_sessions = set()  # Track active call sessions
            self.is_authenticated = True
            
            # Add to user group for notifications
            await self.channel_layer.group_add(self.user_group_name, self.channel_name)
            
            # Accept the connection
            await self.accept()
            
            # Send connection established notification
            await self.send_json({
                'type': 'connection_established',
                'message': 'WebSocket connection successful',
                'user_id': str(self.user.id),
                'user_role': self.user.role,
                'timestamp': timezone.now().isoformat(),
            })
            
            logger.info(
                f"User {self.user_id} ({self.user.role}) connected. "
                f"Channel: {self.channel_name}"
            )
        
        except Exception as e:
            logger.error(f"Error in connect: {str(e)}", exc_info=True)
            await self.close(code=4000, reason="Connection error")
    
    async def disconnect(self, close_code):
        """
        Handle WebSocket disconnection.
        Clean up active calls and remove from groups.
        """
        try:
            if not hasattr(self, 'is_authenticated') or not self.is_authenticated:
                return
            
            # End any active calls
            for session_id in list(self.active_sessions):
                await self._handle_session_cleanup(session_id)
            
            # Remove from user group
            if hasattr(self, 'user_group_name'):
                await self.channel_layer.group_discard(
                    self.user_group_name,
                    self.channel_name
                )
            
            # Remove from active call room
            if self.active_call_room:
                await self.channel_layer.group_discard(
                    self.active_call_room,
                    self.channel_name
                )
            
            logger.info(
                f"User {self.user_id} disconnected. "
                f"Close code: {close_code} | "
                f"Active sessions: {len(self.active_sessions) if hasattr(self, 'active_sessions') else 0}"
            )
        
        except Exception as e:
            logger.error(f"Error in disconnect: {str(e)}", exc_info=True)
    
    async def receive(self, text_data):
        """
        Handle incoming WebSocket messages.
        Routes to appropriate handler based on message type.
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if not message_type:
                logger.warning(f"Message without type from user {self.user_id}")
                await self.send_error('invalid_message', 'Message type required')
                return
            
            # Handler mapping for different message types
            handler_map = {
                # Call management
                'initiate_call': self.handle_initiate_call,
                'accept_call': self.handle_accept_call,
                'decline_call': self.handle_decline_call,
                'end_call': self.handle_end_call,
                
                # Call room management
                'join_call_room': self.handle_join_call_room,
                'leave_call_room': self.handle_leave_call_room,
                
                # WebRTC signaling
                'webrtc_offer': self.handle_webrtc_offer,
                'webrtc_answer': self.handle_webrtc_answer,
                'ice_candidate': self.handle_ice_candidate,
                
                # Connection management
                'connection_established': self.handle_connection_established,
                'connection_quality': self.handle_connection_quality,
                'reconnection_attempt': self.handle_reconnection_attempt,
                
                # Keep-alive
                'ping': self.handle_ping,
            }
            
            handler = handler_map.get(message_type)
            if handler:
                await handler(data)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                await self.send_error('unknown_type', f"Unknown message type: {message_type}")
        
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from user {self.user_id}")
            await self.send_error('invalid_json', 'Invalid JSON format')
        except Exception as e:
            logger.error(f"Error in receive: {str(e)}", exc_info=True)
            await self.send_error('internal_error', 'Internal server error')
    
    # ==================== CALL MANAGEMENT HANDLERS ====================
    
    async def handle_initiate_call(self, data):
        """Handle incoming call request (patient -> consultant)"""
        try:
            session_id = data.get('session_id')
            recipient_id = data.get('recipient_id')
            call_type = data.get('call_type', 'video')
            
            if not session_id or not recipient_id:
                await self.send_error('missing_params', 'session_id and recipient_id required')
                return
            
            call_session = await self.get_call_session(session_id)
            if not call_session:
                await self.send_error('session_not_found', 'Call session not found')
                return
            
            if self.user.id not in [call_session.consultant_id, call_session.patient_id]:
                await self.send_error('unauthorized', 'Not part of this call')
                return
            
            self.active_sessions.add(session_id)
            
            # ASYNC FIX: Use async group_send with type='notification_message' for proper routing
            # Patient initiates -> send incoming_call to the CONSULTANT
            if self.user.id == call_session.patient_id:
                patient_name = getattr(self.user, 'full_name', str(self.user))
                await self.channel_layer.group_send(
                    f"user_{call_session.consultant_id}",
                    {
                        'type': 'notification_message',  # Routes to notification_message handler
                        'notification_type': 'incoming_call',
                        'session_id': session_id,
                        'patient_id': str(call_session.patient_id),
                        'patient_name': patient_name,
                        'call_type': call_type,
                        'timeout_seconds': 45,
                        'timestamp': timezone.now().isoformat(),
                    }
                )
                # Also confirm to patient that ringing has started
                await self.send_json({
                    'type': 'call_ringing',
                    'session_id': session_id,
                    'message': 'Calling consultant...',
                })
                
                # Schedule no-answer handler via Celery
                try:
                    from .tasks import handle_call_no_answer
                    handle_call_no_answer.apply_async(
                        args=[session_id],
                        countdown=45
                    )
                except Exception as e:
                    logger.warning(f"Could not schedule no-answer task: {str(e)}")
            else:
                # Consultant initiated -> notify patient
                consultant_name = getattr(self.user, 'full_name', str(self.user))
                await self.channel_layer.group_send(
                    f"user_{call_session.patient_id}",
                    {
                        'type': 'notification_message',  # Routes to notification_message handler
                        'notification_type': 'incoming_call',
                        'session_id': session_id,
                        'patient_id': str(call_session.patient_id),
                        'caller_name': consultant_name,
                        'caller_role': 'consultant',
                        'call_type': call_type,
                        'timeout_seconds': 45,
                        'timestamp': timezone.now().isoformat(),
                    }
                )
            
            logger.info(f"Call initiated: {session_id} by user {self.user_id}")
        
        except Exception as e:
            logger.error(f"Error in handle_initiate_call: {str(e)}", exc_info=True)
            await self.send_error('call_error', str(e))

    
    async def handle_accept_call(self, data):
        """Handle call acceptance and auto-join both parties to call room"""
        try:
            session_id = data.get('session_id')
            if not session_id:
                await self.send_error('missing_params', 'session_id required')
                return
            
            call_session = await self.get_call_session(session_id)
            if not call_session:
                await self.send_error('session_not_found', 'Call session not found')
                return
            
            success, error = await self.start_call_session(session_id)
            if not success:
                await self.send_error('call_error', error)
                return
            
            self.active_sessions.add(session_id)
            
            other_user_id = (
                call_session.patient_id
                if self.user.id == call_session.consultant_id
                else call_session.consultant_id
            )
            
            # Send call_accepted notification to the other party
            await self.channel_layer.group_send(
                f"user_{other_user_id}",
                {
                    'type': 'notification_message',
                    'notification_type': 'call_accepted',
                    'data': {
                        'session_id': session_id,
                        'accepted_by_id': str(self.user.id),
                    },
                    'timestamp': timezone.now().isoformat(),
                }
            )
            
            # ═══ AUTO-JOIN BOTH PARTIES TO CALL ROOM ═══
            # This ensures both parties automatically join and can start WebRTC signaling
            call_room = f"call_{session_id}"
            
            # Current user joins call room
            self.active_call_room = call_room
            await self.channel_layer.group_add(call_room, self.channel_name)
            
            # Send confirmation to current user that they joined the room (matches handle_join_call_room)
            await self.send_json({
                'type': 'joined_call_room',
                'session_id': session_id,
                'message': 'Joined call room - ready for WebRTC signaling',
                'other_participant_id': str(other_user_id),
            })
            
            # Send participant_joined notification to the other party (matches handle_join_call_room)
            await self.channel_layer.group_send(
                f"user_{other_user_id}",
                {
                    'type': 'participant_joined',
                    'session_id': session_id,
                    'participant_id': str(self.user.id),
                    'participant_name': getattr(self.user, 'full_name', str(self.user)),
                    'timestamp': timezone.now().isoformat(),
                }
            )
            
            # Since the call is now ongoing (accepted), send participant_joined representing
            # the other party to the current user immediately so they don't see "waiting".
            other_user = (
                call_session.patient
                if self.user.id == call_session.consultant_id
                else call_session.consultant
            )
            await self.send_json({
                'type': 'participant_joined',
                'session_id': session_id,
                'participant_id': str(other_user.id),
                'participant_name': getattr(other_user, 'full_name', str(other_user)),
                'timestamp': timezone.now().isoformat(),
            })
            
            # Send command to other party to auto-join call room
            await self.channel_layer.group_send(
                f"user_{other_user_id}",
                {
                    'type': 'auto_join_call_room',
                    'session_id': session_id,
                    'call_room': call_room,
                    'timestamp': timezone.now().isoformat(),
                }
            )
            
            # Notify both parties that they're now ready for WebRTC signaling
            await self.send_json({
                'type': 'ready_for_webrtc',
                'session_id': session_id,
                'message': 'Call room joined, ready for peer connection',
                'call_room': call_room,
            })
            
            logger.info(f"Call accepted & auto-joined room: {session_id} by user {self.user_id}")
        
        except Exception as e:
            logger.error(f"Error in handle_accept_call: {str(e)}", exc_info=True)
            await self.send_error('call_error', str(e))
    
    async def handle_decline_call(self, data):
        """Handle call decline"""
        try:
            session_id = data.get('session_id')
            reason = data.get('reason', 'user_declined')
            
            if not session_id:
                await self.send_error('missing_params', 'session_id required')
                return
            
            call_session = await self.get_call_session(session_id)
            if not call_session:
                await self.send_error('session_not_found', 'Call session not found')
                return
            
            success, error = await self.decline_call_session(session_id, reason)
            if not success:
                await self.send_error('call_error', error)
                return
            
            self.active_sessions.discard(session_id)
            
            # Notify the other party
            other_user_id = (
                call_session.patient_id
                if self.user.id == call_session.consultant_id
                else call_session.consultant_id
            )
            
            await self.channel_layer.group_send(
                f"user_{other_user_id}",
                {
                    'type': 'notification_message',
                    'notification_type': 'call_declined',
                    'session_id': session_id,
                    'reason': reason,
                    'timestamp': timezone.now().isoformat(),
                }
            )
            
            await self.send_json({
                'type': 'call_declined',
                'session_id': session_id,
                'reason': reason,
            })
            
            logger.info(f"Call declined: {session_id} by user {self.user_id} ({reason})")
        
        except Exception as e:
            logger.error(f"Error in handle_decline_call: {str(e)}", exc_info=True)
            await self.send_error('call_error', str(e))
    
    async def handle_end_call(self, data):
        """Handle call termination"""
        try:
            session_id = data.get('session_id')
            notes = data.get('notes', '')
            
            if not session_id:
                await self.send_error('missing_params', 'session_id required')
                return
            
            call_session = await self.get_call_session(session_id)
            if not call_session:
                await self.send_error('session_not_found', 'Call session not found')
                return
            
            success, error = await self.end_call_session(session_id, notes)
            if not success:
                await self.send_error('call_error', error)
                return
            
            self.active_sessions.discard(session_id)
            
            # Notify the other party
            other_user_id = (
                call_session.patient_id
                if self.user.id == call_session.consultant_id
                else call_session.consultant_id
            )
            
            await self.channel_layer.group_send(
                f"user_{other_user_id}",
                {
                    'type': 'notification_message',
                    'notification_type': 'call_ended',
                    'session_id': session_id,
                    'timestamp': timezone.now().isoformat(),
                }
            )
            
            await self.send_json({
                'type': 'call_ended',
                'session_id': session_id,
                'message': 'Call ended',
            })
            
            logger.info(f"Call ended: {session_id} by user {self.user_id}")
        
        except Exception as e:
            logger.error(f"Error in handle_end_call: {str(e)}", exc_info=True)
            await self.send_error('call_error', str(e))
    
    # ==================== CALL ROOM HANDLERS ====================
    
    async def handle_join_call_room(self, data):
        """Handle joining call room for WebRTC"""
        try:
            session_id = data.get('session_id')
            if not session_id:
                await self.send_error('missing_params', 'session_id required')
                return
            
            call_session = await self.get_call_session(session_id)
            if not call_session:
                await self.send_error('session_not_found', 'Call session not found')
                return
            
            if self.user.id not in [call_session.consultant_id, call_session.patient_id]:
                await self.send_error('unauthorized', 'Not part of this call')
                return
            
            # Verify call is in proper state for joining
            if call_session.status not in ['initiated', 'ongoing']:
                await self.send_error('call_error', f'Cannot join call in {call_session.status} state')
                return
            
            call_room = f"call_{session_id}"
            self.active_call_room = call_room
            await self.channel_layer.group_add(call_room, self.channel_name)
            
            other_user_id = (
                call_session.patient_id
                if self.user.id == call_session.consultant_id
                else call_session.consultant_id
            )
            
            await self.channel_layer.group_send(
                f"user_{other_user_id}",
                {
                    'type': 'participant_joined',
                    'session_id': session_id,
                    'participant_id': str(self.user.id),
                    'participant_name': getattr(self.user, 'full_name', str(self.user)),
                    'timestamp': timezone.now().isoformat(),
                }
            )
            
            # If the call is ongoing, it means the other participant is already active or joining.
            # Send participant_joined back to the joining party so they don't get stuck "waiting".
            if call_session.status == 'ongoing':
                other_user = (
                    call_session.patient
                    if self.user.id == call_session.consultant_id
                    else call_session.consultant
                )
                await self.send_json({
                    'type': 'participant_joined',
                    'session_id': session_id,
                    'participant_id': str(other_user.id),
                    'participant_name': getattr(other_user, 'full_name', str(other_user)),
                    'timestamp': timezone.now().isoformat(),
                })
            
            # Send confirmation to joining party
            await self.send_json({
                'type': 'joined_call_room',
                'session_id': session_id,
                'message': 'Joined call room - ready for WebRTC signaling',
                'other_participant_id': str(other_user_id),
            })
            
            # Also send ready_for_webrtc to make sure the client starts signaling
            await self.send_json({
                'type': 'ready_for_webrtc',
                'session_id': session_id,
                'message': 'Call room joined, ready for peer connection',
                'call_room': call_room,
            })
            
            logger.info(f"User {self.user_id} joined call room: {session_id}")
        
        except Exception as e:
            logger.error(f"Error in handle_join_call_room: {str(e)}", exc_info=True)
            await self.send_error('room_error', str(e))
    
    async def handle_leave_call_room(self, data):
        """Handle leaving call room"""
        try:
            session_id = data.get('session_id')
            
            if self.active_call_room:
                await self.channel_layer.group_discard(
                    self.active_call_room,
                    self.channel_name
                )
                
                call_session = await self.get_call_session(session_id)
                if call_session:
                    other_user_id = (
                        call_session.patient_id
                        if self.user.id == call_session.consultant_id
                        else call_session.consultant_id
                    )
                    
                    await self.channel_layer.group_send(
                        f"user_{other_user_id}",
                        {
                            'type': 'participant_left',
                            'session_id': session_id,
                            'participant_id': str(self.user.id),
                            'timestamp': timezone.now().isoformat(),
                        }
                    )
                
                self.active_call_room = None
                logger.info(f"User {self.user_id} left call room: {session_id}")
        
        except Exception as e:
            logger.error(f"Error in handle_leave_call_room: {str(e)}", exc_info=True)
    
    # ==================== WEBRTC SIGNALING HANDLERS ====================
    
    async def handle_webrtc_offer(self, data):
        """Handle WebRTC offer and send to call room"""
        try:
            session_id = data.get('session_id')
            offer = data.get('offer')
            
            if not session_id or not offer:
                await self.send_error('missing_params', 'session_id and offer required')
                return
            
            call_session = await self.get_call_session(session_id)
            if not call_session:
                await self.send_error('session_not_found', 'Call session not found')
                return
            
            # Ensure both parties are in the same room
            if call_session.status not in ['initiated', 'ongoing']:
                await self.send_error('call_error', 'Call not in correct state for WebRTC')
                return
            
            await self.record_offer_exchanged(session_id)
            
            # Send offer to the other party
            recipient_id = (
                call_session.patient_id
                if self.user.id == call_session.consultant_id
                else call_session.consultant_id
            )
            
            await self.channel_layer.group_send(
                f"user_{recipient_id}",
                {
                    'type': 'webrtc_offer',
                    'session_id': session_id,
                    'offer': offer,
                    'from_user_id': str(self.user.id),
                    'timestamp': timezone.now().isoformat(),
                }
            )
            
            logger.debug(f"WebRTC offer sent for session {session_id} from user {self.user_id}")
        
        except Exception as e:
            logger.error(f"Error in handle_webrtc_offer: {str(e)}", exc_info=True)
    
    async def handle_webrtc_answer(self, data):
        """Handle WebRTC answer"""
        try:
            session_id = data.get('session_id')
            answer = data.get('answer')
            
            if not session_id or not answer:
                return
            
            call_session = await self.get_call_session(session_id)
            if not call_session:
                return
            
            await self.record_answer_exchanged(session_id)
            
            recipient_id = (
                call_session.patient_id
                if self.user.id == call_session.consultant_id
                else call_session.consultant_id
            )
            
            await self.channel_layer.group_send(
                f"user_{recipient_id}",
                {
                    'type': 'webrtc_answer',
                    'session_id': session_id,
                    'answer': answer,
                    'from_user_id': str(self.user.id),
                }
            )
        
        except Exception as e:
            logger.error(f"Error in handle_webrtc_answer: {str(e)}", exc_info=True)
    
    
    async def handle_ice_candidate(self, data):
        """Handle ICE candidate"""
        try:
            session_id = data.get('session_id')
            candidate = data.get('candidate')
            
            if not session_id or not candidate:
                return
            
            call_session = await self.get_call_session(session_id)
            if not call_session:
                return
            
            await self.add_ice_candidate(session_id)
            
            recipient_id = (
                call_session.patient_id
                if self.user.id == call_session.consultant_id
                else call_session.consultant_id
            )
            
            await self.channel_layer.group_send(
                f"user_{recipient_id}",
                {
                    'type': 'ice_candidate',
                    'session_id': session_id,
                    'candidate': candidate,
                    'from_user_id': str(self.user.id),
                }
            )
        
        except Exception as e:
            logger.error(f"Error in handle_ice_candidate: {str(e)}", exc_info=True)
    
    # ==================== CONNECTION HANDLERS ====================
    
    async def handle_connection_established(self, data):
        """Handle WebRTC connection established"""
        try:
            session_id = data.get('session_id')
            connection_type = data.get('connection_type', 'unknown')
            
            if not session_id:
                return
            
            success, error = await self.record_connection_established_async(session_id, connection_type)
            if success:
                logger.info(f"Connection established for {session_id} via {connection_type}")
        
        except Exception as e:
            logger.error(f"Error in handle_connection_established: {str(e)}")
    
    async def handle_connection_quality(self, data):
        """Handle connection quality update"""
        try:
            session_id = data.get('session_id')
            quality = data.get('quality')
            stats = data.get('stats', {})
            
            if not session_id or not quality:
                return
            
            await self.update_connection_quality(session_id, quality, stats)
            
            try:
                persist_call_metrics.delay(session_id, stats)
            except Exception as e:
                logger.warning(f"Could not persist metrics: {str(e)}")
        
        except Exception as e:
            logger.error(f"Error in handle_connection_quality: {str(e)}")
    
    async def handle_reconnection_attempt(self, data):
        """Handle reconnection attempt"""
        try:
            session_id = data.get('session_id')
            if not session_id:
                return
            
            await self.record_reconnection_attempt(session_id)
            logger.warning(f"Reconnection attempt for session {session_id} by user {self.user_id}")
        
        except Exception as e:
            logger.error(f"Error in handle_reconnection_attempt: {str(e)}")
    
    # ==================== KEEP-ALIVE & UTILITY HANDLERS ====================
    
    async def handle_ping(self, data):
        """Handle ping for keep-alive"""
        await self.send_json({
            'type': 'pong',
            'timestamp': timezone.now().isoformat(),
        })
        
    
    # ==================== NOTIFICATION RECEIVERS ====================
    
    async def send_notification(self, event):
        """Send notification to client"""
        await self.send_json(event)
    
    async def incoming_call_notification(self, event):
        """Handle incoming call notification"""
        payload = {
            'type': 'incoming_call',
            'session_id': event.get('session_id'),
            'patient_id': event.get('patient_id'),
            'patient_name': event.get('patient_name'),
            'call_type': event.get('call_type'),
            'timeout_seconds': event.get('timeout_seconds', 45),
            'timestamp': event.get('timestamp'),
        }
        await self.send_json(payload)
    
    async def call_accepted_notification(self, event):
        """Handle call accepted notification"""
        await self.send_json({
            'type': 'call_accepted',
            'session_id': event.get('session_id'),
            'accepted_by_id': event.get('accepted_by_id'),
            'timestamp': event.get('timestamp'),
        })
    
    async def participant_joined_notification(self, event):
        """Handle participant joined notification"""
        await self.send_json({
            'type': 'participant_joined',
            'session_id': event.get('session_id'),
            'participant_id': event.get('participant_id'),
            'participant_name': event.get('participant_name'),
            'timestamp': event.get('timestamp'),
        })
    
    async def participant_left_notification(self, event):
        """Handle participant left notification"""
        await self.send_json({
            'type': 'participant_left',
            'session_id': event.get('session_id'),
            'participant_id': event.get('participant_id'),
            'timestamp': event.get('timestamp'),
        })
    
    async def webrtc_offer_notification(self, event):
        """Handle WebRTC offer notification"""
        await self.send_json({
            'type': 'webrtc_offer',
            'session_id': event.get('session_id'),
            'offer': event.get('offer'),
            'from_user_id': event.get('from_user_id'),
        })
    
    async def webrtc_answer_notification(self, event):
        """Handle WebRTC answer notification"""
        await self.send_json({
            'type': 'webrtc_answer',
            'session_id': event.get('session_id'),
            'answer': event.get('answer'),
            'from_user_id': event.get('from_user_id'),
        })
    
    async def ice_candidate_notification(self, event):
        """Handle ICE candidate notification"""
        await self.send_json({
            'type': 'ice_candidate',
            'session_id': event.get('session_id'),
            'candidate': event.get('candidate'),
            'from_user_id': event.get('from_user_id'),
        })
    
    async def connection_quality_alert(self, event):
        """Handle connection quality alert"""
        await self.send_json({
            'type': 'connection_quality_alert',
            'session_id': event.get('session_id'),
            'quality': event.get('quality'),
            'stats': event.get('stats'),
            'timestamp': event.get('timestamp'),
        })
    
    async def reconnection_alert(self, event):
        """Handle reconnection alert"""
        await self.send_json({
            'type': 'reconnection_alert',
            'session_id': event.get('session_id'),
            'reconnection_count': event.get('reconnection_count'),
            'timestamp': event.get('timestamp'),
        })
    
    # ==================== HELPER METHODS ====================
    
    async def send_json(self, content: Dict[str, Any]):
        """Send JSON to client with error handling"""
        try:
            await self.send(text_data=json.dumps(content))
        except Exception as e:
            logger.error(f"Error sending JSON to user {self.user_id}: {str(e)}")
    
    async def send_error(self, error_code: str, error_message: str):
        """Send error notification to client"""
        await self.send_json({
            'type': 'error',
            'error_code': error_code,
            'error_message': error_message,
            'timestamp': timezone.now().isoformat(),
        })
    
    # ==================== DATABASE OPERATIONS =================
    @database_sync_to_async
    def authenticate_user(self, token: str) -> Optional[User]:
        """Authenticate user via JWT token"""
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=["HS256"]
            )
            user_id = payload.get("user_id")
            user = User.objects.get(id=user_id, is_active=True)
            return user
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, User.DoesNotExist):
            return None
    
    @database_sync_to_async
    def get_call_session(self, session_id: str) -> Optional[CallSession]:
        """Get call session from database"""
        from .models import CallSession  
        try:
            return CallSession.objects.select_related(
                'consultant', 'patient'
            ).get(session_id=session_id)
        except CallSession.DoesNotExist:
            return None
    
    @database_sync_to_async
    def start_call_session(self, session_id: str):
        """Start call session — pass the user's ID so the service can distinguish
        consultant-start (ring patient) from patient-accept (go ongoing)."""
        try:
            call_session, error = CallSessionService.start_call(
                session_id, started_by_id=self.user.id
            )
            return bool(call_session), error
        except Exception as e:
            return False, str(e)
    
    @database_sync_to_async
    def decline_call_session(self, session_id: str, reason: str = "user_declined"):
        """Decline call session"""
        try:
            call_session, error = CallSessionService.decline_call(
                session_id,
                self.user.id,
                reason
            )
            return bool(call_session), error
        except Exception as e:
            return False, str(e)
    
    @database_sync_to_async
    def end_call_session(self, session_id: str, notes: str = ""):
        """End call session"""
        try:
            call_session, error = CallSessionService.end_call(
                session_id,
                self.user.id,
                notes
            )
            return bool(call_session), error
        except Exception as e:
            return False, str(e)
    
    @database_sync_to_async
    def record_offer_exchanged(self, session_id: str):
        """Record WebRTC offer exchange"""
        try:
            CallSessionService.record_offer_exchanged(session_id)
        except Exception as e:
            logger.error(f"Error recording offer: {str(e)}")
    
    @database_sync_to_async
    def record_answer_exchanged(self, session_id: str):
        """Record WebRTC answer exchange"""
        try:
            CallSessionService.record_answer_exchanged(session_id)
        except Exception as e:
            logger.error(f"Error recording answer: {str(e)}")
    
    @database_sync_to_async
    def add_ice_candidate(self, session_id: str):
        """Record ICE candidate"""
        try:
            CallSessionService.record_ice_candidate(session_id)
        except Exception as e:
            logger.error(f"Error recording ICE candidate: {str(e)}")
    
    @database_sync_to_async
    def record_connection_established_async(self, session_id: str, connection_type: str = 'unknown'):
        """Record connection established"""
        try:
            success, error = CallSessionService.record_connection_established(session_id, connection_type)
            return success, error
        except Exception as e:
            return False, str(e)
    
    @database_sync_to_async
    def record_reconnection_attempt(self, session_id: str):
        """Record reconnection attempt"""
        try:
            CallSessionService.record_reconnection_attempt(session_id)
        except Exception as e:
            logger.error(f"Error recording reconnection: {str(e)}")
    
    @database_sync_to_async
    def update_connection_quality(self, session_id: str, quality: str, stats: Dict = None):
        """Update connection quality"""
        try:
            CallSessionService.update_connection_quality(session_id, quality, stats)
        except Exception as e:
            logger.error(f"Error updating connection quality: {str(e)}")
    
    @database_sync_to_async
    def _handle_session_cleanup(self, session_id: str):
        """Internal method to clean up session"""
        try:
            call_session = CallSession.objects.get(session_id=session_id)
            if call_session.status == 'ongoing':
                call_session.end_call()
        except CallSession.DoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Error cleaning up session: {str(e)}")
    
    # Initialize is_authenticated flag
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_authenticated = False            

    async def webrtc_offer(self, event):
        """Forward WebRTC Offer to recipient."""
        await self.send(text_data=json.dumps(event))

    async def webrtc_answer(self, event):
        """Forward WebRTC Answer to caller."""
        await self.send(text_data=json.dumps(event))

    async def ice_candidate(self, event):
        """Forward ICE Candidates for peer connection."""
        await self.send(text_data=json.dumps(event))

    # ------------------------------------------------------------------
    # 3. CALL STATUS HANDLERS
    # ------------------------------------------------------------------

    async def incoming_call(self, event):
        """Trigger the 'Incoming Call' UI."""
        await self.send(text_data=json.dumps(event))

    async def call_accepted(self, event):
        """Notify party that call was picked up."""
        await self.send(text_data=json.dumps(event))

    async def call_declined(self, event):
        """Notify party that call was rejected."""
        await self.send(text_data=json.dumps(event))

    async def call_ended(self, event):
        """Clean up UI when a party hangs up."""
        await self.send(text_data=json.dumps(event))

    async def participant_joined(self, event):
        """Notify party that another user joined the room."""
        await self.send(text_data=json.dumps(event))

    async def participant_left(self, event):
        """Notify party that another user left the room."""
        await self.send(text_data=json.dumps(event))

    async def send_notification(self, event):
        """
        Generic notification handler for messages sent via NotificationService._send_to_user
        which uses type='send_notification'.
        """
        await self.send(text_data=json.dumps(event))
