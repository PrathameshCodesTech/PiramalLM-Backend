from rest_framework import serializers
from . import models


# ===================== Category Serializers =====================

class ClauseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ClauseCategory
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class ClauseCategoryListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for dropdowns."""
    children_count = serializers.SerializerMethodField()

    class Meta:
        model = models.ClauseCategory
        fields = ("id", "name", "description", "sort_order", "parent", "children_count")

    def get_children_count(self, obj):
        return obj.children.count()


class ClauseCategoryTreeSerializer(serializers.ModelSerializer):
    """Recursive serializer for category tree."""
    children = serializers.SerializerMethodField()

    class Meta:
        model = models.ClauseCategory
        fields = ("id", "name", "description", "sort_order", "children")

    def get_children(self, obj):
        children = obj.children.all()
        return ClauseCategoryTreeSerializer(children, many=True).data


# ===================== Clause Version Serializers =====================

class ClauseVersionSerializer(serializers.ModelSerializer):
    version_label = serializers.ReadOnlyField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = models.ClauseVersion
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "clause", "major_version", "minor_version"
        )

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return None


class ClauseVersionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for version history list."""
    version_label = serializers.ReadOnlyField()
    created_by_name = serializers.SerializerMethodField()
    clause_title = serializers.CharField(source="clause.title", read_only=True)

    class Meta:
        model = models.ClauseVersion
        fields = (
            "id", "clause", "clause_title", "version_label", "major_version", "minor_version",
            "version_status", "change_summary", "bump_type",
            "created_at", "created_by_name"
        )

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return None


class ClauseVersionCreateSerializer(serializers.Serializer):
    """Serializer for bumping clause version."""
    bump = serializers.ChoiceField(choices=models.ClauseVersion.BumpType.choices)
    change_summary = serializers.CharField(required=True)
    body_text = serializers.CharField(required=False, allow_blank=True)
    config = serializers.JSONField(required=False, default=dict)


# ===================== Clause Serializers =====================

class ClauseListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    category_name = serializers.CharField(source="category.name", read_only=True)
    version_label = serializers.ReadOnlyField()
    owner_name = serializers.SerializerMethodField()
    current_version_config = serializers.SerializerMethodField()

    class Meta:
        model = models.Clause
        fields = (
            "id", "clause_id", "title", "category", "category_name",
            "applies_to", "clause_type", "status", "version_label",
            "owner", "owner_name", "updated_at", "current_version_config",
        )

    def get_owner_name(self, obj):
        if obj.owner:
            return obj.owner.get_full_name() or obj.owner.email
        return None

    def get_current_version_config(self, obj):
        try:
            for v in obj.versions.all():
                if v.version_status == models.ClauseVersion.VersionStatus.CURRENT:
                    return v.config or {}
        except Exception:
            pass
        return {}


class ClauseSerializer(serializers.ModelSerializer):
    version_label = serializers.ReadOnlyField()

    class Meta:
        model = models.Clause
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "clause_id", "current_version", "current_minor_version"
        )


class ClauseDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer with current version and documents."""
    category_name = serializers.CharField(source="category.name", read_only=True)
    version_label = serializers.ReadOnlyField()
    owner_name = serializers.SerializerMethodField()
    current_version_data = serializers.SerializerMethodField()
    linked_documents = serializers.SerializerMethodField()
    version_count = serializers.SerializerMethodField()

    class Meta:
        model = models.Clause
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )

    def get_owner_name(self, obj):
        if obj.owner:
            return obj.owner.get_full_name() or obj.owner.email
        return None

    def get_current_version_data(self, obj):
        try:
            current = obj.versions.filter(
                version_status=models.ClauseVersion.VersionStatus.CURRENT
            ).first()
            if current:
                return ClauseVersionSerializer(current).data
        except Exception:
            pass
        return None

    def get_linked_documents(self, obj):
        links = obj.document_links.select_related("document").all()
        return [
            {
                "link_id": link.id,
                "document_id": link.document.id,
                "document_name": link.document.name,
                "document_type": link.document.document_type,
                "file_url": link.document.file.url if link.document.file else None,
            }
            for link in links
        ]

    def get_version_count(self, obj):
        return obj.versions.count()


class ClauseCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a clause with initial version."""
    initial_change_summary = serializers.CharField(required=False, allow_blank=True)
    initial_body_text = serializers.CharField(required=False, allow_blank=True)
    initial_config = serializers.JSONField(required=False, default=dict)

    class Meta:
        model = models.Clause
        fields = (
            "title", "category", "applies_to", "clause_type", "status",
            "initial_change_summary", "initial_body_text", "initial_config",
        )

    def create(self, validated_data):
        # Extract version data
        change_summary = validated_data.pop("initial_change_summary", "")
        body_text = validated_data.pop("initial_body_text", "")
        config = validated_data.pop("initial_config", {})

        # Create clause
        clause = models.Clause.objects.create(**validated_data)

        # Create initial version
        models.ClauseVersion.objects.create(
            clause=clause,
            scope=clause.scope,
            major_version=1,
            minor_version=0,
            version_status=models.ClauseVersion.VersionStatus.CURRENT,
            change_summary=change_summary or "Initial version",
            body_text=body_text,
            config=config,
            created_by=self.context["request"].user
        )

        return clause


