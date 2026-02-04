from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"ageing-buckets", views.AgeingBucketViewSet, basename="ageing-bucket")
router.register(r"ar-rules", views.ARRuleViewSet, basename="ar-rule")
router.register(r"invoices", views.InvoiceViewSet, basename="invoice")
router.register(r"payments", views.PaymentViewSet, basename="payment")
router.register(r"credit-notes", views.CreditNoteViewSet, basename="credit-note")
router.register(r"invoice-schedules", views.InvoiceScheduleViewSet, basename="invoice-schedule")
router.register(r"ar-summaries", views.ARSummaryViewSet, basename="ar-summary")
router.register(r"lease-rules", views.LeaseRulesViewSet, basename="lease-rules")

urlpatterns = router.urls
