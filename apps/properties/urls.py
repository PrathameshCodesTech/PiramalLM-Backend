from rest_framework.routers import DefaultRouter
from django.urls import path

from apps.properties import views

router = DefaultRouter()

router.register(r"amenities", views.AmenityViewSet)
router.register(r"rooms", views.RoomViewSet)
router.register(r"sites", views.SiteViewSet)
router.register(r"site-amenities", views.SiteAmenityViewSet)
router.register(r"towers", views.TowerViewSet)
router.register(r"floors", views.FloorViewSet)
router.register(r"units", views.UnitViewSet)
router.register(r"unit-area-reservations", views.UnitAreaReservationViewSet)
router.register(r"unit-amenities", views.UnitAmenityViewSet)
router.register(r"unit-rooms", views.UnitRoomViewSet)
router.register(r"asset-categories", views.AssetCategoryViewSet)
router.register(r"asset-items", views.AssetItemViewSet)
router.register(r"unit-assets", views.UnitAssetViewSet)
router.register(r"form-templates", views.FormTemplateViewSet)
router.register(r"form-template-versions", views.FormTemplateVersionViewSet)
router.register(r"form-fields", views.FormFieldViewSet)
router.register(r"site-unit-form-configs", views.SiteUnitFormConfigViewSet)
router.register(r"landlords", views.LandlordViewSet)
router.register(r"landlord-contacts", views.LandlordContactViewSet)
router.register(r"site-attachments", views.SiteAttachmentViewSet)

urlpatterns = router.urls
urlpatterns = [
    path("site-types/", views.site_type_choices, name="site-type-choices"),
] + urlpatterns
