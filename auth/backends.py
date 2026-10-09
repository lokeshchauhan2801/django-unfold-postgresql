from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class UsernameOrEmailBackend(ModelBackend):
    """Authenticate custom-user accounts by either username or email."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get(get_user_model().USERNAME_FIELD)
        if not identifier or not password:
            return None

        user_model = get_user_model()
        matches = user_model._default_manager.filter(
            Q(username__iexact=identifier) | Q(email__iexact=identifier)
        )
        if matches.count() != 1:
            return super().authenticate(
                request,
                username=identifier,
                password=password,
            )

        user = matches.first()
        return super().authenticate(
            request,
            username=getattr(user, user_model.USERNAME_FIELD),
            password=password,
        )
