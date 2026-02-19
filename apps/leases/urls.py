from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()

# Escalation templates (master data - inheritable)
router.register(r"escalation-templates", views.EscalationTemplateViewSet, basename="escalation-template")

# Agreement structure & sections
router.register(r"agreement-structures", views.AgreementStructureViewSet, basename="agreement-structure")
router.register(r"agreement-sections", views.AgreementSectionViewSet, basename="agreement-section")

# Core lease endpoints
router.register(r"agreements", views.AgreementViewSet, basename="agreement")
router.register(r"allocations", views.UnitAllocationViewSet, basename="allocation")
router.register(r"documents", views.DocumentViewSet, basename="document")
router.register(r"notes", views.NoteViewSet, basename="note")
router.register(r"availability", views.AvailabilityViewSet, basename="availability")

# Amendment endpoints
router.register(r"amendments", views.LeaseAmendmentViewSet, basename="amendment")
router.register(r"amendment-approvals", views.AmendmentApprovalViewSet, basename="amendment-approval")
router.register(r"amendment-attachments", views.AmendmentAttachmentViewSet, basename="amendment-attachment")

# Linked document endpoints
router.register(r"linked-documents", views.LeaseLinkedDocumentViewSet, basename="linked-document")
router.register(r"document-approvals", views.DocumentApprovalViewSet, basename="document-approval")

# Clause configuration bundle endpoint
router.register(r"clause-config", views.LeaseClauseConfigBundleView, basename="clause-config")

urlpatterns = router.urls
