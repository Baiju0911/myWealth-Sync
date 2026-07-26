
SELECT 
    a.name AS ledger_account_name,
    a.account_type AS asset_or_core_type,
    COALESCE(
        JSON_UNQUOTE(JSON_EXTRACT(j.evaluation_matrix_snapshot, '$.leg_context')),
        JSON_UNQUOTE(JSON_EXTRACT(j.evaluation_matrix_snapshot, '$.resolved_category')),
        'UNCLASSIFIED'
    ) AS taxonomy_node,
    COUNT(*) AS entry_lines,
    SUM(j.debit) AS total_debits,
    SUM(j.credit) AS total_credits,
    ROUND(SUM(j.debit) - SUM(j.credit), 2) AS group_variance
FROM ledger_journal_entry j
JOIN ledger_account a ON j.account_id = a.id
GROUP BY 
    a.name,
    a.account_type,
    taxonomy_node
ORDER BY 
    a.account_type DESC, 
    a.name ASC;




-- Dynamic Double-Entry Ledger Verification Query
SELECT 
    j.account_id AS target_account,
    a.name AS account_name,
    a.account_type AS account_nature,
    COUNT(*) AS total_committed_lines,
    SUM(j.debit) AS total_debit,
    SUM(j.credit) AS total_credit,
    ROUND(SUM(j.debit) - SUM(j.credit), 2) AS balancing_variance
FROM ledger_journal_entry j
JOIN ledger_account a ON j.account_id = a.id
WHERE j.row_identifier IN (
    SELECT row_identifier 
    FROM ledger_journal_entry 
    
)
GROUP BY j.account_id, a.name, a.account_type;






SELECT 
    j.account_id AS target_account,
    CASE 
        WHEN j.account_id = 7 THEN 'Physical Liquidity Core'
        ELSE 'System Rule Engine Offset'
    END AS entry_nature,
    -- Safely extracts leg_context for account 7 and resolved_category for account 99
    COALESCE(
        JSON_UNQUOTE(JSON_EXTRACT(j.evaluation_matrix_snapshot, '$.leg_context')),
        JSON_UNQUOTE(JSON_EXTRACT(j.evaluation_matrix_snapshot, '$.resolved_category'))
    ) AS extracted_taxonomy_node,
    COUNT(*) AS total_committed_lines,
    SUM(j.debit) AS total_debit_volume,
    SUM(j.credit) AS total_credit_volume,
    ROUND(SUM(j.debit) - SUM(j.credit), 2) AS node_variance
FROM ledger_journal_entry j
WHERE j.row_identifier IN (
    SELECT row_identifier 
    FROM ledger_journal_entry 
    WHERE account_id = 7
)
GROUP BY 
    j.account_id, 
    extracted_taxonomy_node;




select count(*) from ledger_journal_entry






SELECT 
    SUM(total_debit_volume) AS grand_total_debits,
    SUM(total_credit_volume) AS grand_total_credits,
    ROUND(SUM(node_variance), 2) AS absolute_system_variance
FROM (
    SELECT 
        SUM(j.debit) AS total_debit_volume,
        SUM(j.credit) AS total_credit_volume,
        SUM(j.debit) - SUM(j.credit) AS node_variance
    FROM ledger_journal_entry j
    WHERE j.row_identifier IN (SELECT row_identifier FROM ledger_journal_entry WHERE account_id = 7)
    GROUP BY j.account_id, COALESCE(JSON_UNQUOTE(JSON_EXTRACT(j.evaluation_matrix_snapshot, '$.leg_context')), JSON_UNQUOTE(JSON_EXTRACT(j.evaluation_matrix_snapshot, '$.resolved_category')))
) AS breakdown_universe;





SELECT 
    a.name AS ledger_account_name,
    a.account_type AS asset_or_core_type,
    COALESCE(
        JSON_UNQUOTE(JSON_EXTRACT(j.evaluation_matrix_snapshot, '$.leg_context')),
        JSON_UNQUOTE(JSON_EXTRACT(j.evaluation_matrix_snapshot, '$.resolved_category')),
        'UNCLASSIFIED'
    ) AS taxonomy_node,
    COUNT(*) AS entry_lines,
    SUM(j.debit) AS total_debits,
    SUM(j.credit) AS total_credits,
    ROUND(SUM(j.debit) - SUM(j.credit), 2) AS group_variance
