import decimal
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

# 🛢️ Grab your live MySQL model schemas including our new metadata layers
from .models import (
    Account,
    TransactionHeader,
    JournalEntry,
    BankCredential,
    Bank,
    MasterFinancialCategory,
    AccountingRule,
    JournalEntryMapping,
)


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = [
            "id",
            "bank_id",
            "name",
            "account_type",
            "account_number",
            "ifsc_code",
            "branch_name",
            "address",
        ]
        read_only_fields = ["id", "created_at"]


class JournalEntrySerializer(serializers.ModelSerializer):
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(), source="account"
    )

    # 🎯 NEW CATEGORY EXTENSION FIELDS: Optional payloads passed up from checkout views
    assigned_category_id = serializers.PrimaryKeyRelatedField(
        queryset=MasterFinancialCategory.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )
    applied_rule_id = serializers.PrimaryKeyRelatedField(
        queryset=AccountingRule.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )

    class Meta:
        model = JournalEntry
        fields = ["account_id", "amount", "assigned_category_id", "applied_rule_id"]


class TransactionHeaderSerializer(serializers.ModelSerializer):
    lines = JournalEntrySerializer(many=True, source="entries")

    class Meta:
        model = TransactionHeader
        fields = [
            "id",
            "narration",
            "date",
            "source",
            "upi_rrn",
            "merchant_vpa",
            "scanned_by",
            "lines",
        ]
        read_only_fields = ["id"]

    def validate_lines(self, value):
        if len(value) < 2:
            raise serializers.ValidationError(
                "A high-precision double-entry record requires at least 2 ledger entry line splits."
            )

        total = sum(decimal.Decimal(str(line.get("amount", "0.00"))) for line in value)
        if total != 0:
            raise serializers.ValidationError(
                f"Ledger entries must balance to zero. Current discrepancy: {total}"
            )
        return value

    def create(self, validated_data):
        entries_data = validated_data.pop("entries")
        user = self.context["request"].user
        validated_data["user"] = user

        # 🚀 ATOMIC TRANSACTIONS CORE
        with transaction.atomic():
            header = TransactionHeader.objects.create(**validated_data)

            for entry_data in entries_data:
                # Extract our optional metadata parameters from the row dictionary
                assigned_category = entry_data.pop("assigned_category_id", None)
                applied_rule = entry_data.pop("applied_rule_id", None)

                # 1. Create the core transaction line item
                journal_entry = JournalEntry.objects.create(
                    transaction=header, **entry_data
                )

                # 2. If a category mapping is supplied, register it instantly!
                if assigned_category:
                    JournalEntryMapping.objects.create(
                        journal_entry=journal_entry,
                        assigned_category=assigned_category,
                        applied_rule=applied_rule,
                    )

        return header


class BankCredentialSerializer(serializers.ModelSerializer):
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(), source="account"
    )

    class Meta:
        model = BankCredential
        fields = ["id", "account_id", "password_vault", "updated_at"]
        read_only_fields = ["id", "updated_at"]

    def validate_password_vault(self, value):
        if value is None:
            return []
        if isinstance(value, str):
            cleaned_str = value.strip().lstrip("[").rstrip("]")
            return [
                p.strip().replace('"', "").replace("'", "")
                for p in cleaned_str.split(",")
                if p.strip()
            ]
        if isinstance(value, list):
            return [str(pwd).strip() for pwd in value if str(pwd).strip()]
        return []


class MasterFinancialCategoryAdminSerializer(serializers.ModelSerializer):
    """
    🛠️ Administrative CRUD Serializer for taxonomy parameters
    """

    class Meta:
        model = MasterFinancialCategory
        fields = [
            "id",
            "sno",
            "category_type",
            "act_category",
            "act_subcategory",
            "categories_items",
            "dashboard_cat",
            "keys",
            "bank_types",
            "self_account",
            "transfer_value",
            "remarks",
            "concatenate",
            "monthly_expense",
        ]
        read_only_fields = ["id"]


