// src/types/ledger.ts

export interface BankEntity {
  id: string;
  code: string;
  display_name: string;
  account_count?: number;
  credential_count?: number;
}

export interface AccountEntity {
  id: string;
  name: string;
  account_type: string;

  // 🎯 THE FIX: Expose the 4-digit token constraint key to the compilation layer
  account_number: string;

  ifsc_code: string;
  branch_name: string;
  address: string;
  bank_id: string;
}

export interface CredentialEntity {
  id: string;
  account_id: string;
  statement_password: string;
  updated_at: string;
}

export interface StagingPreviewLine {
  id: string;
  post_date: string;
  value_date?: string;
  narration_description: string;
  tran_type?: string;
  chq_ref?: string;
  credit: number | null;
  debit: number | null;
  balance?: number;
  amount?: number;
  status: string;
  Hex?: string;
}

export interface TemplateMetadata {
  id: number;
  template_name: string;
  is_universal: boolean;
}

export interface ApiResponseMeta {
  fileType: string;
  decrypted: boolean;
  count: number;
  openingBalance: number;
  closingBalance: number;
  totalDebit: number;
  totalCredit: number;
  rawMatchCount: number;
  debitLineCount: number;
  creditLineCount: number;
  emptyMemoLineCount: number;
  duplicateCount: number;
  report_from_date?: string | null;
  report_to_date?: string | null;
}