FROM ledger_journal_entry j
JOIN ledger_account a ON j.account_id = a.id
GROUP BY 
    a.name,
    a.account_type,
    taxonomy_node
ORDER BY 
    a.account_type DESC, 
    a.name ASC;
    
    
    
    
    
    
    
    SELECT 
    j.row_identifier,
    MAX(j.transaction_date) AS date,
    -- Physical Side
    SUM(CASE WHEN j.account_id = 7 THEN j.debit ELSE 0 END) AS real_debit,
    SUM(CASE WHEN j.account_id = 7 THEN j.credit ELSE 0 END) AS real_credit,
    -- System Side
    SUM(CASE WHEN j.account_id = 99 THEN j.debit ELSE 0 END) AS sys_debit,
    SUM(CASE WHEN j.account_id = 99 THEN j.credit ELSE 0 END) AS sys_credit,
    -- Net Transaction Balance
    ROUND(SUM(j.debit) - SUM(j.credit), 2) AS transaction_variance
FROM ledger_journal_entry j
WHERE j.row_identifier IN (SELECT row_identifier FROM ledger_journal_entry WHERE account_id = 7)
GROUP BY j.row_identifier
HAVING transaction_variance != 0;








SELECT 
    CASE 
        WHEN a.account_type = 'SYSTEM_CORE' THEN CONCAT('Virtual System Node (ID: ', a.id, ' - ', a.name, ')')
        ELSE CONCAT('Real Physical Account (ID: ', a.id, ' - ', a.name, ')')
    END AS account_node_context,
    COUNT(*) AS entries_processed,
    SUM(j.debit) AS entry_debit_total,
    SUM(j.credit) AS entry_credit_total,
    ROUND(SUM(j.debit) - SUM(j.credit), 2) AS node_variance
FROM ledger_journal_entry j
JOIN ledger_account a ON j.account_id = a.id
WHERE j.row_identifier IN (
    SELECT row_identifier 
    FROM ledger_journal_entry 
 
)
GROUP BY a.id, a.name, a.account_type;



select distinct(lje.account_id)  from ledger_journal_entry lje 








SELECT 
    id,
    rule_code,
    rule_title,
    entry_type,
    JSON_UNQUOTE(JSON_EXTRACT(rule_metadata, '$.category')) AS primary_category,
    JSON_UNQUOTE(JSON_EXTRACT(rule_metadata, '$.subcategory')) AS subcategory,
    description_tags
FROM ledger_accountingrule la 
WHERE is_active = 1
ORDER BY id ASC;


SELECT 
    JSON_UNQUOTE(JSON_EXTRACT(rule_metadata, '$.category')) AS primary_category,
    JSON_UNQUOTE(JSON_EXTRACT(rule_metadata, '$.subcategory')) AS subcategory,
    COUNT(*) AS rule_count
FROM ledger_accountingrule la 
WHERE is_active = 1
GROUP BY primary_category, subcategory
ORDER BY primary_category, subcategory;






SELECT 
    resolved_category AS primary_category,
    resolved_subcategory AS subcategory,
    COUNT(*) AS transaction_count,
    FORMAT(SUM(debit), 2) AS total_debit,
    FORMAT(SUM(credit), 2) AS total_credit,
    FORMAT(SUM(debit) - SUM(credit), 2) AS net_balance
FROM ledger_wip_evaluation_matrix
WHERE account_id = 3
GROUP BY resolved_category, resolved_subcategory
ORDER BY resolved_category, resolved_subcategory;





SELECT 
    primary_category,
    subcategory,
    COUNT(*) AS transaction_count,
    FORMAT(SUM(debit), 2) AS total_debit,
    FORMAT(SUM(credit), 2) AS total_credit,
    FORMAT(SUM(debit) - SUM(credit), 2) AS net_balance
FROM ledger_journal_entry lje 
WHERE account_id = 60
GROUP BY primary_category, subcategory
ORDER BY primary_category, subcategory;



SELECT 
    resolved_category AS primary_category,
    resolved_subcategory AS subcategory,
    COUNT(*) AS transaction_count,
    FORMAT(SUM(debit), 2) AS total_debit,
    FORMAT(SUM(credit), 2) AS total_credit,
    FORMAT(SUM(debit) - SUM(credit), 2) AS net_balance
FROM ledger_journal_entry lje 
WHERE account_id = 60
GROUP BY resolved_category, resolved_subcategory
ORDER BY resolved_category, resolved_subcategory;







