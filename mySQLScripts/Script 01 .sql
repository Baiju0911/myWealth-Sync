
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
    WHERE account_id = 7
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