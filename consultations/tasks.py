"""
Celery background tasks for video/audio consultations.
Handles notifications, call timeouts, cleanup, and persistence operations.
"""
from rnchealth.celery import app
import logging
from celery import shared_task, current_task
from django.utils import timezone
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.db import transaction
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from datetime import timedelta
import json

from .models import CallSession, Appointment
from .notification_service import NotificationService, NotificationType

logger = logging.getLogger(__name__)
User = get_user_model()


# ==================== CALL TIMEOUT & CLEANUP TASKS ====================

@shared_task(
    name='consultations.handle_call_no_answer',
    max_retries=3,
    default_retry_delay=60,
    bind=True,
    time_limit=300  # 5 minutes
)
def handle_call_no_answer(self, session_id: str):
    """
    Handle missed calls after timeout (45 seconds).
    Called when user doesn't answer within timeout period.
    """
    try:
        call_session = CallSession.objects.get(session_id=session_id)
        
        if call_session.status not in ['initiated', 'scheduled']:
            logger.info(f"Call {session_id} already handled (status: {call_session.status})")
            return
        
        # Mark call as no-show
        with transaction.atomic():
            call_session.status = 'no_show'
            call_session.save(update_fields=['status'])
            
            # Send notification to both parties
            NotificationService.send_call_missed(
                patient_id=call_session.patient_id,
                consultant_id=call_session.consultant_id,
                session_id=session_id,
                call_type=call_session.call_type
            )
            
            # Log event
            logger.warning(
                f"Call {session_id} marked as no-show. "
                f"Patient: {call_session.patient_id}, "
                f"Consultant: {call_session.consultant_id}"
            )
            
    except CallSession.DoesNotExist:
        logger.error(f"Call session {session_id} not found")
    except Exception as e:
        logger.error(f"Error in handle_call_no_answer: {str(e)}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(
    name='consultations.handle_call_timeout',
    max_retries=3,
    default_retry_delay=60,
    bind=True,
    time_limit=600  # 10 minutes
)
def handle_call_timeout(self, session_id: str):
    """
    Handle call timeout after maximum duration exceeded.
    Gracefully ends ongoing calls that exceed time limits.
    """
    try:
        call_session = CallSession.objects.get(session_id=session_id)
        
        if call_session.status != 'ongoing':
            logger.info(f"Call {session_id} not ongoing, skipping timeout handling")
            return
        
        with transaction.atomic():
            # End the call
            call_session.end_call()
            
            # Notify both parties
            NotificationService.send_call_ended(
                patient_id=call_session.patient_id,
                consultant_id=call_session.consultant_id,
                session_id=session_id,
                duration_minutes=call_session.duration_minutes,
                reason='timeout'
            )
            
            logger.warning(f"Call {session_id} ended due to timeout. Duration: {call_session.duration_minutes}m")
            
    except CallSession.DoesNotExist:
        logger.error(f"Call session {session_id} not found")
    except Exception as e:
        logger.error(f"Error in handle_call_timeout: {str(e)}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(
    name='consultations.cleanup_stale_calls',
    max_retries=2,
    bind=True
)
def cleanup_stale_calls(self):
    """
    Cleanup stale/abandoned call sessions.
    Runs periodically to clean up calls stuck in initiated state.
    """
    try:
        stale_threshold = timezone.now() - timedelta(hours=1)
        
        stale_calls = CallSession.objects.filter(
            status__in=['initiated', 'scheduled'],
            created_at__lt=stale_threshold
        )
        
        count = 0
        for call in stale_calls:
            try:
                with transaction.atomic():
                    call.status = 'cancelled'
                    call.save(update_fields=['status'])
                    count += 1
                    
                    # Send notifications
                    NotificationService.send_call_cancelled(
                        patient_id=call.patient_id,
                        consultant_id=call.consultant_id,
                        session_id=call.session_id,
                        reason='expired'
                    )
            except Exception as e:
                logger.error(f"Error cleaning up call {call.session_id}: {str(e)}")
        
        logger.info(f"Cleaned up {count} stale calls")
        return {'cleaned': count}
        
    except Exception as e:
        logger.error(f"Error in cleanup_stale_calls: {str(e)}", exc_info=True)
        raise self.retry(exc=e)


