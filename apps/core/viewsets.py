from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.core.utils import get_active_scope


class ScopedViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_active_scope(self):
        return get_active_scope(self.request)

    def get_queryset(self):
        queryset = super().get_queryset()
        scope = self.get_active_scope()
        if hasattr(queryset, "for_scope"):
            return queryset.for_scope(scope)
        return queryset.filter(scope=scope)

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope)

    def perform_update(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope)
