
SET FOREIGN_KEY_CHECKS = 0;
SET SQL_SAFE_UPDATES = 0;

TRUNCATE TABLE ledger_journal_entry;
TRUNCATE TABLE ledger_wip_evaluation_matrix;

UPDATE ledger_statementstagingline 
SET routing_status = 'PENDING';

SET SQL_SAFE_UPDATES = 1;
SET FOREIGN_KEY_CHECKS = 1;



SHOW TABLE STATUS LIKE 'ledger_journal_entry';

SET FOREIGN_KEY_CHECKS = 0;
SET SQL_SAFE_UPDATES = 0;

-- 1. Wipe taxonomy & classification rules
TRUNCATE TABLE ledger_taxonomy_tree;
TRUNCATE TABLE ledger_classification_rule;

-- 2. Wipe accounting double-entry books & WIP evaluation sandbox
TRUNCATE TABLE ledger_journal_entry;
TRUNCATE TABLE ledger_wip_evaluation_matrix;

-- 3. Reset raw statement staging rows back to PENDING
UPDATE ledger_statementstagingline 
SET routing_status = 'PENDING',
    suggested_contra_account_id = NULL;

SET SQL_SAFE_UPDATES = 1;
SET FOREIGN_KEY_CHECKS = 1;

SET FOREIGN_KEY_CHECKS = 0;
SET SQL_SAFE_UPDATES = 0;

-- 1. Wipe taxonomy & classification rules
TRUNCATE TABLE ledger_taxonomy_tree;
TRUNCATE TABLE ledger_classification_rule;

-- 2. Wipe accounting double-entry books & WIP evaluation sandbox
TRUNCATE TABLE ledger_journal_entry;
TRUNCATE TABLE ledger_wip_evaluation_matrix;

-- 3. Reset raw statement staging rows back to PENDING
Truncate TABLE ledger_statementstagingline;
Truncate TABLE tracker_statement_ingest_registry;

SET SQL_SAFE_UPDATES = 1;
SET FOREIGN_KEY_CHECKS = 1;