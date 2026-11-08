from __future__ import annotations

# Base & Audit
from .base import BulkAuditQuerySet, BulkAuditManager, AuditLog

# RBAC
from .auth_models import Permission, Role, CustomUserManager, User

# Banking Entities
from .banking_models import (
    Bank,
    Account,
    BankCredential,
    BankLayoutSchema,
    UserStatementTemplate,
)

# Staging & Ingest
from .staging_models import StatementIngestRegistry, StatementStagingLine

# Core Double Entry & Classification
from .accounting_models import (
    TransactionHeader,
    TaxonomyTree,
    AccountingRule,
    MasterFinancialCategory,
    ClassificationStatus,
    ClassificationRule,
    JournalEntry,
    JournalEntryMapping,
    WIPEvaluationMatrix,
    DirectionalVectorOverride,
)

# Tagging & Group Hierarchy
from .tagging_models import (
    WorkbenchGroupHierarchy,
    MasterNarrationTagRule,
)

# Optional existing submodules if present
try:
    from .subledger import *
except ImportError:
    pass

try:
    from .emailModels import *
except ImportError:
    pass
