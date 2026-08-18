export interface FieldDefinition {
  key: string;
  label: string;
  placeholder?: string;
  type?: 'text' | 'number' | 'date';
}

export const CATEGORY_DYNAMIC_SCHEMAS: Record<string, FieldDefinition[]> = {
  // ==========================================
  // 📦 ASSET SUB-LEDGER SCHEMAS
  // ==========================================
  REAL_ESTATE: [
    {
      key: 'sro_name',
      label: 'SRO Office Name',
      placeholder: 'e.g. Kakkanad SRO',
    },
    {
      key: 'survey_no',
      label: 'Survey / Sub-division No.',
      placeholder: 'e.g. 342/12-A',
    },
    {
      key: 'panchayat_tax',
      label: 'Panchayat / Property Tax ID',
      placeholder: 'e.g. TAX-2026-88',
    },
    {
      key: 'tax_due_date',
      label: 'Next Tax Due Date',
      placeholder: 'YYYY-MM-DD',
      type: 'date',
    },
    {
      key: 'deed_number',
      label: 'Deed / Document Number',
      placeholder: 'e.g. Doc #1029/2024',
    },
  ],
  FIXED_DEPOSIT: [
    {
      key: 'deposit_receipt_no',
      label: 'FD Receipt Number',
      placeholder: 'e.g. FDR-9938102',
    },
    {
      key: 'interest_rate_pct',
      label: 'Interest Rate (%)',
      placeholder: 'e.g. 7.25',
      type: 'number',
    },
    {
      key: 'maturity_date',
      label: 'Maturity Date',
      placeholder: 'YYYY-MM-DD',
      type: 'date',
    },
    {
      key: 'payout_type',
      label: 'Interest Payout (Cumulative/Monthly)',
      placeholder: 'e.g. Quarterly Payout',
    },
  ],
  RECURRING_DEPOSIT: [
    {
      key: 'account_number',
      label: 'RD Account Number',
      placeholder: 'e.g. RD-8820391',
    },
    {
      key: 'monthly_installment',
      label: 'Monthly Deposit (₹)',
      placeholder: 'e.g. 5000',
      type: 'number',
    },
    {
      key: 'interest_rate_pct',
      label: 'Interest Rate (%)',
      placeholder: 'e.g. 7.0',
      type: 'number',
    },
    {
      key: 'maturity_date',
      label: 'Maturity Date',
      placeholder: 'YYYY-MM-DD',
      type: 'date',
    },
  ],
  MARKET_INVESTMENT: [
    {
      key: 'symbol_ticker',
      label: 'Stock Ticker / ISIN / Scheme',
      placeholder: 'e.g. RELIANCE / INF200K01135',
    },
    {
      key: 'quantity',
      label: 'Units / Number of Shares',
      placeholder: 'e.g. 100',
      type: 'number',
    },
    {
      key: 'folio_dp_id',
      label: 'Demat DP ID / Folio No.',
      placeholder: 'e.g. IN300126-10293847',
    },
    {
      key: 'amc_broker',
      label: 'Broker / AMC Name',
      placeholder: 'e.g. Zerodha / SBI Mutual Fund',
    },
  ],
  PENSION_RETIREMENT: [
    {
      key: 'pran_account_no',
      label: 'PRAN / Account Number',
      placeholder: 'e.g. 110029384756',
    },
    {
      key: 'tier_type',
      label: 'Tier / Type',
      placeholder: 'e.g. NPS Tier I or PPF',
    },
    {
      key: 'maturity_date',
      label: 'Maturity / Retirement Date',
      placeholder: 'YYYY-MM-DD',
      type: 'date',
    },
  ],
  INSURANCE_PLAN: [
    {
      key: 'policy_number',
      label: 'Policy Number',
      placeholder: 'e.g. POL-9938201',
    },
    {
      key: 'sum_assured',
      label: 'Sum Assured (₹)',
      placeholder: 'e.g. 1000000',
      type: 'number',
    },
    {
      key: 'premium_amount',
      label: 'Annual Premium (₹)',
      placeholder: 'e.g. 25000',
      type: 'number',
    },
    {
      key: 'next_due_date',
      label: 'Next Premium Due Date',
      placeholder: 'YYYY-MM-DD',
      type: 'date',
    },
  ],
  VEHICLE: [
    {
      key: 'registration_no',
      label: 'Vehicle Reg. Number',
      placeholder: 'e.g. KL-01-CB-1234',
    },
    {
      key: 'chassis_no',
      label: 'Chassis / VIN Number',
      placeholder: 'e.g. MA3EWB...829',
    },
    {
      key: 'insurance_expiry',
      label: 'Insurance Expiry Date',
      placeholder: 'YYYY-MM-DD',
      type: 'date',
    },
  ],
  PRECIOUS_METALS: [
    {
      key: 'weight_grams',
      label: 'Weight (Grams)',
      placeholder: 'e.g. 50.5',
      type: 'number',
    },
    { key: 'purity_karat', label: 'Purity', placeholder: 'e.g. 22K or 24K' },
    {
      key: 'hallmark_number',
      label: 'HUID / Hallmark No.',
      placeholder: 'e.g. HUID-88392',
    },
  ],
  PERSONAL_RECEIVABLE: [
    {
      key: 'borrower_name',
      label: 'Borrower Name',
      placeholder: 'e.g. John Doe',
    },
    {
      key: 'loan_agreed_date',
      label: 'Loan Date',
      placeholder: 'YYYY-MM-DD',
      type: 'date',
    },
    {
      key: 'expected_return_date',
      label: 'Expected Return Date',
      placeholder: 'YYYY-MM-DD',
      type: 'date',
    },
  ],

  // ==========================================
  // 💰 INCOME STREAM SUB-LEDGER SCHEMAS
  // ==========================================
  RENTAL_STREAM: [
    {
      key: 'tenant_name',
      label: 'Tenant Name',
      placeholder: 'e.g. Alex Johnson',
    },
    {
      key: 'monthly_rent_amount',
      label: 'Monthly Rent (₹)',
      placeholder: 'e.g. 25000',
      type: 'number',
    },
    {
      key: 'lease_expiry_date',
      label: 'Lease Agreement Expiry',
      placeholder: 'YYYY-MM-DD',
      type: 'date',
    },
    {
      key: 'security_deposit_held',
      label: 'Security Deposit Held (₹)',
      placeholder: 'e.g. 100000',
      type: 'number',
    },
  ],
  RENT_INCOME: [
    {
      key: 'tenant_name',
      label: 'Tenant Name',
      placeholder: 'e.g. Alex Johnson',
    },
    {
      key: 'unit_flat_no',
      label: 'Flat / Unit Number',
      placeholder: 'e.g. Flat 302, Sun Medanta',
    },
    {
      key: 'lease_expiry',
      label: 'Lease Expiry Date',
      placeholder: 'YYYY-MM-DD',
      type: 'date',
    },
  ],
  DIVIDEND_FOLIO: [
    {
      key: 'folio_dp_id',
      label: 'Demat / Folio Number',
      placeholder: 'e.g. 10293847/SBI-MF',
    },
    {
      key: 'payout_frequency',
      label: 'Payout Frequency',
      placeholder: 'e.g. Quarterly / Interim',
    },
    {
      key: 'expected_yield_pct',
      label: 'Expected Dividend Yield (%)',
      placeholder: 'e.g. 3.5',
      type: 'number',
    },
  ],
  INTEREST_INCOME: [
    {
      key: 'payout_frequency',
      label: 'Payout Frequency',
      placeholder: 'e.g. Monthly / On Maturity',
    },
    {
      key: 'interest_rate_pct',
      label: 'Applicable Interest Rate (%)',
      placeholder: 'e.g. 7.5',
      type: 'number',
    },
    {
      key: 'tds_applicable',
      label: 'TDS Deducted (Yes/No)',
      placeholder: 'e.g. Yes @ 10%',
    },
  ],
  SALARY_EOSB: [
    {
      key: 'employer_name',
      label: 'Employer / Company Name',
      placeholder: 'e.g. Tech Corp Ltd',
    },
    {
      key: 'employee_id',
      label: 'Employee ID',
      placeholder: 'e.g. EMP-9921',
    },
    {
      key: 'pay_cycle_day',
      label: 'Salary Credit Day of Month',
      placeholder: 'e.g. 1st or 30th',
    },
  ],

  // ==========================================
  // 📊 EXPENSE COST CENTER SUB-LEDGER SCHEMAS
  // ==========================================
  VENDOR_MERCHANT: [
    {
      key: 'vendor_gstin',
      label: 'Vendor GSTIN / Tax ID',
      placeholder: 'e.g. 32AABCU9603R1ZM',
    },
    {
      key: 'contract_ref',
      label: 'Contract / AMC Reference No.',
      placeholder: 'e.g. AMC-2026-004',
    },
    {
      key: 'payment_terms',
      label: 'Payment Terms',
      placeholder: 'e.g. Net 30 Days',
    },
  ],
  CHARITY_RECIPIENT: [
    {
      key: 'pan_number',
      label: 'Institution PAN Number',
      placeholder: 'e.g. AAATT8829F',
    },
    {
      key: 'receipt_80g_no',
      label: '80G Certificate Number',
      placeholder: 'e.g. 80G/2025/1029',
    },
  ],
  MMC_CHARGES: [
    {
      key: 'association_flat_no',
      label: 'Apartment / Flat Identifier',
      placeholder: 'e.g. Flat 101, Sun Medanta',
    },
    {
      key: 'monthly_maintenance_fee',
      label: 'Monthly MMC Rate (₹)',
      placeholder: 'e.g. 3500',
      type: 'number',
    },
    {
      key: 'next_due_date',
      label: 'Next Maintenance Due Date',
      placeholder: 'YYYY-MM-DD',
      type: 'date',
    },
  ],
  UTILITIES_BILLS: [
    {
      key: 'consumer_number',
      label: 'Consumer / KSEB / Water ID',
      placeholder: 'e.g. 1155029384',
    },
    {
      key: 'billing_cycle',
      label: 'Billing Cycle',
      placeholder: 'e.g. Bi-monthly',
    },
  ],
};
