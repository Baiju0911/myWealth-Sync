# tracker/auditSignals.py

from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
import json

# List of critical accounting & configuration models to track globally
AUDITED_MODELS = [
    "JournalEntry",
    "ClassificationRule",
    "StatementStagingLine",
    "UserStatementTemplate",
    "AccountingRule",
    "MasterFinancialCategory",
    "TaxonomyTree",
]


def serialize_instance(instance) -> dict:
    """Safely converts model instance fields to a JSON-serializable dictionary."""
    data = {}
    for field in instance._meta.concrete_fields:
        val = field.value_from_object(instance)

        # Convert non-serializable objects (UUIDs, datetimes, decimals)
        if val is None:
            data[field.name] = None
        elif hasattr(val, "isoformat"):
            data[field.name] = val.isoformat()
        else:
            data[field.name] = str(val)
    return data


@receiver(pre_save)
def capture_previous_state(sender, instance, **kwargs):
    """Stashes the old state on the instance before an update occurs."""
    if sender.__name__ in AUDITED_MODELS and instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            instance._old_state = serialize_instance(old_instance)
        except sender.DoesNotExist:
            instance._old_state = {}


@receiver(post_save)
def global_audit_save_listener(sender, instance, created, **kwargs):
    """Automatically logs CREATE and UPDATE events across audited models."""
    if sender.__name__ not in AUDITED_MODELS or sender.__name__ == "AuditLog":
        return

    from .models.models import AuditLog

    action = "CREATE" if created else "UPDATE"
    prev_state = getattr(instance, "_old_state", {}) if not created else {}
    new_state = serialize_instance(instance)

    # Extract account_id & row_identifier dynamically if present on the model instance
    account_id = getattr(instance, "account_id", None)
    row_identifier = getattr(instance, "row_identifier", None)

    # Check if a specific rule_code is stored in evaluation_matrix_snapshot or rule object
    applied_rule_code = None
    if hasattr(instance, "rule_code"):
        applied_rule_code = instance.rule_code
    elif hasattr(instance, "evaluation_matrix_snapshot") and isinstance(
        instance.evaluation_matrix_snapshot, dict
    ):
        applied_rule_code = instance.evaluation_matrix_snapshot.get(
            "applied_rule_code"
        ) or instance.evaluation_matrix_snapshot.get("applied_rule")

    AuditLog.objects.create(
        action_type=f"{sender.__name__.upper()}_{action}",
        target_table=sender._meta.db_table,
        account_id=account_id,
        row_identifier=row_identifier,
        previous_state=prev_state,
        new_state=new_state,
        applied_rule_code=applied_rule_code,
        notes=f"Auto-captured {action} event on {sender.__name__} (PK: {instance.pk})",
    )


@receiver(post_delete)
def global_audit_delete_listener(sender, instance, **kwargs):
    """Automatically logs DELETE events across audited models."""
    if sender.__name__ not in AUDITED_MODELS or sender.__name__ == "AuditLog":
        return

    from .models.models import AuditLog

    AuditLog.objects.create(
        action_type=f"{sender.__name__.upper()}_DELETE",
        target_table=sender._meta.db_table,
        account_id=getattr(instance, "account_id", None),
        row_identifier=getattr(instance, "row_identifier", None),
        previous_state=serialize_instance(instance),
        new_state={},
        notes=f"Auto-captured DELETE event on {sender.__name__} (PK: {instance.pk})",
    )
