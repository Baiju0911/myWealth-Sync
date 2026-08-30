// src/views/index.ts

// 📦 Gather and re-export all views from a single central gateway
export { default as DashboardView } from './BanksView';
export { default as CredentialsView } from './CredentialsView';
export { default as AccountsView } from './AccountsView';
export { default as MasterInstitutionsContainer } from './MasterInstitutionsContainer';
export { default as StatementIngestView } from './StatementIngestView';
export { default as StatementIngestionNode } from './StatementIngestionNode';
export { default as UniversalStatementIngestView } from './UniversalStatementIngestView';

export { default as AccountingHeaders } from './AccountingHeaders';
export { default as StagingQueueEvaluator } from './StagingQueueEvaluator';
export { UnifiedStatementPipeline } from './UnifiedStatementPipeline';

//export { default as LedgerDashboard } from './LedgerDashboard';
export { LedgerDashboard } from './LedgerDashboard';
export { SubLedgerDashboard } from './SubLedgerDashboard';
export { EmailIngestView } from './EmailIngestView';
