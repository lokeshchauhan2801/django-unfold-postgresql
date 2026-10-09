from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

from chat.views import admin_login_redirect
from docs.views import document_file


def home_redirect(request):
    return redirect("/chat/")


urlpatterns = [
    path("admin/login/", admin_login_redirect, name="shared_admin_login"),
    path("admin/", admin.site.urls),
    path("", home_redirect, name="home"),

    # ------------------------------------------------------------------ #
    #  API v1 — pattern: api/v1/<app>/<model>/                            #
    # ------------------------------------------------------------------ #

    # Auth: register, login, logout, me, token/refresh
    path("api/v1/auth/", include("auth.api.urls")),

    # Company: companies, memberships
    path("api/v1/company/", include("company.api.urls")),

    # Scrapper: documents, document-chunks, queue-messages
    path("api/v1/scrapper/", include("scrapper.api.urls")),

    # ------------------------------------------------------------------ #
    #  Main application views                                             #
    # ------------------------------------------------------------------ #
    path("chat/", include("chat.urls")),
    path("documents/", include("docs.urls")),
    path("media/documents/<path:file_path>", document_file, name="document_file"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
