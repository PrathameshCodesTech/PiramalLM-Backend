from rest_framework.routers import DefaultRouter
from django.urls import path

from apps.accounts import views

router = DefaultRouter()

router.register(r"orgs", views.OrgViewSet)
router.register(r"companies", views.CompanyViewSet)
router.register(r"entities", views.EntityViewSet)
router.register(r"scopes", views.TenantScopeViewSet)
router.register(r"permissions", views.PermissionViewSet)
router.register(r"roles", views.RoleViewSet)
router.register(r"role-permissions", views.RolePermissionViewSet)
router.register(r"users", views.UserViewSet)
router.register(r"user-scopes", views.UserScopeViewSet)
router.register(r"memberships", views.ScopeMembershipViewSet)
router.register(r"credentials", views.UserCredentialViewSet)
router.register(r"user-profiles", views.UserProfileViewSet)

urlpatterns = [
    path("me/", views.me, name="accounts-me"),
    path("assign-site/", views.assign_site, name="accounts-assign-site"),
    path("change-password/", views.change_password, name="accounts-change-password"),
] + router.urls
