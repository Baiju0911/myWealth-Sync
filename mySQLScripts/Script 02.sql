SELECT * FROM mywealth_sync_db.ledger_journal_entry;

SELECT 
    j.id AS entry_id,
    j.row_identifier,
    j.account_id,
    CASE 
        WHEN j.account_id = 99 THEN 'Node 99 (Suspense / Taxonomy Leg)'
        ELSE CONCAT('Bank Account #', j.account_id)
    END AS leg_type,
    j.debit,
    j.credit,
    j.is_reclassified,
    j.classification_status,
    JSON_UNQUOTE(JSON_EXTRACT(j.evaluation_matrix_snapshot, '$.resolved_subcategory')) AS resolved_subcategory,
    s.narration AS raw_bank_narration
FROM ledger_journal_entry j
LEFT JOIN ledger_statementstagingline s 
    ON j.row_identifier = s.row_identifier
WHERE j.row_identifier = (
    -- Picks 1 sample row identifier from Node 99
    SELECT row_identifier 
    FROM ledger_journal_entry 
    WHERE account_id = 99 
    LIMIT 1
);



SELECT 
    row_identifier,
    COUNT(*) AS total_journal_legs,
    SUM(CASE WHEN account_id = 99 THEN 1 ELSE 0 END) AS node_99_legs,
    SUM(CASE WHEN account_id != 99 THEN 1 ELSE 0 END) AS bank_legs
FROM ledger_journal_entry
GROUP BY row_identifier
HAVING COUNT(*) != 2;


SELECT 
    account_id,
    CASE WHEN account_id = 99 THEN 'Node 99 (Suspense / Taxonomy)' ELSE 'Bank Account' END AS account_role,
    COUNT(*) AS total_legs,
    SUM(debit) AS total_debit,
    SUM(credit) AS total_credit
FROM ledger_journal_entry
GROUP BY account_id, account_role
ORDER BY total_legs DESC;



SELECT 
    row_identifier,
    COUNT(*) AS total_journal_legs,
    SUM(CASE WHEN account_id = 99 THEN 1 ELSE 0 END) AS node_99_legs,
    SUM(CASE WHEN account_id != 99 THEN 1 ELSE 0 END) AS bank_legs
FROM ledger_journal_entry
GROUP BY row_identifier
HAVING COUNT(*) != 2;


SELECT 
    row_identifier,
    account_id,
    debit,
    credit,
    COUNT(*) AS duplicate_count,
    GROUP_CONCAT(id SEPARATOR ' | ') AS journal_entry_ids
FROM ledger_journal_entry
GROUP BY row_identifier, account_id, debit, credit
HAVING COUNT(*) > 1
LIMIT 50;


SELECT 
    j.row_identifier,
    j.id AS entry_id,
    j.account_id,
    j.debit,
    j.credit,
    j.created_at
FROM ledger_journal_entry j
WHERE j.row_identifier IN (
    SELECT row_identifier 
    FROM ledger_journal_entry 
    GROUP BY row_identifier, account_id 
    HAVING COUNT(*) > 1
)
ORDER BY j.row_identifier, j.account_id, j.created_at ASC
LIMIT 40;


SELECT 
    (SELECT COUNT(*) FROM ledger_statementstagingline) AS total_staging_lines,
    (SELECT COUNT(DISTINCT row_identifier) FROM ledger_journal_entry) AS unique_journal_transactions,
    (SELECT COUNT(*) FROM ledger_journal_entry) AS total_journal_entry_rows,
    (SELECT COUNT(*) FROM ledger_journal_entry) / (SELECT COUNT(DISTINCT row_identifier) FROM ledger_journal_entry) AS avg_legs_per_transaction;
    
    
    
    SELECT 
    account_id,
    COUNT(*) AS total_rows,
    COUNT(DISTINCT row_identifier) AS unique_transactions,
    COUNT(*) - COUNT(DISTINCT row_identifier) AS excess_duplicate_rows
FROM ledger_journal_entry
GROUP BY account_id
ORDER BY account_id ASC;



SET SQL_SAFE_UPDATES = 0;

-- 1. Get all row_identifiers associated with Account 4
CREATE TEMPORARY TABLE IF NOT EXISTS tmp_account4_rows AS
SELECT DISTINCT row_identifier 
FROM ledger_journal_entry 
WHERE account_id = 4;

-- 2. Delete ALL journal legs (both Account 4 legs and Node 99 legs) for these rows
DELETE FROM ledger_journal_entry 
WHERE row_identifier IN (SELECT row_identifier FROM tmp_account4_rows);

-- 3. Reset the classification/routing status on Account 4's raw staging lines back to PENDING
UPDATE ledger_statementstagingline
SET classification_status = 'PENDING',
    routing_status = 'PENDING'
WHERE account_id = 4;

DROP TEMPORARY TABLE IF EXISTS tmp_account4_rows;

SET SQL_SAFE_UPDATES = 1;


SET SQL_SAFE_UPDATES = 0;

