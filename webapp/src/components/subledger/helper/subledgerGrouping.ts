import type { AssetSubLedgerNode } from '../../../api/subledger';

export interface HierarchyAssetNode extends AssetSubLedgerNode {
  children?: HierarchyAssetNode[];
  vendor_name?: string | null;
}

export interface AssetCategoryGroup {
  groupKey: string;
  groupTitle: string;
  categoryType: 'ASSET' | 'INCOME' | 'EXPENSE';
  rootAssets: HierarchyAssetNode[];
  totalValuation: number;
  totalMapped: number;
  totalNodeCount: number;
}

/**
 * Normalizes category type (ASSET | INCOME | EXPENSE)
 */
export const getSubledgerType = (
  asset: any
): 'ASSET' | 'INCOME' | 'EXPENSE' => {
  if (asset.category_type)
    return String(asset.category_type).toUpperCase() as any;
  if (asset.category_detail?.category_type) {
    return String(asset.category_detail.category_type).toUpperCase() as any;
  }
  if (asset.asset_code?.startsWith('INC')) return 'INCOME';
  if (asset.asset_code?.startsWith('EXP')) return 'EXPENSE';
  return 'ASSET';
};

/**
 * Resolves the display head (e.g., "Real Estate", "Fixed Deposits", "Gold & Precious Metals")
 */
export const getAssetHeadTitle = (asset: any): string => {
  return (
    asset.linked_gl_account ||
    asset.category_display ||
    asset.category ||
    asset.subcategory ||
    'Unassigned Asset Head'
  );
};

/**
 * Groups a flat array of asset nodes into an Asset Head hierarchy with parent-child nesting
 */
export const groupAssetsByHead = (
  assetsList: AssetSubLedgerNode[]
): AssetCategoryGroup[] => {
  const groupsMap: Record<string, AssetCategoryGroup> = {};

  assetsList.forEach((asset: any) => {
    const headTitle = getAssetHeadTitle(asset);
    const headKey = headTitle.toLowerCase().replace(/[^a-z0-9]/g, '_');
    const catType = getSubledgerType(asset);

    if (!groupsMap[headKey]) {
      groupsMap[headKey] = {
        groupKey: headKey,
        groupTitle: headTitle,
        categoryType: catType,
        rootAssets: [],
        totalValuation: 0,
        totalMapped: 0,
        totalNodeCount: 0,
      };
    }

    groupsMap[headKey].totalValuation += Number(asset.current_valuation || 0);
    groupsMap[headKey].totalMapped += Number(
      asset.mapped_transaction_total || 0
    );
    groupsMap[headKey].totalNodeCount += 1;
  });

  // Assemble parent-child hierarchy within each group
  Object.keys(groupsMap).forEach((headKey) => {
    const headAssets = assetsList.filter((a: any) => {
      const key = getAssetHeadTitle(a)
        .toLowerCase()
        .replace(/[^a-z0-9]/g, '_');
      return key === headKey;
    });

    const nodeMap = new Map<string, HierarchyAssetNode>();
    headAssets.forEach((a) => {
      nodeMap.set(a.id, { ...a, children: [] });
    });

    const rootNodes: HierarchyAssetNode[] = [];

    nodeMap.forEach((node) => {
      const parentId =
        (node as any).parent_asset_id ||
        (node as any).parent_asset?.id ||
        (node as any).parent_asset;

      if (parentId && nodeMap.has(parentId)) {
        nodeMap.get(parentId)!.children!.push(node);
      } else {
        rootNodes.push(node);
      }
    });

    // Deterministic sorting by asset code
    rootNodes.sort((a, b) => a.asset_code.localeCompare(b.asset_code));
    rootNodes.forEach((parent) => {
      if (parent.children) {
        parent.children.sort((a, b) =>
          a.asset_code.localeCompare(b.asset_code)
        );
      }
    });

    groupsMap[headKey].rootAssets = rootNodes;
  });

  return Object.values(groupsMap).sort(
    (a, b) => b.totalValuation - a.totalValuation
  );
};
