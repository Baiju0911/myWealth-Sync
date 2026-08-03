use mywealth_sync_db

SELECT 
    id,
    rule_code,
    name,
    rule_type,
    target_category,
    target_subcategory,
    patterns,
    taxonomy_id,
    match_count,
    created_at
FROM ledger_classification_rule
WHERE patterns LIKE '%BLUEDART%' OR patterns LIKE '%BLUEDOT%'
ORDER BY created_at DESC;




SELECT 
    id,
    account_id,
    debit,
    credit,
    classification_status,
    is_reclassified,
    evaluation_matrix_snapshot->>'$.resolved_subcategory' AS resolved_sub,
    evaluation_matrix_snapshot->>'$.applied_rule_code' AS applied_rule,
    remarks->>'$.display_text' AS display_text,
    created_at
FROM ledger_journal_entry
WHERE account_id = 99 
  AND is_reclassified = TRUE
ORDER BY created_at DESC
LIMIT 10;



SELECT 
    account_id,
    CASE 
        WHEN account_id = 99 AND is_reclassified = FALSE THEN '🔴 Pending Suspense (Node 99)'
        WHEN is_reclassified = TRUE THEN '🟡 Reclassified via Workbench'
        ELSE '🟢 Auto-Classified at Ingestion'
    END AS processing_status,
    COUNT(*) AS total_rows,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY account_id), 2) AS percentage_share,
    SUM(debit) AS total_debit,
    SUM(credit) AS total_credit
FROM ledger_journal_entry
WHERE account_id IN (3, 99)  -- Replace 3 with your active account_id
GROUP BY account_id, processing_status
ORDER BY account_id, total_rows DESC;


SELECT 
    r.rule_code,
    r.rule_type,
    r.name,
    r.target_subcategory,
    r.match_count AS logged_rule_matches,
    COUNT(j.id) AS actual_journal_matches,
    SUM(j.debit + j.credit) AS total_volume_rupees
FROM ledger_classification_rule r
LEFT JOIN ledger_journal_entry j 
  ON j.evaluation_matrix_snapshot->>'$.applied_rule_code' = r.rule_code
GROUP BY r.id, r.rule_code, r.rule_type, r.name, r.target_subcategory, r.match_count
ORDER BY actual_journal_matches DESC;



SELECT 
    j.id AS entry_id,
    j.account_id,
    j.debit,
    j.credit,
    r.rule_code,
    r.rule_type AS rule_direction,
    CASE 
        WHEN j.debit > 0 THEN 'Debit'
        WHEN j.credit > 0 THEN 'Credit'
    END AS actual_txn_direction,
    j.evaluation_matrix_snapshot->>'$.resolved_subcategory' AS resolved_sub
FROM ledger_journal_entry j
JOIN ledger_classification_rule r 
  ON j.evaluation_matrix_snapshot->>'$.applied_rule_code' = r.rule_code
WHERE (j.debit > 0 AND r.rule_type = 'Credit')
   OR (j.credit > 0 AND r.rule_type = 'Debit');
   
   
   
   
   SELECT 
    account_id,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN account_id = 99 AND is_reclassified = FALSE THEN 1 ELSE 0 END) AS pending_suspense_rows,
    SUM(CASE WHEN is_reclassified = TRUE THEN 1 ELSE 0 END) AS workbench_reclassified_rows,
    SUM(CASE WHEN account_id != 99 AND (is_reclassified = FALSE OR is_reclassified IS NULL) THEN 1 ELSE 0 END) AS auto_classified_rows,
    CONCAT(ROUND(
        (COUNT(*) - SUM(CASE WHEN account_id = 99 AND is_reclassified = FALSE THEN 1 ELSE 0 END)) * 100.0 / COUNT(*), 
    2), '%') AS overall_clearance_rate,
    ROUND(SUM(debit), 2) AS total_debit_inr,
    ROUND(SUM(credit), 2) AS total_credit_inr,
    ROUND(ABS(SUM(debit) - SUM(credit)), 2) AS double_entry_variance
FROM ledger_journal_entry
GROUP BY account_id WITH ROLLUP;


select * from ledger_journal_entry
SELECT 
    -- 1. Ledger Target Context
    account_id,
    COUNT(id) AS total_rows,
    
    -- 2. Status Breakdown
    COUNT(CASE WHEN classification_status = 'INITIAL' AND account_id = '99' THEN 1 END) AS pending_suspense_rows,
    COUNT(CASE WHEN is_reclassified = '1' OR is_reclassified = 1 THEN 1 END) AS reclassified_rows,
    COUNT(CASE WHEN classification_status != 'INITIAL' OR account_id != '99' THEN 1 END) AS cleared_rows,
    
    -- 3. Automation & Rule Intelligence Proof
    ROUND(
        (COUNT(CASE WHEN classification_status != 'INITIAL' OR account_id != '99' THEN 1 END) * 100.0 / COUNT(id)), 
        2
    ) || '%' AS overall_clearance_rate,
    
    ROUND(
        AVG(CAST(JSON_EXTRACT(evaluation_matrix_snapshot, '$.confidence_score') AS FLOAT)), 
        1
    ) AS avg_confidence_score,
    
    -- 4. Extracted Entities & Pattern Count (Jio, Lulu, Paytm, etc.)
    COUNT(DISTINCT JSON_EXTRACT(remarks, '$.payee')) AS distinct_payees_extracted,
    COUNT(DISTINCT JSON_EXTRACT(evaluation_matrix_snapshot, '$.applied_rule_code')) AS active_rules_triggered,
    
    -- 5. Financial Totals (INR)
    ROUND(SUM(CAST(debit AS FLOAT)), 2) AS total_debit_inr,
    ROUND(SUM(CAST(credit AS FLOAT)), 2) AS total_credit_inr,
    ROUND(SUM(CAST(credit AS FLOAT)) - SUM(CAST(debit AS FLOAT)), 2) AS net_liquidity_inr,
    ROUND(ABS(SUM(CAST(debit AS FLOAT)) - SUM(CAST(credit AS FLOAT))), 2) AS double_entry_variance,
    
    -- 6. Audit Symmetry Proof Flag
    CASE 
        WHEN ROUND(ABS(SUM(CAST(debit AS FLOAT)) - SUM(CAST(credit AS FLOAT))), 2) = 0.00 THEN 'TRUE (BALANCED)' 
        ELSE 'FALSE (IMBALANCE)' 
    END AS is_balanced_proof

FROM ledger_journal_entry -- 👈 Replace with your actual table name if different
GROUP BY account_id WITH ROLLUP;





SELECT 
    account_id,
    COUNT(id) AS total_rows,
    COUNT(CASE WHEN is_reclassified = 1 OR is_reclassified = '1' THEN 1 END) AS reclassified_rows,
    COUNT(CASE WHEN classification_status = 'SWEEP_CLEARED' THEN 1 END) AS sweep_cleared_rows,
    COUNT(CASE WHEN classification_status = 'INITIAL' AND account_id = '99' THEN 1 END) AS pending_suspense_rows,
    ROUND(
        AVG(CAST(JSON_EXTRACT(evaluation_matrix_snapshot, '$.confidence_score') AS FLOAT)), 
        1
    ) AS avg_confidence,
    ROUND(SUM(CAST(debit AS FLOAT)), 2) AS total_debit,
    ROUND(SUM(CAST(credit AS FLOAT)), 2) AS total_credit
FROM ledger_journal_entry
GROUP BY account_id WITH ROLLUP;