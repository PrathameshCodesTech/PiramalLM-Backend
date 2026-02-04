from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"companies", views.TenantCompanyViewSet, basename="company")
router.register(r"contacts", views.TenantContactViewSet, basename="contact")
router.register(r"kyc", views.TenantKYCViewSet, basename="kyc")
router.register(r"preferences", views.TenantPreferencesViewSet, basename="preferences")

urlpatterns = router.urls