class AccountingRuleAdminSerializer(serializers.ModelSerializer):
    """
    🛠️ Administrative CRUD Serializer for compressed golden rules
    """

    class Meta:
        model = AccountingRule
        fields = [
            "id",
            "rule_code",
            "rule_title",
            "entry_type",
            "rule_priority",
            "description_tags",
            "examples",
            "rule_metadata",
            "is_active",
            "apply_to_ai",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# import decimal
# from datetime import timedelta
# from django.utils import timezone
# from django.db import (
#     transaction,
# )  # 🛡️ FIXED: Added missing database atomic transaction helper
# from rest_framework import serializers
# from rest_framework.exceptions import ValidationError

# # 🛢️ Grab your precise live MySQL model schemas
# from .models import Account, TransactionHeader, JournalEntry, BankCredential, Bank


# class AccountSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Account
#         fields = [
#             "id",
#             "bank_id",
#             "name",
#             "account_type",
#             "account_number",
#             "ifsc_code",
#             "branch_name",
#             "address",
#         ]
#         read_only_fields = ["id", "created_at"]


# class JournalEntrySerializer(serializers.ModelSerializer):
#     account_id = serializers.PrimaryKeyRelatedField(
#         queryset=Account.objects.all(), source="account"
#     )

#     class Meta:
#         model = JournalEntry
#         fields = ["account_id", "amount"]


# class TransactionHeaderSerializer(serializers.ModelSerializer):
#     lines = JournalEntrySerializer(many=True, source="entries")

#     class Meta:
#         model = TransactionHeader
#         fields = [
#             "id",
#             "narration",
#             "date",
#             "source",
#             "upi_rrn",
#             "merchant_vpa",
#             "scanned_by",
#             "lines",
#         ]
#         read_only_fields = ["id"]

#     def validate_lines(self, value):
#         if len(value) < 2:
#             raise serializers.ValidationError(
#                 "A high-precision double-entry record requires at least 2 ledger entry line splits."
#             )

#         # Enforce exact string conversions to prevent floating-point representation drift
#         total = sum(decimal.Decimal(str(line.get("amount", "0.00"))) for line in value)
#         if total != 0:
#             raise serializers.ValidationError(
#                 f"Ledger entries must balance to zero. Current discrepancy: {total}"
#             )
#         return value

#     def create(self, validated_data):
#         entries_data = validated_data.pop("entries")
#         user = self.context["request"].user
#         validated_data["user"] = user

#         # 🚀 FIXED: 'transaction' block will now execute perfectly inside MySQL
#         with transaction.atomic():
#             header = TransactionHeader.objects.create(**validated_data)
#             for entry_data in entries_data:
#                 JournalEntry.objects.create(transaction=header, **entry_data)
#         return header


# class BankCredentialSerializer(serializers.ModelSerializer):
#     account_id = serializers.PrimaryKeyRelatedField(
#         queryset=Account.objects.all(), source="account"
#     )

#     class Meta:
#         model = BankCredential
#         fields = [
#             "id",
#             "account_id",
#             "password_vault",
#             "updated_at",
#         ]
#         read_only_fields = ["id", "updated_at"]

#     def validate_password_vault(self, value):
#         """
#         🛡️ ENHANCED PARSING FORCE-MULTIPLIER:
#         Catches variations from frontend engines and forces them into a clean python list.
#         """
#         if value is None:
#             return []
#         # If the frontend sent a plain string instead of an array, wrap it immediately!
#         if isinstance(value, str):
#             cleaned_str = value.strip()
#             # If it's a string looking like an array string '["pass"]', strip brackets
#             cleaned_str = cleaned_str.lstrip("[").rstrip("]")
#             return [
#                 p.strip().replace('"', "").replace("'", "")
#                 for p in cleaned_str.split(",")
#                 if p.strip()
#             ]
#         if isinstance(value, list):
#             return [str(pwd).strip() for pwd in value if str(pwd).strip()]
#         return []
