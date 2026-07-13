
SET FOREIGN_KEY_CHECKS = 0;
SET SQL_SAFE_UPDATES = 0;

-- 1. Wipe out your historical accounting books completely
TRUNCATE TABLE ledger_journal_entry;

-- 2. Clear out your rules evaluation matrix workspace sandbox
TRUNCATE TABLE ledger_wip_evaluation_matrix;

-- 3. If you have an active split component registry, wipe it too
-- TRUNCATE TABLE ledger_wip_split_component;

-- 4. Realign all raw staging statement rows back to PENDING status
UPDATE ledger_statementstagingline 
SET routing_status = 'PENDING';

SET SQL_SAFE_UPDATES = 1;
SET FOREIGN_KEY_CHECKS = 1;