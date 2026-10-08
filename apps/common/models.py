import uuid
from django.db import models

class UUIDModel(models.Model):
    """Abstract base model that uses UUID as primary key."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True

class TimestampedModel(models.Model):
    """Abstract base model that tracks creation and update times."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class BaseModel(UUIDModel, TimestampedModel):
    """Combined abstract base with UUID pk and timestamps."""
    class Meta:
        abstract = True

class SystemSetting(BaseModel):
    """Key-value store for system-level configuration."""
    key = models.CharField(max_length=100, unique=True, db_index=True)
    value = models.TextField()
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'common_system_settings'
        ordering = ['key']

    def __str__(self) -> str:
        return self.key
