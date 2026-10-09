import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model that extends AbstractUser.
    Uses UUID primary key. Auth models deliberately have no company FK
    because users can belong to multiple companies via CompanyMembership.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(unique=True)
    avatar_url = models.URLField(blank=True, null=True)
    bio = models.TextField(blank=True)

    # Use email as the login identifier
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_user"
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]

    def __str__(self) -> str:
        return self.email
