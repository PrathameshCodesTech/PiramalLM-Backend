"""
Reports App URLs
================

URL routing for dashboard and reporting endpoints.
"""

from rest_framework.routers import DefaultRouter
from .views import DashboardViewSet

router = DefaultRouter()
router.register(r'dashboard', DashboardViewSet, basename='dashboard')

urlpatterns = router.urls
