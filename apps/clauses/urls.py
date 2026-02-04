from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"categories", views.ClauseCategoryViewSet, basename="clause-category")
router.register(r"clauses", views.ClauseViewSet, basename="clause")
router.register(r"versions", views.ClauseVersionViewSet, basename="clause-version")
router.register(r"documents", views.ClauseDocumentViewSet, basename="clause-document")
router.register(r"document-links", views.ClauseDocumentLinkViewSet, basename="clause-document-link")
router.register(r"usages", views.ClauseUsageViewSet, basename="clause-usage")
router.register(r"stats", views.ClauseLibraryStatsViewSet, basename="clause-stats")

urlpatterns = router.urls
