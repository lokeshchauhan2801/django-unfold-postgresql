from django.contrib import admin
from django.contrib.admin import sites
from unfold.apps import DefaultAppConfig
from unfold.sites import UnfoldAdminSite

from company.access import is_active_company_admin


class CompanyAdminSite(UnfoldAdminSite):
    def has_permission(self, request):
        user = request.user
        return bool(
            user.is_active
            and (user.is_staff or is_active_company_admin(user))
        )


class CompanyAdminAppConfig(DefaultAppConfig):
    def ready(self):
        site = CompanyAdminSite()
        admin.site = site
        sites.site = site