# ==================== NOTIFICATION TASKS ====================

@shared_task(
    name='consultations.send_call_incoming_notification',
    max_retries=3,
    default_retry_delay=30,
    bind=True
)
def send_call_incoming_notification(self, session_id: str, patient_name: str, call_type: str):
    """
    Send incoming call notification via WebSocket.
    Includes retry logic for delivery guarantee.
    """
    try:
        call_session = CallSession.objects.select_related(
            'patient', 'consultant'
        ).get(session_id=session_id)
        
        channel_layer = get_channel_layer()
        
        # Send to consultant using notification_message routing
        async_to_sync(channel_layer.group_send)(
            f"user_{call_session.consultant_id}",
            {
                "type": "notification_message",
                "notification_type": "incoming_call",
                "session_id": session_id,
                "patient_id": str(call_session.patient_id),
                "patient_name": patient_name,
                "call_type": call_type,
                "timestamp": timezone.now().isoformat(),
            }
        )
        
        logger.info(f"Incoming call notification sent for {session_id}")
        
    except CallSession.DoesNotExist:
        logger.error(f"Call session {session_id} not found for notification")
    except Exception as e:
        logger.error(f"Error sending incoming call notification: {str(e)}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(
    name='consultations.send_connection_quality_alert',
    max_retries=2,
    bind=True
)
def send_connection_quality_alert(self, session_id: str, quality: str, stats: dict):
    """
    Send connection quality alerts when issues are detected.
    Enterprise-grade monitoring of call quality.
    """
    try:
        call_session = CallSession.objects.get(session_id=session_id)
        
        # Only send alert if quality is poor or lower
        quality_levels = {'excellent': 4, 'good': 3, 'fair': 2, 'poor': 1, 'failed': 0}
        if quality_levels.get(quality, 0) > 1:
            logger.debug(f"Call {session_id} quality acceptable: {quality}")
            return
        
        channel_layer = get_channel_layer()
        alert_payload = {
            "type": "connection_quality_alert",
            "session_id": session_id,
            "quality": quality,
            "stats": stats,
            "timestamp": timezone.now().isoformat(),
            "notification_type": NotificationType.CONNECTION_QUALITY.value,
        }
        
        # Send to both participants
        for user_id in [call_session.patient_id, call_session.consultant_id]:
            async_to_sync(channel_layer.group_send)(
                f"user_{user_id}",
                alert_payload
            )
        
        logger.warning(f"Connection quality alert for {session_id}: {quality}")
        
    except CallSession.DoesNotExist:
        logger.error(f"Call session {session_id} not found")
    except Exception as e:
        logger.error(f"Error sending quality alert: {str(e)}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(
    name='consultations.send_reconnection_alert',
    max_retries=2,
    bind=True
)
def send_reconnection_alert(self, session_id: str, reconnection_count: int):
    """
    Send reconnection alerts for unstable connections.
    Helps identify and monitor connectivity issues.
    """
    try:
        call_session = CallSession.objects.get(session_id=session_id)
        
        # Alert if reconnections exceed threshold (3+)
        if reconnection_count < 3:
            return
        
        channel_layer = get_channel_layer()
        
        for user_id in [call_session.patient_id, call_session.consultant_id]:
            async_to_sync(channel_layer.group_send)(
                f"user_{user_id}",
                {
                    "type": "reconnection_alert",
                    "session_id": session_id,
                    "reconnection_count": reconnection_count,
                    "timestamp": timezone.now().isoformat(),
                    "notification_type": NotificationType.RECONNECTION_ALERT.value,
                }
            )
        
        logger.warning(
            f"Reconnection alert for {session_id}: {reconnection_count} attempts"
        )
        
    except CallSession.DoesNotExist:
        logger.error(f"Call session {session_id} not found")
    except Exception as e:
        logger.error(f"Error sending reconnection alert: {str(e)}", exc_info=True)
        raise self.retry(exc=e)


