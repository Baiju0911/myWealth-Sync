
SET FOREIGN_KEY_CHECKS = 0;
SET SQL_SAFE_UPDATES = 0;

TRUNCATE TABLE ledger_journal_entry;
TRUNCATE TABLE ledger_wip_evaluation_matrix;

UPDATE ledger_statementstagingline 
SET routing_status = 'PENDING';

SET SQL_SAFE_UPDATES = 1;
SET FOREIGN_KEY_CHECKS = 1;



SHOW TABLE STATUS LIKE 'ledger_journal_entry';