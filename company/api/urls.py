from rest_framework.routers import DefaultRouter

from .views import CompanyMembershipViewSet, CompanyViewSet

router = DefaultRouter()
router.register("companies", CompanyViewSet, basename="company")
router.register("memberships", CompanyMembershipViewSet, basename="company-membership")

urlpatterns = router.urls
