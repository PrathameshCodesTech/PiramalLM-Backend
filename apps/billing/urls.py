from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()

# Existing viewsets
router.register(r"ageing-buckets", views.AgeingBucketViewSet, basename="ageing-bucket")
router.register(r"ar-rules", views.ARRuleViewSet, basename="ar-rule")
router.register(r"invoices", views.InvoiceViewSet, basename="invoice")
router.register(r"invoice-attachments", views.InvoiceAttachmentViewSet, basename="invoice-attachment")
router.register(r"payments", views.PaymentViewSet, basename="payment")
router.register(r"credit-notes", views.CreditNoteViewSet, basename="credit-note")
router.register(r"invoice-schedules", views.InvoiceScheduleViewSet, basename="invoice-schedule")
router.register(r"ar-summaries", views.ARSummaryViewSet, basename="ar-summary")
router.register(r"rent-schedule-lines", views.RentScheduleLineViewSet, basename="rent-schedule-line")
router.register(r"lease-rules", views.LeaseRulesViewSet, basename="lease-rules")

# New viewsets (Tab-based configuration)
router.register(r"ageing-config", views.AgeingConfigViewSet, basename="ageing-config")
router.register(r"site-billing-configs", views.SiteBillingConfigViewSet, basename="site-billing-config")
router.register(r"billing-rules", views.BillingRuleViewSet, basename="billing-rule")
router.register(r"dispute-rules", views.DisputeRuleViewSet, basename="dispute-rule")
router.register(r"credit-rules", views.CreditRuleViewSet, basename="credit-rule")
router.register(r"ar-global-settings", views.ARGlobalSettingsViewSet, basename="ar-global-settings")
router.register(r"pending-actions", views.PendingActionViewSet, basename="pending-action")

urlpatterns = router.urls + [
    # Bundle endpoints for fetching all config at once
    path("config/", views.BillingConfigBundleView.as_view(), name="billing-config-bundle"),
    path("site/<int:site_id>/config/", views.SiteBillingConfigBundleView.as_view(), name="site-billing-config-bundle"),
    path("receivables/", views.ReceivablesListAPIView.as_view(), name="receivables-list"),
    path("rent-schedule-kpis/", views.RentScheduleKPIsAPIView.as_view(), name="rent-schedule-kpis"),
    path("revenue-recognition/", views.RevenueRecognitionAPIView.as_view(), name="revenue-recognition"),
    path("revenue-recognition/export/", views.RevenueRecognitionExportAPIView.as_view(), name="revenue-recognition-export"),
]
