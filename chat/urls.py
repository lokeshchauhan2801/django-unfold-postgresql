from django.urls import path

from .views import (
    chat_api,
    chat_page,
    company_dashboard,
    company_members,
    company_meta,
    conversation_detail,
    conversation_list,
    embedded_chat_page,
    set_active_company,
    session_login,
    session_logout,
)


urlpatterns = [
    path("", chat_page, name="chat"),
    path("embedded/", embedded_chat_page, name="chat_embedded"),
    path("api/", chat_api, name="chat_api"),
    path("api/conversations/", conversation_list, name="conversation_list"),
    path(
        "api/conversations/<uuid:conversation_id>/",
        conversation_detail,
        name="conversation_detail",
    ),
    path("api/company/", company_meta, name="chat_company_meta"),
    path("api/company/members/", company_members, name="company_members"),
    path("api/company/dashboard/", company_dashboard, name="company_dashboard"),
    path("session/login/", session_login, name="chat_session_login"),
    path("session/logout/", session_logout, name="chat_session_logout"),
    path("session/company/", set_active_company, name="chat_set_active_company"),
]