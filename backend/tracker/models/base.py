from __future__ import annotations
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class BulkAuditQuerySet(models.QuerySet):
    """
    Custom QuerySet that intercepts bulk operations (bulk_create, bulk_update)
    and automatically emits AuditLog records for high-performance ingestion engines.
    """

    def bulk_create(self, objs, *args, **kwargs):
        created_objs = super().bulk_create(objs, *args, **kwargs)
        from .base import AuditLog

        audit_logs = []
        for obj in created_objs:
            account_id = getattr(obj, "account_id", None)
            row_identifier = getattr(obj, "row_identifier", None)
            applied_rule = None

            if hasattr(obj, "evaluation_matrix_snapshot") and isinstance(
                obj.evaluation_matrix_snapshot, dict
            ):
                applied_rule = obj.evaluation_matrix_snapshot.get(
                    "applied_rule_code"
                ) or obj.evaluation_matrix_snapshot.get("applied_rule")

            audit_logs.append(
                AuditLog(
                    action_type=f"{obj.__class__.__name__.upper()}_BULK_CREATE",
                    target_table=obj._meta.db_table,
                    account_id=account_id,
                    row_identifier=row_identifier,
                    previous_state={},
                    new_state={
                        f.name: str(getattr(obj, f.name))
                        for f in obj._meta.concrete_fields
                        if getattr(obj, f.name) is not None
                    },
                    applied_rule_code=applied_rule,
                    notes=f"Bulk created via engine pipeline (PK: {obj.pk})",
                )
            )

        if audit_logs:
            AuditLog.objects.bulk_create(audit_logs, batch_size=1000)

        return created_objs

    def bulk_update(self, objs, fields, *args, **kwargs):
        result = super().bulk_update(objs, fields, *args, **kwargs)
        from .base import AuditLog

        audit_logs = []
        for obj in objs:
            account_id = getattr(obj, "account_id", None)
            row_identifier = getattr(obj, "row_identifier", None)

            audit_logs.append(
                AuditLog(
                    action_type=f"{obj.__class__.__name__.upper()}_BULK_UPDATE",
                    target_table=obj._meta.db_table,
                    account_id=account_id,
                    row_identifier=row_identifier,
                    previous_state={},
                    new_state={
                        f: str(getattr(obj, f)) for f in fields if hasattr(obj, f)
                    },
                    notes=f"Bulk updated fields {fields} (PK: {obj.pk})",
                )
            )

        if audit_logs:
            AuditLog.objects.bulk_create(audit_logs, batch_size=1000)

        return result


class BulkAuditManager(models.Manager):
    def get_queryset(self):
        return BulkAuditQuerySet(self.model, using=self._db)


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_actions",
    )
    action_type = models.CharField(max_length=50, db_index=True)
    target_table = models.CharField(max_length=100, db_index=True)
    account_id = models.IntegerField(null=True, blank=True, db_index=True)
    row_identifier = models.CharField(
        max_length=64, null=True, blank=True, db_index=True
    )

    previous_state = models.JSONField(default=dict, blank=True)
    new_state = models.JSONField(default=dict, blank=True)

    applied_rule_code = models.CharField(max_length=50, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "ledger_audit_log"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["account_id", "action_type"]),
            models.Index(fields=["target_table", "row_identifier"]),
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self):
        user_str = self.user.email if self.user else "SYSTEM"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.action_type} by {user_str} on {self.target_table}"
