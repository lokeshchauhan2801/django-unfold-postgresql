import uuid
from django.conf import settings
from django.db import models
from basics.models import BaseModel


class AuditLog(BaseModel):
    """Immutable audit record for every significant operation."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
    )
    company = models.ForeignKey(
        'company.Company',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
    )
    action = models.CharField(max_length=100, db_index=True)
    resource_type = models.CharField(max_length=100, blank=True, db_index=True)
    resource_id = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['company', 'action']),
            models.Index(fields=['resource_type', 'resource_id']),
        ]

    def __str__(self) -> str:
        return f'{self.action} by {self.user} at {self.created_at}'
