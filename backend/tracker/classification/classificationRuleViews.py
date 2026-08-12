import hashlib
import logging
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..models.models import ClassificationRule, TaxonomyTree

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# 1. LIST & FILTER RULES
# ------------------------------------------------------------------------------
@api_view(["GET"])
def list_classification_rules(request):
    """Lists all classification rules with optional filtering by status or subcategory."""
    is_active = request.query_params.get("is_active")
    search_query = request.query_params.get("query", "").strip()

    qs = ClassificationRule.objects.all().order_by("-priority", "target_subcategory")

    if is_active is not None:
        qs = qs.filter(is_active=is_active.lower() == "true")

    if search_query:
        qs = qs.filter(
            name__icontains=search_query
        ) | ClassificationRule.objects.filter(rule_code__icontains=search_query)

    rules_data = []
    for r in qs:
        rules_data.append(
            {
                "id": r.id,
                "rule_code": r.rule_code,
                "name": r.name,
                "rule_type": r.rule_type,
                "target_category": r.target_category,
                "target_subcategory": r.target_subcategory,
                "patterns": (
                    r.get_patterns() if hasattr(r, "get_patterns") else r.patterns
                ),
                "priority": r.priority,
                "is_active": r.is_active,
                "match_count": r.match_count or 0,
                "created_from_manual_override": r.created_from_manual_override,
                "updated_at": r.updated_at,
            }
        )

    return Response(
        {"status": "success", "count": len(rules_data), "rules": rules_data}
    )


# ------------------------------------------------------------------------------
# 2. CREATE RULE
# ------------------------------------------------------------------------------
@api_view(["POST"])
def create_classification_rule(request):
    """Creates a new Classification Rule manually from the UI."""
    data = request.data
    name = data.get("name", "").strip()
    category = data.get("target_category", "").strip()
    subcategory = data.get("target_subcategory", "").strip()
    entry_type = (
        "Credit"
        if str(data.get("rule_type", "")).strip().lower() == "credit"
        else "Debit"
    )
    patterns = data.get("patterns", [])
    priority = int(data.get("priority", 1))

    if not category or not subcategory or not patterns:
        return Response(
            {"error": "Category, subcategory, and at least one pattern are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Clean patterns
    clean_patterns = [
        str(p).strip().upper().lstrip("#") for p in patterns if str(p).strip()
    ]
    if not clean_patterns:
        return Response(
            {"error": "No valid non-empty patterns provided."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Generate rule_code
    vector_prefix = "DE" if entry_type == "Debit" else "CR"
    hash_input = f"{subcategory}_{clean_patterns[0]}_{entry_type}".upper()
    short_code = hashlib.md5(hash_input.encode()).hexdigest()[:6].upper()
    rule_code = f"CR_{vector_prefix}_{short_code}"

    taxonomy_node = TaxonomyTree.objects.filter(
        category__iexact=category, subcategory__iexact=subcategory
    ).first()

    rule = ClassificationRule.objects.create(
        name=name or f"Rule ({entry_type}): {subcategory}",
        rule_code=rule_code,
        rule_type=entry_type,
        target_category=category,
        target_subcategory=subcategory,
        patterns=clean_patterns,
        priority=priority,
        is_active=True,
        created_from_manual_override=True,
        match_count=0,
        taxonomy=taxonomy_node,
    )

    print(
        f"✅ [CRUD CREATE] Created new rule {rule.rule_code} with patterns: {clean_patterns}"
    )

    return Response(
        {
            "status": "success",
            "message": f"Rule {rule_code} created successfully.",
            "rule_code": rule_code,
        },
        status=status.HTTP_201_CREATED,
    )


# ------------------------------------------------------------------------------
# 3. UPDATE RULE
# ------------------------------------------------------------------------------
@api_view(["PUT", "PATCH"])
def update_classification_rule(request, rule_code):
    """Updates target taxonomy, priority, name, or pattern list for a rule."""
    try:
        rule = ClassificationRule.objects.get(rule_code=rule_code)
    except ClassificationRule.DoesNotExist:
        return Response(
            {"error": f"Rule {rule_code} not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    data = request.data
    if "name" in data:
        rule.name = str(data["name"]).strip()
    if "target_category" in data:
        rule.target_category = str(data["target_category"]).strip()
    if "target_subcategory" in data:
        rule.target_subcategory = str(data["target_subcategory"]).strip()
    if "priority" in data:
        rule.priority = int(data["priority"])
    if "is_active" in data:
        rule.is_active = bool(data["is_active"])
    if "patterns" in data and isinstance(data["patterns"], list):
        clean_pats = [
            str(p).strip().upper().lstrip("#")
            for p in data["patterns"]
            if str(p).strip()
        ]
        rule.patterns = clean_pats

    # Re-link taxonomy node if category/subcategory changed
    taxonomy_node = TaxonomyTree.objects.filter(
        category__iexact=rule.target_category,
        subcategory__iexact=rule.target_subcategory,
    ).first()
    rule.taxonomy = taxonomy_node

    rule.save()
    print(f"✅ [CRUD UPDATE] Updated rule {rule_code}")

    return Response(
        {"status": "success", "message": f"Rule {rule_code} updated successfully."}
    )


# ------------------------------------------------------------------------------
# 4. TOGGLE ACTIVE / INACTIVE
# ------------------------------------------------------------------------------
@api_view(["POST"])
def toggle_rule_active_status(request, rule_code):
    """Quick toggle to activate or deactivate a rule."""
    try:
        rule = ClassificationRule.objects.get(rule_code=rule_code)
        rule.is_active = not rule.is_active
        rule.save(update_fields=["is_active", "updated_at"])

        status_str = "ACTIVE" if rule.is_active else "INACTIVE"
        print(f"⚙️ [CRUD TOGGLE] Rule {rule_code} is now {status_str}")

        return Response(
            {
                "status": "success",
                "is_active": rule.is_active,
                "message": f"Rule {rule_code} marked as {status_str}.",
            }
        )
    except ClassificationRule.DoesNotExist:
        return Response(
            {"error": f"Rule {rule_code} not found."},
            status=status.HTTP_404_NOT_FOUND,
        )


# ------------------------------------------------------------------------------
# 5. DELETE RULE
# ------------------------------------------------------------------------------
@api_view(["DELETE"])
def delete_classification_rule(request, rule_code):
    """Deletes a rule completely or soft-deletes it by setting is_active=False."""
    try:
        rule = ClassificationRule.objects.get(rule_code=rule_code)
        rule.delete()
        print(f"🗑️ [CRUD DELETE] Deleted rule {rule_code}")

        return Response(
            {"status": "success", "message": f"Rule {rule_code} permanently deleted."}
        )
    except ClassificationRule.DoesNotExist:
        return Response(
            {"error": f"Rule {rule_code} not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
