from rest_framework import serializers
from ..models.emailModels import RawEmailPayload


class RawEmailPayloadSerializer(serializers.ModelSerializer):
    taxonomy_payload = serializers.JSONField(required=False, allow_null=True)

    class Meta:
        model = RawEmailPayload
        fields = "__all__"
        # 🎯 FIX: Remove `read_only_fields = fields` so taxonomy_payload can be updated via PATCH/POST
        read_only_fields = ["id", "created_at", "processed_at"]


class IngestRequestSerializer(serializers.Serializer):
    encrypted_payload = serializers.CharField(
        required=False, allow_blank=True, default="BYPASS"
    )
    payload_hash = serializers.CharField(required=False, allow_blank=True)
    source = serializers.CharField(required=False, allow_blank=True, default="IOS_SMS")
