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
