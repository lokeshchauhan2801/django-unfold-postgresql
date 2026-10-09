import logging
import uuid
from typing import Any

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Unified exception handler that returns consistent JSON error responses."""
    response = exception_handler(exc, context)
    request = context.get('request')
    request_id = getattr(request, 'request_id', str(uuid.uuid4())) if request else str(uuid.uuid4())

    if response is not None:
        if isinstance(exc, ValidationError):
            return Response(
                {
                    'success': False,
                    'error': {'code': 'VALIDATION_ERROR', 'message': 'Invalid input data.', 'details': response.data},
                    'request_id': request_id,
                },
                status=response.status_code,
            )
        if isinstance(exc, NotAuthenticated):
            return Response(
                {'success': False, 'error': {'code': 'UNAUTHENTICATED', 'message': 'Authentication required.'}, 'request_id': request_id},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if isinstance(exc, AuthenticationFailed):
            return Response(
                {'success': False, 'error': {'code': 'AUTHENTICATION_FAILED', 'message': 'Invalid credentials.'}, 'request_id': request_id},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if isinstance(exc, PermissionDenied):
            return Response(
                {'success': False, 'error': {'code': 'PERMISSION_DENIED', 'message': 'You do not have permission.'}, 'request_id': request_id},
                status=status.HTTP_403_FORBIDDEN,
            )
        if isinstance(exc, Http404):
            return Response(
                {'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Resource not found.'}, 'request_id': request_id},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {'success': False, 'error': {'code': 'SERVER_ERROR', 'message': str(exc)}, 'request_id': request_id},
            status=response.status_code,
        )

    logger.exception('Unhandled exception [request_id=%s]: %s', request_id, exc)
    return None