SELECT 
    JSON_UNQUOTE(JSON_EXTRACT(j.evaluation_matrix_snapshot, '$.resolved_category')) AS primary_category,
    JSON_UNQUOTE(JSON_EXTRACT(j.evaluation_matrix_snapshot, '$.resolved_subcategory')) AS subcategory,
    COUNT(DISTINCT j.row_identifier) AS transaction_count,
    
    -- Account 3 (Physical Bank Liquidity Leg)
    FORMAT(SUM(CASE WHEN j.account_id = 3 THEN j.debit ELSE 0 END), 2) AS bank_debit_acc3,
    FORMAT(SUM(CASE WHEN j.account_id = 3 THEN j.credit ELSE 0 END), 2) AS bank_credit_acc3,
    
    -- Account 99 (System Taxonomy Integration Leg)
    FORMAT(SUM(CASE WHEN j.account_id = 99 THEN j.debit ELSE 0 END), 2) AS taxonomy_debit_acc99,
    FORMAT(SUM(CASE WHEN j.account_id = 99 THEN j.credit ELSE 0 END), 2) AS taxonomy_credit_acc99,
    
    -- Double-Entry Balance Proof (Should equal 0.00)
    FORMAT(
        SUM(CASE WHEN j.account_id = 3 THEN j.debit - j.credit ELSE 0 END) +
        SUM(CASE WHEN j.account_id = 99 THEN j.debit - j.credit ELSE 0 END),
        2
    ) AS leg_variance_proof

FROM ledger_journal_entry j
WHERE j.row_identifier IN (
    SELECT row_identifier FROM ledger_journal_entry WHERE account_id = 3
)
GROUP BY 1, 2
ORDER BY primary_category, subcategory;






SELECT 
    CASE 
        WHEN j.account_id = 3 THEN 'Account 3: Bank Liquidity Node (SIB)'
        WHEN j.account_id = 99 THEN 'Account 99: System Taxonomy Node'
        ELSE CONCAT('Account ID: ', j.account_id)
    END AS account_node,
    COALESCE(
        JSON_UNQUOTE(JSON_EXTRACT(j.evaluation_matrix_snapshot, '$.resolved_category')),
        'Bank Cash Movement'
    ) AS primary_category,
    COALESCE(
        JSON_UNQUOTE(JSON_EXTRACT(j.evaluation_matrix_snapshot, '$.resolved_subcategory')),
        'Liquidity Core'
    ) AS subcategory,
    COUNT(*) AS transaction_count,
    FORMAT(SUM(j.debit), 2) AS total_debit,
    FORMAT(SUM(j.credit), 2) AS total_credit,
    FORMAT(SUM(j.debit) - SUM(j.credit), 2) AS net_balance
FROM ledger_journal_entry j
WHERE j.account_id IN (3, 99)
GROUP BY j.account_id, 2, 3
ORDER BY j.account_id, primary_category, subcategory;





SELECT 
    row_identifier,
    SUM(debit) AS total_debit,
    SUM(credit) AS total_credit,
    (SUM(debit) - SUM(credit)) AS imbalance_amount
FROM ledger_journal_entry
GROUP BY row_identifier
HAVING imbalance_amount <> 0;




SELECT 
    SUM(debit) AS global_total_debit,
    SUM(credit) AS global_total_credit,
    (SUM(debit) - SUM(credit)) AS global_difference
FROM ledger_journal_entry;



-- 1. Check Staging Table
SELECT 
    '1. STAGING' AS table_source,
    row_identifier,
    narration,
    routing_status,
    applied_rule_code,
    updated_at
FROM ledger_statementstagingline
WHERE row_identifier = '052cc276-600a-4de5-bbb1-a8de05a75285'

UNION ALL

-- 2. Check WIP Evaluation Matrix
SELECT 
    '2. WIP MATRIX' AS table_source,
    row_identifier,
    applied_rule_code,
    resolved_category AS category,
    resolved_subcategory AS subcategory,
    updated_at
FROM ledger_wip_evaluation_matrix
WHERE row_identifier = '052cc276-600a-4de5-bbb1-a8de05a75285'

UNION ALL

-- 3. Check Journal Entries (Both Legs)
SELECT 
    '3. JOURNAL ENTRY' AS table_source,
    row_identifier,
    classification_status,
    account_id,
    CAST(debit AS CHAR) AS debit,
    updated_at
FROM ledger_journal_entry
WHERE row_identifier = '052cc276-600a-4de5-bbb1-a8de05a75285';