# ==================== PERSISTENCE & ANALYTICS TASKS ====================

@shared_task(
    name='consultations.persist_call_metrics',
    max_retries=3,
    default_retry_delay=30,
    bind=True
)
def persist_call_metrics(self, session_id: str, metrics: dict):
    """
    Persist WebRTC and call metrics to database for analytics.
    Enterprise-grade call quality analysis.
    """
    try:
        call_session = CallSession.objects.get(session_id=session_id)
        
        with transaction.atomic():
            # Update existing stats
            current_stats = call_session.webrtc_stats or {}
            current_stats.update(metrics)
            
            call_session.webrtc_stats = current_stats
            call_session.last_ping_timestamp = timezone.now()
            call_session.save(update_fields=['webrtc_stats', 'last_ping_timestamp'])
            
            logger.debug(f"Metrics persisted for call {session_id}")
            
    except CallSession.DoesNotExist:
        logger.error(f"Call session {session_id} not found")
    except Exception as e:
        logger.error(f"Error persisting call metrics: {str(e)}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(
    name='consultations.generate_call_analytics',
    max_retries=2,
    bind=True
)
def generate_call_analytics(self, session_id: str):
    """
    Generate analytics after call completion.
    Calculate quality scores, connection health, and performance metrics.
    """
    try:
        call_session = CallSession.objects.get(session_id=session_id)
        
        if call_session.status != 'completed':
            logger.info(f"Call {session_id} not completed, skipping analytics")
            return
        
        # Calculate analytics
        analytics = {
            'connection_health': call_session.connection_health,
            'call_quality': call_session.connection_quality,
            'total_reconnections': call_session.reconnection_attempts,
            'total_ice_candidates': call_session.ice_candidates_count,
            'connection_type': call_session.connection_type,
            'duration_minutes': call_session.duration_minutes,
            'timestamp': timezone.now().isoformat(),
        }
        
        # Store in cache for quick access
        cache_key = f"call_analytics_{session_id}"
        cache.set(cache_key, analytics, timeout=86400)  # 24 hours
        
        logger.info(f"Analytics generated for call {session_id}: {analytics}")
        return analytics
        
    except CallSession.DoesNotExist:
        logger.error(f"Call session {session_id} not found")
    except Exception as e:
        logger.error(f"Error generating analytics: {str(e)}", exc_info=True)
        raise self.retry(exc=e)


# ==================== APPOINTMENT-BASED CALL TASKS ====================

@shared_task(
    name='consultations.auto_create_call_session',
    max_retries=2,
    bind=True
)
def auto_create_call_session(self, appointment_id: str):
    """
    Automatically create call session for confirmed appointments.
    Called when appointment time approaches.
    """
    try:
        appointment = Appointment.objects.select_related(
            'patient', 'consultant__user'
        ).get(id=appointment_id)
        
        if appointment.status != 'confirmed':
            logger.info(f"Appointment {appointment_id} not confirmed")
            return
        
        # Check if call session already exists
        existing_call = CallSession.objects.filter(
            patient=appointment.patient,
            consultant=appointment.consultant.user,
            scheduled_at__date=appointment.scheduled_datetime.date()
        ).first()
        
        if existing_call:
            logger.info(f"Call session already exists for appointment {appointment_id}")
            return
        
        # Create call session
        with transaction.atomic():
            call_session = CallSession.objects.create(
                session_id=f"apt_{appointment_id}",
                patient=appointment.patient,
                consultant=appointment.consultant.user,
                call_type='video',
                scheduled_at=appointment.scheduled_datetime,
                status='scheduled',
                consultation_fee=appointment.consultation_fee,
            )
            
            logger.info(f"Call session created for appointment {appointment_id}: {call_session.session_id}")
            
            # Send ONLY 'call_session_ready' notification (NOT incoming_call)
            # This notifies both parties that the call session is available
            # but DOES NOT trigger the incoming call ringtone/UI
            # The incoming_call notification will be sent when the consultant explicitly initiates the call
            NotificationService.send_call_session_ready(
                patient_id=appointment.patient_id,
                consultant_id=appointment.consultant.user_id,
                session_id=call_session.session_id,
                appointment_id=appointment_id
            )
        
        return call_session.session_id
        
    except Appointment.DoesNotExist:
        logger.error(f"Appointment {appointment_id} not found")
    except Exception as e:
        logger.error(f"Error creating call session: {str(e)}", exc_info=True)
        raise self.retry(exc=e)


