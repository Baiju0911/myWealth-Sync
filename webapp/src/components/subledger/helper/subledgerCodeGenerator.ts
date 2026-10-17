/**
 * Utility to generate standard entity codes across subledgers.
 * Supports Asset (AST-), Income (INC-), Expense (EXP-), and Cash Float (CASH-) schemes.
 */
export const generateDynamicCode = (
  mode: string,
  vendorNameStr?: string,
  isCash: boolean = false
): string => {
  const randomSuffix = Math.floor(1000 + Math.random() * 9000);

  if (isCash) {
    const cleanVendor = vendorNameStr
      ? vendorNameStr
          .replace(/[^a-zA-Z0-9]/g, '')
          .slice(0, 4)
          .toUpperCase()
      : 'FLT';
    return `CASH-${cleanVendor || 'FLT'}-${randomSuffix}`;
  }

  const normalizedMode = mode.toUpperCase();
  const codePrefix =
    normalizedMode === 'INCOME'
      ? 'INC'
      : normalizedMode === 'EXPENSE'
        ? 'EXP'
        : 'AST';

  const cleanVendor = vendorNameStr
    ? vendorNameStr
        .replace(/[^a-zA-Z0-9]/g, '')
        .slice(0, 4)
        .toUpperCase()
    : 'GEN';

  return `${codePrefix}-${cleanVendor || 'GEN'}-${randomSuffix}`;
};