-- Reset staging line status for Account 4 back to PENDING
UPDATE ledger_statementstagingline
SET routing_status = 'PENDING'
WHERE account_id = 4;

DROP TEMPORARY TABLE IF EXISTS tmp_account4_rows;

SET SQL_SAFE_UPDATES = 1;

SELECT 
    (SELECT COUNT(*) FROM ledger_statementstagingline) AS total_staging_lines,
    (SELECT COUNT(DISTINCT row_identifier) FROM ledger_journal_entry) AS unique_journal_transactions,
    (SELECT COUNT(*) FROM ledger_journal_entry) AS total_journal_entry_rows,
    (SELECT COUNT(*) FROM ledger_journal_entry) / (SELECT COUNT(DISTINCT row_identifier) FROM ledger_journal_entry) AS avg_legs_per_transaction;
    
    
    SELECT 
    account_id,
    COUNT(*) AS total_rows,
    COUNT(DISTINCT row_identifier) AS unique_transactions,
    COUNT(*) - COUNT(DISTINCT row_identifier) AS excess_duplicate_rows
FROM ledger_journal_entry
GROUP BY account_id
ORDER BY account_id ASC;


SELECT 
    COUNT(*) AS total_transactions,
    SUM(credit) AS total_credit_amount,
    SUM(debit) AS total_debit_amount
FROM ledger_journal_entry
WHERE account_id = 4
  AND (
      -- Search inside JSON remarks payload
      JSON_UNQUOTE(JSON_EXTRACT(remarks, '$.payee')) LIKE '%SUMEE S%'
      OR JSON_UNQUOTE(JSON_EXTRACT(remarks, '$.display_text')) LIKE '%SUMEE S%'
      -- Fallback search against raw bank statement narration
      OR row_identifier IN (
          SELECT row_identifier 
          FROM ledger_statementstagingline 
          WHERE narration LIKE '%SUMEE S%'
      )
  );


SELECT 
    j.transaction_date,
    j.row_identifier,
    j.debit,
    j.credit,
    j.classification_status,
    s.narration AS raw_bank_narration
FROM ledger_journal_entry j
LEFT JOIN ledger_statementstagingline s 
    ON j.row_identifier = s.row_identifier
WHERE j.account_id = 4
  AND (
      JSON_UNQUOTE(JSON_EXTRACT(j.remarks, '$.payee')) LIKE '%SUMEE S%'
      OR JSON_UNQUOTE(JSON_EXTRACT(j.remarks, '$.display_text')) LIKE '%SUMEE S%'
      OR s.narration LIKE '%SUMEE S%'
  )
ORDER BY j.transaction_date DESC;


SELECT 
    j.row_identifier,
    j.account_id,
    CASE 
        WHEN j.account_id = 99 THEN 'Node 99 (Suspense / Workbench View)'
        ELSE CONCAT('Bank Account #', j.account_id)
    END AS ledger_perspective,
    j.debit,
    j.credit,
    s.narration AS raw_bank_narration
FROM ledger_journal_entry j
LEFT JOIN ledger_statementstagingline s 
    ON j.row_identifier = s.row_identifier
WHERE j.row_identifier = (
    -- Picks 1 sample row identifier for SUMEE S from Account 4
    SELECT row_identifier 
    FROM ledger_journal_entry 
    WHERE account_id = 4 
      AND debit > 0
      AND row_identifier IN (
          SELECT row_identifier 
          FROM ledger_statementstagingline 
          WHERE narration LIKE '%SUMEE S%'
      )
    LIMIT 1
);




SELECT 
    id,
    asset_code,
    name,
    category,
    acquisition_cost,
    current_valuation,
    status,
    JSON_PRETTY(metadata_payload) AS metadata,
    created_at
FROM ledger_asset_subledger
WHERE asset_code = 'AST-RE-001';



select * from ledger_statementstagingline where narration like "%3b072d613f5fc7d03b814a8815b3be44a7f9%"

SELECT 
    cs.id AS schedule_id,
    cs.title,
    cs.schedule_type,
    cs.due_date,
    cs.expected_amount,
    cs.is_paid,
    cs.paid_at,
    cs.linked_row_identifier
FROM ledger_asset_compliance_schedule cs
JOIN ledger_asset_subledger ast ON cs.asset_id = ast.id
WHERE ast.asset_code = 'AST-RE-001'
ORDER BY cs.due_date ASC;


SELECT 
    ast.asset_code,
    ast.name AS asset_name,
    cs.title AS schedule_title,
    cs.due_date,
    cs.is_paid,
    cs.paid_at,
    tm.row_identifier,
    tm.amount AS paid_amount,
    tm.user_note
FROM ledger_asset_subledger ast
LEFT JOIN ledger_asset_compliance_schedule cs ON ast.id = cs.asset_id
LEFT JOIN ledger_asset_transaction_mapping tm ON cs.id = tm.schedule_id
WHERE ast.asset_code = 'AST-RE-001';