# ==================== BATCH NOTIFICATION TASKS ====================

@shared_task(
    name='consultations.batch_send_notifications',
    max_retries=2,
    bind=True
)
def batch_send_notifications(self, user_ids: list, notification_data: dict):
    """
    Send same notification to multiple users efficiently.
    Used for bulk notifications like system announcements.
    """
    try:
        channel_layer = get_channel_layer()
        failed_users = []
        
        for user_id in user_ids:
            try:
                notification_data['user_id'] = str(user_id)
                notification_data['timestamp'] = timezone.now().isoformat()
                
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_id}",
                    notification_data
                )
            except Exception as e:
                logger.error(f"Failed to send notification to user {user_id}: {str(e)}")
                failed_users.append(user_id)
        
        logger.info(f"Batch notification sent to {len(user_ids) - len(failed_users)}/{len(user_ids)} users")
        return {
            'total': len(user_ids),
            'sent': len(user_ids) - len(failed_users),
            'failed': failed_users
        }
        
    except Exception as e:
        logger.error(f"Error in batch_send_notifications: {str(e)}", exc_info=True)
        raise self.retry(exc=e)


# ==================== MONITORING & LOGGING TASKS ====================

@shared_task(
    name='consultations.log_call_event',
    max_retries=1,
    bind=True
)
def log_call_event(self, session_id: str, event_type: str, event_data: dict):
    """
    Log call events for audit trail and debugging.
    Helps with troubleshooting and compliance.
    """
    try:
        call_session = CallSession.objects.get(session_id=session_id)
        
        event_log = {
            'session_id': session_id,
            'event_type': event_type,
            'event_data': event_data,
            'timestamp': timezone.now().isoformat(),
            'call_status': call_session.status,
            'duration_so_far': (
                (timezone.now() - call_session.started_at).total_seconds() / 60
                if call_session.started_at else 0
            ),
        }
        
        logger.info(f"Call event logged: {json.dumps(event_log)}")
        
    except CallSession.DoesNotExist:
        logger.warning(f"Call session {session_id} not found for event logging")
    except Exception as e:
        logger.error(f"Error logging call event: {str(e)}")
        # Don't retry for logging errors


@shared_task(
    name='consultations.monitor_active_calls',
    bind=True
)
def monitor_active_calls(self):
    """
    Monitor active calls and detect stalled connections.
    Proactive health monitoring for ongoing calls.
    """
    try:
        active_calls = CallSession.objects.filter(status='ongoing')
        
        monitoring_data = {
            'total_active': active_calls.count(),
            'by_type': {},
            'connection_issues': [],
            'timestamp': timezone.now().isoformat(),
        }
        
        for call in active_calls:
            # Group by call type
            call_type = call.call_type
            if call_type not in monitoring_data['by_type']:
                monitoring_data['by_type'][call_type] = 0
            monitoring_data['by_type'][call_type] += 1
            
            # Check for connection issues
            if call.reconnection_attempts > 3 or call.connection_quality == 'poor':
                monitoring_data['connection_issues'].append({
                    'session_id': call.session_id,
                    'reconnections': call.reconnection_attempts,
                    'quality': call.connection_quality,
                })
        
        logger.info(f"Active calls monitoring: {json.dumps(monitoring_data)}")
        return monitoring_data
        
    except Exception as e:
        logger.error(f"Error monitoring active calls: {str(e)}", exc_info=True)



