"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/core/', include('apps.core.urls')),
    path('api/v1/accounts/', include('apps.accounts.urls')),
    path('api/v1/properties/', include('apps.properties.urls')),
    path('api/v1/tenants/', include('apps.tenants.urls')),
    path('api/v1/leases/', include('apps.leases.urls')),
    path('api/v1/payments/', include('apps.payments.urls')),
    path('api/v1/billing/', include('apps.billing.urls')),
    path('api/v1/clauses/', include('apps.clauses.urls')),
    path('api/v1/maintenance/', include('apps.maintenance.urls')),
    path('api/v1/communications/', include('apps.communications.urls')),
    path('api/v1/reports/', include('apps.reports.urls')),
    path('api/v1/approvals/', include('apps.approvals.urls')),
]
