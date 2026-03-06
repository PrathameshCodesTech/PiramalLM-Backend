from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Count, Q

from apps.core.viewsets import ScopedViewSet, InheritableScopedViewSet
from . import models, serializers


class ClauseCategoryViewSet(InheritableScopedViewSet):
    """
    ViewSet for clause categories.

    Uses InheritableScopedViewSet for upward visibility:
    - Child scopes see categories from parent scopes

    Endpoints:
    - GET /categories/ - List all categories (includes inherited from parent scopes)
    - POST /categories/ - Create category
    - GET /categories/{id}/ - Get category details
    - PATCH /categories/{id}/ - Update category
    - DELETE /categories/{id}/ - Delete category
    - GET /categories/tree/ - Get category tree structure
    """

    queryset = models.ClauseCategory.objects.all()
    serializer_class = serializers.ClauseCategorySerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.ClauseCategoryListSerializer
        if self.action == "tree":
            return serializers.ClauseCategoryTreeSerializer
        return serializers.ClauseCategorySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter by parent for nested categories
        parent_id = self.request.query_params.get("parent_id")
        if parent_id:
            if parent_id == "null" or parent_id == "root":
                queryset = queryset.filter(parent__isnull=True)
            else:
                queryset = queryset.filter(parent_id=parent_id)
        return queryset

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=False, methods=["get"])
    def tree(self, request):
        """Get category tree structure."""
        scope = self.get_active_scope()
        root_categories = models.ClauseCategory.objects.filter(
            scope=scope,
            parent__isnull=True
        ).prefetch_related("children")

        serializer = serializers.ClauseCategoryTreeSerializer(root_categories, many=True)
        return Response(serializer.data)


