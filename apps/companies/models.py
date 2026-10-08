import uuid
from django.conf import settings
from django.db import models
from apps.common.models import BaseModel


class Company(BaseModel):
    """Represents a tenant organisation."""
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to='companies/logos/', null=True, blank=True)
    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    settings_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'companies'
        ordering = ['name']
        verbose_name_plural = 'companies'

    def __str__(self) -> str:
        return self.name


class CompanyMembership(BaseModel):
    """Links a user to a company with a role."""

    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        ADMIN = 'admin', 'Admin'
        MEMBER = 'member', 'Member'
        VIEWER = 'viewer', 'Viewer'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INVITED = 'invited', 'Invited'
        SUSPENDED = 'suspended', 'Suspended'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company_memberships',
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'company_memberships'
        unique_together = ('user', 'company')
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['company', 'role']),
        ]

    def __str__(self) -> str:
        return f'{self.user} - {self.company} ({self.role})'
