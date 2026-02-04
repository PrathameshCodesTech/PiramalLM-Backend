from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"agreements", views.AgreementViewSet, basename="agreement")
router.register(r"allocations", views.UnitAllocationViewSet, basename="allocation")
router.register(r"documents", views.DocumentViewSet, basename="document")
router.register(r"notes", views.NoteViewSet, basename="note")
router.register(r"availability", views.AvailabilityViewSet, basename="availability")

urlpatterns = router.urls
