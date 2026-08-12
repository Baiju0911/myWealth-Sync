from rest_framework import serializers
from ..models.models import JournalEntry, ClassificationStatus


class StructuredRemarksSerializer(serializers.Serializer):
    """
    Nested serializer for structured JSON remarks.
    """

    directional_prefix = serializers.CharField(required=False, allow_null=True)
    target_account_name = serializers.CharField(required=False, allow_null=True)
    display_text = serializers.CharField(required=False, allow_null=True)
    payee = serializers.CharField(required=False, allow_null=True)
    upi_ref = serializers.CharField(required=False, allow_null=True)
    user_note = serializers.CharField(required=False, allow_null=True)
    rule_code = serializers.CharField(required=False, allow_null=True)
    source = serializers.CharField(required=False, allow_null=True)


class ClassificationJournalEntrySerializer(serializers.ModelSerializer):
    """
    Serializer specifically tailored for the Classification/Reclassification flow.
    """

    # 📝 Handles native JSONField deserialization cleanly
    remarks = StructuredRemarksSerializer(read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            "id",
            "account_id",
            "transaction_date",
            "row_identifier",
            "debit",
            "credit",
            "is_reclassified",
            "classification_status",
            "remarks",
            "evaluation_matrix_snapshot",
            "created_at",
        ]


class ReclassifyRequestSerializer(serializers.Serializer):
    """
    Input payload serializer for reclassifying a row from the frontend modal.
    """

    row_identifier = serializers.CharField(required=True, max_length=64)
    new_category = serializers.CharField(required=True, max_length=100)
    new_subcategory = serializers.CharField(required=True, max_length=100)
    rule_code = serializers.CharField(default="MANUAL", max_length=50)
    taxonomy_node_account_id = serializers.IntegerField(default=99)
    user_note = serializers.CharField(required=False, allow_blank=True, allow_null=True)