class ClauseViewSet(InheritableScopedViewSet):
    """
    ViewSet for clauses.

    Uses InheritableScopedViewSet for upward visibility:
    - Child scopes see clauses from parent scopes

    Endpoints:
    - GET / - List all clauses (includes inherited from parent scopes)
    - POST / - Create clause with initial version
    - GET /{id}/ - Get clause details
    - PATCH /{id}/ - Update clause
    - DELETE /{id}/ - Delete clause
    - GET /{id}/versions/ - List clause versions
    - POST /{id}/bump/ - Create new version (bump)
    - POST /{id}/duplicate/ - Duplicate clause
    """

    queryset = models.Clause.objects.all()
    serializer_class = serializers.ClauseSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.ClauseListSerializer
        if self.action == "retrieve":
            return serializers.ClauseDetailSerializer
        if self.action == "create":
            return serializers.ClauseCreateSerializer
        return serializers.ClauseSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Search by title or clause_id
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(clause_id__icontains=search)
            )

        # Filter by category
        category_id = self.request.query_params.get("category")
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by applies_to
        applies_to = self.request.query_params.get("applies_to")
        if applies_to:
            queryset = queryset.filter(applies_to=applies_to)

        # Filter by clause_type
        clause_type = self.request.query_params.get("clause_type")
        if clause_type:
            queryset = queryset.filter(clause_type=clause_type)

        return queryset.select_related("category", "owner").prefetch_related("versions")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(
            scope=scope,
            created_by=self.request.user,
            owner=self.request.user
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        """List all versions of a clause."""
        clause = self.get_object()
        versions = clause.versions.all().order_by("-major_version", "-minor_version")

        page = self.paginate_queryset(versions)
        if page is not None:
            serializer = serializers.ClauseVersionListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = serializers.ClauseVersionListSerializer(versions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def bump(self, request, pk=None):
        """Create a new version (bump) of the clause."""
        clause = self.get_object()
        scope = self.get_active_scope()

        serializer = serializers.ClauseVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        bump_type = serializer.validated_data["bump"]
        change_summary = serializer.validated_data["change_summary"]
        body_text = serializer.validated_data.get("body_text", "")
        config = serializer.validated_data.get("config", {})

        # Calculate new version numbers
        if bump_type == models.ClauseVersion.BumpType.MAJOR:
            new_major = clause.current_version + 1
            new_minor = 0
        else:  # MINOR
            new_major = clause.current_version
            new_minor = clause.current_minor_version + 1

        # Get current version's content as base if not provided
        try:
            current_version = clause.versions.filter(
                version_status=models.ClauseVersion.VersionStatus.CURRENT
            ).first()
            if current_version:
                if not body_text:
                    body_text = current_version.body_text
                if not config:
                    config = current_version.config
        except Exception:
            pass

        # Create new version
        new_version = models.ClauseVersion.objects.create(
            clause=clause,
            scope=scope,
            major_version=new_major,
            minor_version=new_minor,
            version_status=models.ClauseVersion.VersionStatus.CURRENT,
            change_summary=change_summary,
            body_text=body_text,
            config=config,
            bump_type=bump_type,
            created_by=request.user
        )

        # Update clause version tracking
        clause.current_version = new_major
        clause.current_minor_version = new_minor
        clause.updated_by = request.user
        clause.save()

        return Response(
            serializers.ClauseVersionSerializer(new_version).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        """Duplicate a clause."""
        original = self.get_object()
        scope = self.get_active_scope()

        # Get suffix from request or default
        suffix = request.data.get("suffix", "(Copy)")

        # Create new clause
        new_clause = models.Clause.objects.create(
            scope=scope,
            title=f"{original.title} {suffix}",
            category=original.category,
            applies_to=original.applies_to,
            status=models.Clause.Status.DRAFT,
            owner=request.user,
            created_by=request.user
        )

        # Copy current version
        try:
            current_version = original.versions.filter(
                version_status=models.ClauseVersion.VersionStatus.CURRENT
            ).first()
            if current_version:
                models.ClauseVersion.objects.create(
                    clause=new_clause,
                    scope=scope,
                    major_version=1,
                    minor_version=0,
                    version_status=models.ClauseVersion.VersionStatus.CURRENT,
                    change_summary=f"Duplicated from {original.clause_id}",
                    body_text=current_version.body_text,
                    config=current_version.config,
                    created_by=request.user
                )
        except Exception:
            # Create empty version if no source version
            models.ClauseVersion.objects.create(
                clause=new_clause,
                scope=scope,
                major_version=1,
                minor_version=0,
                version_status=models.ClauseVersion.VersionStatus.CURRENT,
                change_summary=f"Duplicated from {original.clause_id}",
                created_by=request.user
            )

        return Response(
            serializers.ClauseDetailSerializer(new_clause).data,
            status=status.HTTP_201_CREATED
        )


class ClauseVersionViewSet(InheritableScopedViewSet):
    """
    ViewSet for clause versions (read-only, creation via clause.bump).

    Uses InheritableScopedViewSet for upward visibility:
    - Child scopes see versions from parent scopes

    Endpoints:
    - GET /versions/ - List all versions (includes inherited from parent scopes)
    - GET /versions/{id}/ - Get version details
    """

    queryset = models.ClauseVersion.objects.all()
    serializer_class = serializers.ClauseVersionSerializer
    http_method_names = ["get", "head", "options"]

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.ClauseVersionListSerializer
        return serializers.ClauseVersionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by clause
        clause_id = self.request.query_params.get("clause_id")
        if clause_id:
            queryset = queryset.filter(clause_id=clause_id)

        # Filter by status
        version_status = self.request.query_params.get("version_status")
        if version_status:
            queryset = queryset.filter(version_status=version_status)

        return queryset.select_related("clause", "created_by")


class ClauseDocumentViewSet(InheritableScopedViewSet):
    """
    ViewSet for clause documents.

    Uses InheritableScopedViewSet for upward visibility:
    - Child scopes see documents from parent scopes

    Endpoints:
    - GET /documents/ - List all documents (includes inherited from parent scopes)
    - POST /documents/ - Upload document
    - GET /documents/{id}/ - Get document details
    - PATCH /documents/{id}/ - Update document metadata
    - DELETE /documents/{id}/ - Delete document
    """

    queryset = models.ClauseDocument.objects.all()
    serializer_class = serializers.ClauseDocumentSerializer
    parser_classes = (MultiPartParser, FormParser)

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.ClauseDocumentListSerializer
        if self.action == "create":
            return serializers.ClauseDocumentUploadSerializer
        return serializers.ClauseDocumentSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Search by name
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)

        # Filter by document type
        document_type = self.request.query_params.get("document_type")
        if document_type:
            queryset = queryset.filter(document_type=document_type)

        return queryset.select_related("uploaded_by").prefetch_related("clause_links")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(
            scope=scope,
            created_by=self.request.user,
            uploaded_by=self.request.user
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class ClauseDocumentLinkViewSet(InheritableScopedViewSet):
    """
    ViewSet for document-clause links.

    Uses InheritableScopedViewSet for upward visibility:
    - Child scopes see links from parent scopes

    Endpoints:
    - GET /document-links/ - List all links (includes inherited from parent scopes)
    - POST /document-links/ - Create link
    - DELETE /document-links/{id}/ - Delete link
    """

    queryset = models.ClauseDocumentLink.objects.all()
    serializer_class = serializers.ClauseDocumentLinkSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.ClauseDocumentLinkCreateSerializer
        return serializers.ClauseDocumentLinkSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by document
        document_id = self.request.query_params.get("document_id")
        if document_id:
            queryset = queryset.filter(document_id=document_id)

        # Filter by clause
        clause_id = self.request.query_params.get("clause_id")
        if clause_id:
            queryset = queryset.filter(clause_id=clause_id)

        return queryset.select_related("document", "clause")

    def perform_create(self, serializer):
        scope = self.get_active_scope()
        serializer.save(scope=scope, created_by=self.request.user)


class ClauseUsageViewSet(ScopedViewSet):
    """
    ViewSet for clause usage in agreements.

    Endpoints:
    - GET /usages/ - List all usages
    - POST /usages/ - Attach clause to agreement
    - GET /usages/{id}/ - Get usage details
    - PATCH /usages/{id}/ - Update custom config
    - DELETE /usages/{id}/ - Remove clause from agreement
    - GET /usages/by-agreement/{agreement_id}/ - Get all clauses for agreement
    - GET /usages/by-clause/{clause_id}/ - Get all agreements using clause
    """

    queryset = models.ClauseUsage.objects.all()
    serializer_class = serializers.ClauseUsageSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.ClauseUsageCreateSerializer
        return serializers.ClauseUsageSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by agreement
        agreement_id = self.request.query_params.get("agreement_id")
        if agreement_id:
            queryset = queryset.filter(agreement_id=agreement_id)

        # Filter by clause
        clause_id = self.request.query_params.get("clause_id")
        if clause_id:
            queryset = queryset.filter(clause_id=clause_id)

        return queryset.select_related(
            "clause", "clause_version", "agreement"
        )

    def perform_create(self, serializer):
        scope = self.get_active_scope()

        # Auto-select current version if not specified
        clause = serializer.validated_data.get("clause")
        clause_version = serializer.validated_data.get("clause_version")

        if not clause_version and clause:
            clause_version = clause.versions.filter(
                version_status=models.ClauseVersion.VersionStatus.CURRENT
            ).first()

        instance = serializer.save(
            scope=scope,
            clause_version=clause_version,
            created_by=self.request.user,
        )
        try:
            instance.apply_to_agreement()
        except Exception:
            pass

    def perform_update(self, serializer):
        instance = serializer.save(updated_by=self.request.user)
        try:
            instance.apply_to_agreement()
        except Exception:
            pass

    @action(detail=False, methods=["get"], url_path="by-agreement/(?P<agreement_id>[^/.]+)")
    def by_agreement(self, request, agreement_id=None):
        """Get all clause usages for an agreement, ordered by sort_order."""
        scope = self.get_active_scope()
        usages = models.ClauseUsage.objects.filter(
            agreement_id=agreement_id,
            scope=scope
        ).select_related("clause", "clause_version").order_by("sort_order", "id")

        serializer = self.get_serializer(usages, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="by-clause/(?P<clause_id>[^/.]+)")
    def by_clause(self, request, clause_id=None):
        """Get all agreements using a clause."""
        scope = self.get_active_scope()
        usages = models.ClauseUsage.objects.filter(
            clause_id=clause_id,
            scope=scope
        ).select_related("agreement")

        serializer = self.get_serializer(usages, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="reorder")
    def reorder(self, request):
        """Reorder clause usages within an agreement section.

        Payload: {"items": [{"id": 1, "sort_order": 0}, {"id": 2, "sort_order": 1}, ...]}
        """
        items = request.data.get("items")
        if not isinstance(items, list):
            return Response({"detail": "items must be a list."}, status=status.HTTP_400_BAD_REQUEST)

        scope = self.get_active_scope()
        ids = [item.get("id") for item in items if item.get("id") is not None]
        usages = {u.id: u for u in models.ClauseUsage.objects.filter(id__in=ids, scope=scope)}

        for item in items:
            uid = item.get("id")
            new_order = item.get("sort_order")
            if uid in usages and new_order is not None:
                usages[uid].sort_order = new_order

        models.ClauseUsage.objects.bulk_update(list(usages.values()), ["sort_order"])
        return Response({"detail": f"Reordered {len(usages)} clause(s)."})


class ClauseLibraryStatsViewSet(InheritableScopedViewSet):
    """
    ViewSet for clause library statistics.

    Uses InheritableScopedViewSet to include inherited clauses in stats.

    Endpoints:
    - GET /stats/summary/ - Get overall stats (includes inherited from parent scopes)
    - GET /stats/by-category/ - Get stats by category
    """

    queryset = models.Clause.objects.all()
    serializer_class = serializers.ClauseListSerializer

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Get overall clause library statistics (includes inherited from parent scopes)."""
        scope = self.get_active_scope()
        scope_filter = self.get_inheritable_scope_filter(scope)

        total_clauses = models.Clause.objects.filter(scope_filter).count()
        active_clauses = models.Clause.objects.filter(
            scope_filter, status=models.Clause.Status.ACTIVE
        ).count()
        draft_clauses = models.Clause.objects.filter(
            scope_filter, status=models.Clause.Status.DRAFT
        ).count()
        archived_clauses = models.Clause.objects.filter(
            scope_filter, status=models.Clause.Status.ARCHIVED
        ).count()

        total_documents = models.ClauseDocument.objects.filter(scope_filter).count()
        total_categories = models.ClauseCategory.objects.filter(scope_filter).count()
        total_versions = models.ClauseVersion.objects.filter(scope_filter).count()

        return Response({
            "total_clauses": total_clauses,
            "active_clauses": active_clauses,
            "draft_clauses": draft_clauses,
            "archived_clauses": archived_clauses,
            "total_documents": total_documents,
            "total_categories": total_categories,
            "total_versions": total_versions,
        })

    @action(detail=False, methods=["get"], url_path="by-category")
    def by_category(self, request):
        """Get clause counts by category (includes inherited from parent scopes)."""
        scope = self.get_active_scope()
        scope_filter = self.get_inheritable_scope_filter(scope)

        categories = models.ClauseCategory.objects.filter(
            scope_filter
        ).annotate(
            clause_count=Count("clauses"),
            active_count=Count(
                "clauses",
                filter=Q(clauses__status=models.Clause.Status.ACTIVE)
            )
        ).values("id", "name", "clause_count", "active_count")

        return Response(list(categories))
