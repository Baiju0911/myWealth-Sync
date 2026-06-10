# S:\_BaijSoft\myWealth-Sync\backend\tracker\views.py
import csv
import datetime
import decimal
import io
import re
import hashlib

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from pypdf import PdfReader

# 🔌 Django REST Framework Tools
from rest_framework import serializers, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from .parsers.utils import MatchWrapper, generate_row_fingerprint


from .models import (
    Account,
    Bank,
    BankCredential,
    BankLayoutSchema,
    JournalEntry,
    Permission,
    Role,
    TransactionHeader,
    StatementStagingLine,
    StatementIngestRegistry,
)
from .serializers import AccountSerializer, BankCredentialSerializer
from .parsers.SBI_format import process_SBI_pdf_statement
from .parsers.SIB_format import process_SIB_pdf_statement
from .parsers.FED_format import process_FED_pdf_statement
from .parsers.unified_csv_format import process_unified_csv_statement

User = get_user_model()

# ==========================================
# 1. SYSTEM STRUCTURAL METADATA ENDPOINTS
# ==========================================


class SystemConfigView(APIView):
    """
    Exposes global system constants to the frontend app.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        account_types = [
            {"key": item[0], "label": item[1]} for item in settings.ACCOUNT_TYPES
        ]
        transaction_statuses = [
            {"key": item[0], "label": item[1]}
            for item in settings.TRANSACTION_STATUS_CHOICES
        ]
        return Response(
            {
                "account_types": account_types,
                "transaction_statuses": transaction_statuses,
                "currency": "INR",
                "precision_decimal_places": 2,
            }
        )


# ==========================================
# 2. ACCOUNT CONTROL LAYER (CRUD & SUFFIX INTEGRATION)
# ==========================================


class AccountListCreateView(APIView):
    """
    Adapter Endpoint to manage structural multi-account assets and configurations.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        """
        📥 GET: Fetch full array payloads for active financial nodes
        """
        accounts = Account.objects.all()
        # Enforce detailed representation straight from your pre-configured serializer block
        serializer = AccountSerializer(accounts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """
        🚀 POST: Provision a new Master Ledger Account Node
        """
        bank_id = request.data.get("bank_id")
        name = request.data.get("name")
        account_type = request.data.get("account_type", "ASSET")
        ifsc_code = request.data.get("ifsc_code", "").strip().upper()
        branch_name = request.data.get("branch_name", "")
        address = request.data.get("address", "")

        # 🔗 COMPATIBILITY LINK: Extracts 'account_number' but checks old 'account_suffix' as a fallback
        account_number = request.data.get("account_number") or request.data.get(
            "account_suffix", ""
        )

        # 🧩 SAFE CONTEXT GENERATION: Execute a get_or_create query directly over matching attributes
        account, created = Account.objects.get_or_create(
            bank_id=bank_id,
            name=name,
            defaults={
                "account_type": account_type,
                "account_number": account_number,
                "ifsc_code": ifsc_code,
                "branch_name": branch_name,
                "address": address,
            },
        )

        serializer = AccountSerializer(account)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class AccountDetailView(APIView):
    """
    ✏️ ADAPTER CORE: Manages isolated updates to individual records, squashing 405 errors.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def put(self, request, pk=None):
        """
        💾 PUT: Modify and lock detailed metadata configuration rows (IFSC, Branch, Suffix)
        """
        account = get_object_or_404(Account, id=pk)

        # Hydrate text parameters from active inputs or retain fallback values
        account.name = request.data.get("name", account.name)
        account.account_type = request.data.get("account_type", account.account_type)
        account.ifsc_code = (
            request.data.get("ifsc_code", account.ifsc_code).strip().upper()
        )
        account.branch_name = request.data.get("branch_name", account.branch_name)
        account.address = request.data.get("address", account.address)

        # Check both modern and legacy variables for the 4-digit token
        account.account_number = (
            request.data.get("account_number")
            or request.data.get("account_suffix")
            or account.account_number
        )

        account.save()

        serializer = AccountSerializer(account)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk=None):
        """
        🗑️ DELETE: Purge account records cleanly from the system registry
        """
        account = get_object_or_404(Account, id=pk)
        account.delete()
        return Response(
            {"message": "Account node removed cleanly"}, status=status.HTTP_200_OK
        )


# ==========================================
# 3. DOUBLE-ENTRY TRANSACTION QUEUE HANDLING
# ==========================================


class TransactionListCreateView(APIView):
    """
    Fallback historical review view list.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        mock_user = User.objects.first() or User.objects.create_user(
            email="testowner@wealth.com", password="TestPassword123"
        )
        headers = TransactionHeader.objects.filter(user=mock_user).prefetch_related(
            "entries__account"
        )

        serialized_list = []
        for h in headers:
            lines = [
                {"account_name": e.account.name, "amount": float(e.amount)}
                for e in h.entries.all()
            ]
            serialized_list.append(
                {
                    "id": str(h.id),
                    "date": h.date,
                    "description": h.narration,
                    "source": h.source,
                    "upi_rrn": h.upi_rrn,
                    "lines": lines,
                }
            )
        return Response(serialized_list, status=status.HTTP_200_OK)


class BulkTransactionSyncView(APIView):
    """
    Smart mobile payload translator adapter to double-entry rows.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        owner_role, _ = Role.objects.get_or_create(name="PLATFORM_OWNER")
        mock_user = User.objects.first()
        if not mock_user:
            mock_user = User.objects.create_user(
                email="testowner@wealth.com",
                password="TestPassword123",
                role=owner_role,
            )
        elif not mock_user.role:
            mock_user.role = owner_role
            mock_user.save()

        perm, _ = Permission.objects.get_or_create(codename="CAN_UPLOAD_STATEMENT")
        owner_role.permissions.add(perm)

        payload = request.data
        transactions_to_process = payload if isinstance(payload, list) else [payload]

        try:
            with transaction.atomic():
                for item in transactions_to_process:
                    description = item.get("description", "QR Scan Transfer Inflow")
                    timestamp_str = item.get(
                        "timestamp", datetime.datetime.now().isoformat()
                    )
                    parsed_date = datetime.datetime.fromisoformat(
                        timestamp_str.replace("Z", "")
                    ).date()

                    raw_narration = ""
                    header = TransactionHeader.objects.create(
                        user=mock_user,
                        date=parsed_date,
                        narration=raw_narration,
                        source="QR_SCAN_MOBILE",
                        upi_rrn=item.get("upi_rrn", None),
                        merchant_vpa=item.get("merchant_vpa", None),
                        scanned_by=item.get("scanned_by", "Handheld App Mobile Client"),
                    )

                    incoming_lines = item.get("lines", [])
                    if incoming_lines:
                        for line in incoming_lines:
                            account_name = line.get(
                                "account_name", "Expenses:Unclassified"
                            )
                            debit = decimal.Decimal(str(line.get("debit_amount", 0.00)))
                            credit = decimal.Decimal(
                                str(line.get("credit_amount", 0.00))
                            )
                            net_amount = debit - credit

                            # 🎯 GLOBAL STRUCTURAL REFIX: Removed 'user=mock_user' field filter parameter
                            account, _ = Account.objects.get_or_create(
                                name=account_name,
                                defaults={
                                    "account_type": (
                                        "EXPENSE"
                                        if "Expense" in account_name
                                        else "ASSET"
                                    )
                                },
                            )

                            JournalEntry.objects.create(
                                transaction=header, account=account, amount=net_amount
                            )
                    else:
                        fallback_amt = decimal.Decimal(str(item.get("amount", 0.00)))
                        if fallback_amt > 0:
                            # 🎯 GLOBAL STRUCTURAL REFIX: Removed 'user=mock_user' field filter parameter
                            exp_acc, _ = Account.objects.get_or_create(
                                name="Expenses:General",
                                defaults={"account_type": "EXPENSE"},
                            )
                            asset_acc, _ = Account.objects.get_or_create(
                                name="Assets:Liquid Wallet",
                                defaults={"account_type": "ASSET"},
                            )

                            JournalEntry.objects.create(
                                transaction=header, account=exp_acc, amount=fallback_amt
                            )
                            JournalEntry.objects.create(
                                transaction=header,
                                account=asset_acc,
                                amount=-fallback_amt,
                            )

            return Response(
                {
                    "status": "SUCCESS",
                    "message": "Successfully translated and synchronized offline queue items to MySQL!",
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            return Response(
                {
                    "status": "ERROR",
                    "message": f"Database processing exception: {str(e)}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


# ==========================================
# 4. CREDENTIAL VAULT VIEWS & PARSING PIPELINE
# ==========================================


class BankCredentialViewSet(viewsets.ModelViewSet):
    serializer_class = BankCredentialSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return BankCredential.objects.filter(user=self.request.user)
        test_user = User.objects.filter(email="testowner@wealth.com").first()
        return (
            BankCredential.objects.filter(user=test_user)
            if test_user
            else BankCredential.objects.none()
        )

    def _get_target_user(self):
        """Helper to safely determine user ownership across auth and local testing contexts"""
        if self.request.user.is_authenticated:
            return self.request.user
        return User.objects.filter(email="testowner@wealth.com").first()

    def create(self, request, *args, **kwargs):
        # 📥 Copy the inbound request dictionary data matrix defensively
        payload_data = request.data.copy()

        # 🛡️ ALIGN DATA PROPERTY KEYS FOR THE SERIALIZER
        if "account_id" in payload_data and "account" not in payload_data:
            payload_data["account"] = payload_data["account_id"]

        # 🎯 THE JSON ARRAY FIX: Reconstruct raw text into a list block array structure
        raw_pass = payload_data.get("statement_password") or payload_data.get(
            "password_vault"
        )

        if raw_pass:
            if isinstance(raw_pass, str) and raw_pass.strip():
                payload_data["password_vault"] = [raw_pass.strip()]
            elif isinstance(raw_pass, list):
                payload_data["password_vault"] = raw_pass

        # print(f"📥 [NORMALIZED VAULT INPUT PAYLOAD]: {payload_data}")  # 🔍 DEBUG ENGINE

        serializer = self.get_serializer(data=payload_data)
        serializer.is_valid(raise_exception=True)

        target_account = serializer.validated_data.get("account")
        incoming_passwords = serializer.validated_data.get("password_vault", [])

        print(
            f"📦 [PARSED VALIDATED DATA ARRAY]: Account: {target_account.id if target_account else 'None'}, Vault Array: {incoming_passwords}"
        )

        target_user = self._get_target_user()
        existing_credential = BankCredential.objects.filter(
            account=target_account
        ).first()

        # 🔄 BRANCH A: THE EDIT ROUTE (Existing Profile Found)
        if existing_credential:
            print(
                f"🔄 [VAULT MATCH FOUND] Row ID: {existing_credential.id}. Executing merge loop..."
            )
            current_vault = existing_credential.password_vault
            if not isinstance(current_vault, list):
                current_vault = []

            for raw_pwd in reversed(incoming_passwords):
                pwd_string = str(raw_pwd).strip()
                if not pwd_string or pwd_string in current_vault:
                    if pwd_string in current_vault:
                        current_vault.remove(pwd_string)
                current_vault.insert(0, pwd_string)

            existing_credential.password_vault = current_vault[:5]
            if target_user:
                existing_credential.user = target_user

            existing_credential.save()

            # Use serializer to return clean output format
            return Response(
                self.get_serializer(existing_credential).data, status=status.HTTP_200_OK
            )

        # 🚀 BRANCH B: THE NEW ROUTE FIXED!
        # Instead of calling super().create(), we save the validated serializer data explicitly
        # and pass the password_vault list directly into the database commit layer.
        serializer.save(user=target_user, password_vault=incoming_passwords)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        """
        🛡️ THE INTEGRITY SHIELD:
        Forces both user assignment AND the normalized password vault array
        directly into the database insert statement, preventing serializer drops!
        """
        target_user = self._get_target_user()

        # 🎯 SNATCH the validated vault array directly from the serializer context
        validated_vault = serializer.validated_data.get("password_vault", [])

        # If the serializer stripped it out, fallback to pulling it right from our request data modification
        if not validated_vault:
            raw_val = serializer.initial_data.get("password_vault")
            if isinstance(raw_val, list):
                validated_vault = raw_val

        # Force save both variables straight to the database layer
        serializer.save(user=target_user, password_vault=validated_vault)


class StatementIngestRouterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        account_id = request.data.get("account_id")
        uploaded_file = request.FILES.get("statement_file")

        if not account_id or not uploaded_file:
            return Response(
                {"error": "Target Account and Statement File are both mandatory."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 🕵️ STRATEGY 1: Extract the file extension dynamically from the file payload name
        filename = uploaded_file.name.lower()
        if filename.endswith(".pdf"):
            file_format = "PDF"
        elif filename.endswith(".csv"):
            file_format = "CSV"
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            file_format = "EXCEL"
        else:
            return Response(
                {"error": "Unsupported file format extension uploaded."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            account_profile = Account.objects.select_related("bank").get(id=account_id)
            bank_code = account_profile.bank.code.upper()
        except Account.DoesNotExist:
            return Response(
                {"error": "Invalid Account Profile ID."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 🔀 THE NESTED MULTI-FORMAT STRATEGY MATRIX MAP
        # Keeps database codes pure while splitting engines on file extension routes cleanly
        PARSER_STRATEGY_MAP = {
            "SBI": {
                "PDF": process_SBI_pdf_statement,
                "CSV": process_unified_csv_statement,
            },
            "FED": {
                "PDF": process_FED_pdf_statement,
                "CSV": process_unified_csv_statement,
            },
            "SIB": {
                "PDF": process_SIB_pdf_statement,
                "CSV": process_unified_csv_statement,
            },
        }

        # 🛑 STEP 1: Verify bank support
        if bank_code not in PARSER_STRATEGY_MAP:
            return Response(
                {
                    "error": f"The parser format for bank {bank_code} is currently not available."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 🛑 STEP 2: Verify format availability within that bank
        bank_engines = PARSER_STRATEGY_MAP[bank_code]
        if file_format not in bank_engines:
            return Response(
                {
                    "error": f"The {file_format} file layout engine for {bank_code} is not yet implemented."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 🎯 Dynamic allocation locks in safely here
        processing_function = bank_engines[file_format]

        # 🚀 Launch the targeted processing function capsule pass
        return processing_function(request)


# ──────────────────────────────────────────────────────────────────────────
# 🛡️ THE URL DISPATCHER ANCHOR: RESTORES THE COMMIT DISCOVERABILITY WORKSPACE
# ──────────────────────────────────────────────────────────────────────────


class StatementStagingCommitView(APIView):
    """
    🔒 CORE TRANSACTION COMMIT ENGINE (LEDGER CONNECTED):
    Filters out duplicates in memory using centralized SHA-256 fingerprint strings,
    executes an atomic bulk write directly into the master ledger table, and
    saves incoming records EXACTLY as they were extracted by the parsing engine.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        account_id = request.data.get("account_id")
        preview_dataset = request.data.get("preview_dataset", [])
        meta_summary = request.data.get("meta_summary", {})

        fallback_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        file_name = (
            request.data.get("file_name")
            or request.data.get("fileName")
            or f"STATEMENT_UPLOAD_{fallback_time}.PDF"
        )

        if not account_id or not preview_dataset:
            return Response(
                {
                    "message": "Required parameters missing or empty payload array received."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        account = get_object_or_404(Account, id=account_id)
        bank = account.bank

        existing_hashes = set(
            StatementStagingLine.objects.filter(account_id=account.id).values_list(
                "row_identifier", flat=True
            )
        )

        def extract_clean_decimal(camel_key, snake_key):
            extracted_val = meta_summary.get(camel_key)
            if extracted_val is None:
                extracted_val = meta_summary.get(snake_key, 0.00)
            return decimal.Decimal(
                str(extracted_val if extracted_val is not None else 0.00)
            )

        op_bal = extract_clean_decimal("openingBalance", "opening_balance")
        cl_bal = extract_clean_decimal("closingBalance", "closing_balance")
        tot_dr = extract_clean_decimal("totalDebit", "total_debit")
        tot_cr = extract_clean_decimal("totalCredit", "total_credit")

        from_date_raw = (
            request.data.get("report_from_date")
            or request.data.get("reportFromDate")
            or meta_summary.get("report_from_date")
            or meta_summary.get("reportFromDate")
        )
        to_date_raw = (
            request.data.get("report_to_date")
            or request.data.get("reportToDate")
            or meta_summary.get("report_to_date")
            or meta_summary.get("reportToDate")
        )

        report_from_date = None
        report_to_date = None

        if from_date_raw:
            report_from_date = datetime.datetime.strptime(
                from_date_raw.split("T")[0], "%Y-%m-%d"
            ).date()
        if to_date_raw:
            report_to_date = datetime.datetime.strptime(
                to_date_raw.split("T")[0], "%Y-%m-%d"
            ).date()

        production_tx_pool = []
        duplicate_skip_count = 0

        try:
            with transaction.atomic():
                registry_entry = StatementIngestRegistry.objects.create(
                    account=account,
                    file_name=file_name,
                    file_type=meta_summary.get("fileType")
                    or meta_summary.get("file_type", "PDF"),
                    vault_decrypted=meta_summary.get("decrypted")
                    or meta_summary.get("vault_decrypted", False),
                    report_from_date=report_from_date,
                    report_to_date=report_to_date,
                    opening_balance=op_bal,
                    closing_balance=cl_bal,
                    total_debit_amount=tot_dr,
                    total_credit_amount=tot_cr,
                    total_row_count=len(preview_dataset),
                    debit_line_count=meta_summary.get("debitLineCount")
                    or meta_summary.get("debit_line_count", 0),
                    credit_line_count=meta_summary.get("creditLineCount")
                    or meta_summary.get("credit_line_count", 0),
                    skipped_duplicate_count=0,
                    source_channel="WEB_DASHBOARD",
                    ingested_at=timezone.now(),
                )

                # 🏁 STEP 2: LOOP AND BULK ASSIGN CHILD ROWS AS EXTRACTED NATIVELY
                for index, item in enumerate(preview_dataset):
                    # 🟢 TRUST INGESTION SIGNATURE: Pull the exact calculated preview hash directly
                    row_hex = (
                        item.get("id") or item.get("Hex") or item.get("row_identifier")
                    )
                    if not row_hex:
                        raise ValueError(
                            f"Missing row footprint signature identifier at index {index}"
                        )

                    raw_amt = item.get("amount", 0.00)
                    amt_val = decimal.Decimal(
                        str(raw_amt if raw_amt is not None else 0.00)
                    )

                    # 🟢 TRUST INGESTION BALANCES: Read directly from incoming payload props
                    raw_incoming_balance = (
                        item.get("balance") or item.get("running_balance") or 0.00
                    )
                    bal_val = decimal.Decimal(
                        str(raw_incoming_balance).replace(",", "").strip()
                    )

                    raw_dr = item.get("debit")
                    dr_val = (
                        decimal.Decimal(str(raw_dr))
                        if (raw_dr is not None and str(raw_dr).strip() != "")
                        else None
                    )

                    raw_cr = item.get("credit")
                    cr_val = (
                        decimal.Decimal(str(raw_cr))
                        if (raw_cr is not None and str(raw_cr).strip() != "")
                        else None
                    )

                    raw_date = item.get("date")
                    if not raw_date:
                        raise ValueError(
                            f"Missing date signature at row dataset index {index}"
                        )
                    tx_date = datetime.datetime.strptime(
                        raw_date.split("T")[0], "%Y-%m-%d"
                    ).date()

                    pure_database_narration = item.get(
                        "description", "Bank Transaction Entry"
                    )
                    cheque_reference_id = item.get("cheque_ref") or None

                    # 🛡️ GATEKEEPER DUPLICATE MATCH EVALUATION FILTER
                    if row_hex in existing_hashes or item.get("status") == "DUPLICATE":
                        duplicate_skip_count += 1
                        continue

                    staging_obj = StatementStagingLine(
                        account=account,
                        bank=bank,
                        ingest_registry=registry_entry,
                        raw_statement_date=tx_date,
                        narration=pure_database_narration,
                        amount=amt_val,
                        running_balance=bal_val,
                        debit=dr_val,
                        credit=cr_val,
                        bank_transaction_id=item.get("bank_transaction_id") or "",
                        cheque_ref_number=cheque_reference_id,
                        row_identifier=row_hex,  # 🔒 Saves the exact hash displayed on preview screen
                        routing_status="COMMITTED",
                    )
                    production_tx_pool.append(staging_obj)
                    existing_hashes.add(row_hex)

                if production_tx_pool:
                    StatementStagingLine.objects.bulk_create(production_tx_pool)

                if duplicate_skip_count > 0:
                    registry_entry.skipped_duplicate_count = duplicate_skip_count
                    registry_entry.save(update_fields=["skipped_duplicate_count"])

            return Response(
                {
                    "status": "SUCCESS",
                    "registry_id": str(registry_entry.id),
                    "message": f"Sync run complete. Saved {len(production_tx_pool)} new rows, safely skipped {duplicate_skip_count} duplicate records.",
                },
                status=status.HTTP_200_OK,
            )

        except Exception as batch_err:
            print(f"❌ RECONCILIATION DATA COMMIT CRASHED: {str(batch_err)}")
            return Response(
                {"message": f"Ledger write failure: {str(batch_err)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ==========================================
# 5. CORE MASTER INSTITUTION VIEWS
# ==========================================


class BankSerializer(serializers.ModelSerializer):
    account_count = serializers.IntegerField(read_only=True)
    credential_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Bank
        fields = ["id", "code", "display_name", "account_count", "credential_count"]


class BankViewSet(viewsets.ModelViewSet):
    """
    🏦 Master Institutional Core Engine
    """

    serializer_class = BankSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Bank.objects.annotate(
            account_count=Count("accounts", distinct=True),
            credential_count=Count("accounts__credential", distinct=True),
        ).order_by("-id")


class UpdateBankCredentialVaultView(APIView):
    """
    🔐 IDEMPOTENT VAULT KEYCHAIN UPDATER:
    Handles appending new passwords to an existing account's vault.
    If no vault exists yet for the account, it seamlessly instantiates one.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        account_id = request.data.get("account_id")
        new_password = request.data.get("new_password", "").strip()

        if not account_id or not new_password:
            return Response(
                {
                    "message": "Required parameters missing: account_id and new_password."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        account = get_object_or_404(Account, id=account_id)

        # 🎯 THE FIX: Get existing record or prepare to create a net-new one
        credential, created = BankCredential.objects.get_or_create(
            account=account,
            defaults={
                "user": request.user if request.user.is_authenticated else None,
                "password_vault": [],
            },
        )

        current_vault = (
            credential.password_vault
            if isinstance(credential.password_vault, list)
            else []
        )

        # 🛡️ THE APPENDING SHIELD LOGIC:
        if new_password in current_vault:
            # If the password is already in the list, just float it to the front (Index 0)
            current_vault.remove(new_password)

        # Push the newest password to index 0 so the parser tries it first!
        current_vault.insert(0, new_password)

        # Keep the history manageable (cap at the last 5 historical passwords)
        credential.password_vault = current_vault[:5]
        credential.save()

        return Response(
            {
                "status": "SUCCESS",
                "message": "Password successfully added to the front of the account vault keychain.",
                "vault_depth": len(credential.password_vault),
            },
            status=status.HTTP_200_OK,
        )
