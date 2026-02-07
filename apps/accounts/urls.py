from rest_framework.routers import DefaultRouter
from django.urls import path

from apps.accounts import views
from apps.accounts.views_org_tree import org_tree_list, org_tree_detail

router = DefaultRouter()

router.register(r"orgs", views.OrgViewSet)
router.register(r"companies", views.CompanyViewSet)
router.register(r"entities", views.EntityViewSet)
router.register(r"scopes", views.TenantScopeViewSet)
router.register(r"permissions", views.PermissionViewSet)
router.register(r"roles", views.RoleViewSet)
router.register(r"role-permissions", views.RolePermissionViewSet)
router.register(r"users", views.UserViewSet)
router.register(r"memberships", views.ScopeMembershipViewSet)
router.register(r"user-profiles", views.UserProfileViewSet)

urlpatterns = [
    path("me/", views.me, name="accounts-me"),
    path("me/available-scopes/", views.available_scopes, name="accounts-available-scopes"),
    path("org-tree/", org_tree_list, name="accounts-org-tree-list"),
    path("org-tree/<int:org_id>/", org_tree_detail, name="accounts-org-tree-detail"),
    path("change-password/", views.change_password, name="accounts-change-password"),
] + router.urls
