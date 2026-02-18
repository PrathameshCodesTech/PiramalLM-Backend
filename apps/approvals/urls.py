from rest_framework.routers import DefaultRouter

from apps.approvals.views import ApprovalRuleViewSet

router = DefaultRouter()
router.register(r"rules", ApprovalRuleViewSet, basename="approval-rule")

urlpatterns = router.urls
