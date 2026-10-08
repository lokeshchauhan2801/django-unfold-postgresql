from django.urls import path

from .views import (
    chat_api,
    chat_page,
    conversation_detail,
    conversation_list,
    session_login,
    session_logout,
)


urlpatterns = [
    path("", chat_page, name="chat"),
    path("api/", chat_api, name="chat_api"),
    path("api/conversations/", conversation_list, name="conversation_list"),
    path(
        "api/conversations/<uuid:conversation_id>/",
        conversation_detail,
        name="conversation_detail",
    ),
    path("session/login/", session_login, name="chat_session_login"),
    path("session/logout/", session_logout, name="chat_session_logout"),
]