# ===================== Document Serializers =====================

class ClauseDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = models.ClauseDocument
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at",
            "file_size", "uploaded_by"
        )

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name() or obj.uploaded_by.email
        return None

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class ClauseDocumentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for document list."""
    uploaded_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    linked_clauses = serializers.SerializerMethodField()

    class Meta:
        model = models.ClauseDocument
        fields = (
            "id", "name", "document_type", "file_size", "file_url",
            "uploaded_by", "uploaded_by_name", "created_at", "linked_clauses"
        )

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name() or obj.uploaded_by.email
        return None

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None

    def get_linked_clauses(self, obj):
        links = obj.clause_links.select_related("clause").all()
        return [
            {
                "link_id": link.id,
                "clause_id": link.clause.id,
                "clause_title": link.clause.title,
            }
            for link in links
        ]


class ClauseDocumentUploadSerializer(serializers.ModelSerializer):
    """Serializer for uploading documents with optional clause linking."""
    link_to_clauses = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        write_only=True
    )

    class Meta:
        model = models.ClauseDocument
        fields = ("name", "document_type", "file", "link_to_clauses")

    def create(self, validated_data):
        clause_ids = validated_data.pop("link_to_clauses", [])

        # Create document
        document = models.ClauseDocument.objects.create(**validated_data)

        # Create links
        for clause_id in clause_ids:
            models.ClauseDocumentLink.objects.create(
                document=document,
                clause_id=clause_id,
                scope=document.scope,
                created_by=self.context["request"].user
            )

        return document


# ===================== Document Link Serializers =====================

class ClauseDocumentLinkSerializer(serializers.ModelSerializer):
    document_name = serializers.CharField(source="document.name", read_only=True)
    clause_title = serializers.CharField(source="clause.title", read_only=True)

    class Meta:
        model = models.ClauseDocumentLink
        fields = "__all__"
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "created_by", "updated_by", "is_active", "deleted_at"
        )


class ClauseDocumentLinkCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating document-clause links."""

    class Meta:
        model = models.ClauseDocumentLink
        fields = ("document", "clause")


# ===================== Clause Usage Serializers =====================

class ClauseUsageSerializer(serializers.ModelSerializer):
    clause_title = serializers.CharField(source="clause.title", read_only=True)
    clause_id_display = serializers.CharField(source="clause.clause_id", read_only=True)
    clause_type = serializers.CharField(source="clause.clause_type", read_only=True)
    agreement_lease_id = serializers.CharField(source="agreement.lease_id", read_only=True)
    version_label = serializers.SerializerMethodField()
    master_config = serializers.SerializerMethodField()
    merged_config = serializers.SerializerMethodField()

    class Meta:
        model = models.ClauseUsage
        fields = (
            "id", "clause", "clause_title", "clause_id_display", "clause_type",
            "clause_version", "agreement", "agreement_lease_id", "section",
            "active", "custom_config", "custom_body_text", "sort_order",
            "master_config", "merged_config", "version_label",
            "scope", "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "scope", "created_at", "updated_at",
            "clause_title", "clause_id_display", "clause_type",
            "agreement_lease_id", "version_label", "master_config", "merged_config",
        )

    def get_version_label(self, obj):
        if obj.clause_version:
            return obj.clause_version.version_label
        return None

    def get_master_config(self, obj):
        return obj.get_master_config()

    def get_merged_config(self, obj):
        return obj.get_merged_config()


class ClauseUsageCreateSerializer(serializers.ModelSerializer):
    """Serializer for attaching a clause to an agreement."""

    class Meta:
        model = models.ClauseUsage
        fields = (
            "clause", "clause_version", "agreement", "section",
            "active", "custom_config", "custom_body_text", "sort_order",
        )