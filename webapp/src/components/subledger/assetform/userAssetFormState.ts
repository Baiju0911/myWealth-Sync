import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  subledgerApi,
  type AssetSubLedgerNode,
  type OwnershipType,
  type AssetStatusType,
  type SubledgerTaxonomyGroup,
  type Vendor,
  type AssetCategoryType,
  type AssetSubLedgerPayload,
} from '../../../api/subledger';
import {
  CATEGORY_DYNAMIC_SCHEMAS,
  type FieldDefinition,
} from '../../ui/categorySchemaRegistry';
import { generateDynamicCode } from '../helper/subledgerCodeGenerator';
import type { MetadataRow } from './modalParts/MetadataAttributesSection';

interface UseAssetFormStateProps {
  isOpen: boolean;
  assetToEdit?: AssetSubLedgerNode | null;
  defaultSubcategory?: string | null;
  activeTab?: 'ASSET' | 'INCOME' | 'EXPENSE';
  onSuccess: () => void;
  onClose: () => void;
}

export const useAssetFormState = ({
  isOpen,
  assetToEdit,
  defaultSubcategory,
  activeTab = 'ASSET',
  onSuccess,
  onClose,
}: UseAssetFormStateProps) => {
  // Core Identifiers
  const [assetCode, setAssetCode] = useState('AST-001');
  const [name, setName] = useState('');
  const [parentAssetId, setParentAssetId] = useState<string>('');
  const [allAssets, setAllAssets] = useState<AssetSubLedgerNode[]>([]);

  // Financials & Status
  const [acquisitionDate, setAcquisitionDate] = useState<string>(
    new Date().toISOString().split('T')[0]
  );
  const [acquisitionCost, setAcquisitionCost] = useState<number | string>('');
  const [currentValuation, setCurrentValuation] = useState<number | string>('');
  const [acquisitionFundingSource, setAcquisitionFundingSource] =
    useState<string>('BANK_STAGING');
  const [ownershipType] = useState<OwnershipType>('INDIVIDUAL');
  const [status, setStatus] = useState<AssetStatusType>('ACTIVE');
  const [isMatured, setIsMatured] = useState<boolean>(false);

  // Taxonomy & Schemas
  const [linkedGlAccount, setLinkedGlAccount] = useState<string>('');
  const [selectedCategoryCode, setSelectedCategoryCode] = useState<string>('');
  const [taxonomyTree, setTaxonomyTree] = useState<SubledgerTaxonomyGroup[]>(
    []
  );
  const [metadataEntries, setMetadataEntries] = useState<MetadataRow[]>([]);
  const [categoryChoices, setCategoryChoices] = useState<
    { code: string; label: string }[]
  >([]);

  // Vendors
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [selectedVendorId, setSelectedVendorId] = useState<string>('');

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasHydratedRef = useRef(false);

  const isCashFormMode = useMemo(() => {
    const cat = (selectedCategoryCode || '').toUpperCase();
    const gl = (linkedGlAccount || '').toLowerCase();
    return (
      cat === 'PETTY_CASH' ||
      cat === 'CASH_FLOAT' ||
      gl.includes('cash') ||
      gl.includes('float')
    );
  }, [selectedCategoryCode, linkedGlAccount]);

  const currentMode = useMemo(() => {
    if (assetToEdit) {
      const editNode = assetToEdit as Record<string, any>;
      const typeStr = String(
        assetToEdit.asset_category_detail?.default_taxonomy_category ||
          editNode.category_type ||
          editNode.category_detail?.category_type ||
          ''
      ).toUpperCase();

      if (
        typeStr.includes('INCOME') ||
        assetToEdit.asset_code?.startsWith('INC-')
      )
        return 'INCOME';
      if (
        typeStr.includes('EXPENSE') ||
        assetToEdit.asset_code?.startsWith('EXP-')
      )
        return 'EXPENSE';
      if (
        typeStr.includes('ASSET') ||
        assetToEdit.asset_code?.startsWith('AST-')
      )
        return 'ASSET';
    }
    return activeTab || 'ASSET';
  }, [assetToEdit, activeTab]);

  const masterAssetsOnly = useMemo(() => {
    return allAssets.filter((ast: any) => {
      if (assetToEdit && String(ast.id) === String(assetToEdit.id))
        return false;
      const catType = String(
        ast.category_type || ast.category_detail?.category_type || 'ASSET'
      ).toUpperCase();
      const isIncOrExp =
        catType === 'INCOME' ||
        catType === 'EXPENSE' ||
        String(ast.asset_code || '').startsWith('INC-') ||
        String(ast.asset_code || '').startsWith('EXP-');
      const parentId =
        ast.parent_asset_id || ast.parent_asset?.id || ast.parent_asset;
      return catType === 'ASSET' && !isIncOrExp && !parentId;
    });
  }, [allAssets, assetToEdit]);

  const filteredTaxonomySubcategories = useMemo(() => {
    const targetGroup = String(currentMode).trim().toLowerCase();
    return taxonomyTree
      .filter((group) => {
        const catName = group.category.toLowerCase();
        if (targetGroup === 'income') return catName.includes('income');
        if (targetGroup === 'expense') return catName.includes('expense');
        return catName.includes('asset');
      })
      .flatMap((group) =>
        group.subcategories.map((sub: any) => ({
          id: typeof sub === 'object' ? sub.id : sub,
          subcategory: typeof sub === 'object' ? sub.subcategory : sub,
          category_code:
            typeof sub === 'object'
              ? sub.category_code || sub.code || sub.asset_category_code || null
              : null,
          group: group.category,
        }))
      );
  }, [taxonomyTree, currentMode]);

  const loadMergedCategorySchema = useCallback(async (catCode: string) => {
    const localSchema = CATEGORY_DYNAMIC_SCHEMAS[catCode] || [];
    const keySet = new Set<string>();
    const rows: MetadataRow[] = [];

    localSchema.forEach((field: FieldDefinition) => {
      rows.push({ key: field.key, value: '' });
      keySet.add(field.key);
    });

    try {
      const dbKeys = await subledgerApi.getCategorySchemaKeys(catCode);
      dbKeys.forEach((dbKey: string) => {
        if (!keySet.has(dbKey)) {
          rows.push({ key: dbKey, value: '' });
          keySet.add(dbKey);
        }
      });
    } catch (err) {
      console.error('Failed to fetch category schema keys:', err);
    }

    setMetadataEntries(rows.length > 0 ? rows : [{ key: '', value: '' }]);
  }, []);

  const handleGlTaxonomyChange = useCallback(
    async (newGlSubcategory: string) => {
      setLinkedGlAccount(newGlSubcategory);
      if (!newGlSubcategory) return;

      const isCash =
        newGlSubcategory.toLowerCase().includes('cash') ||
        newGlSubcategory.toLowerCase().includes('float');

      if (!assetToEdit) {
        setAssetCode(generateDynamicCode(currentMode, undefined, isCash));
      }

      const matchedItem = filteredTaxonomySubcategories.find(
        (item) => item.subcategory === newGlSubcategory
      );

      const code =
        matchedItem?.category_code ||
        newGlSubcategory
          .toUpperCase()
          .replace(/^(INCOME|EXPENSE|ASSET)\s*-\s*/, '')
          .replace(/[^A-Z0-9]/g, '_')
          .replace(/_+/g, '_');

      setSelectedCategoryCode(code);
      await loadMergedCategorySchema(code);
    },
    [
      assetToEdit,
      currentMode,
      filteredTaxonomySubcategories,
      loadMergedCategorySchema,
    ]
  );

  useEffect(() => {
    if (!isOpen) {
      hasHydratedRef.current = false;
      return;
    }
    if (hasHydratedRef.current) return;
    hasHydratedRef.current = true;

    Promise.all([
      subledgerApi.getVendors().catch(() => []),
      subledgerApi.getAssets().catch(() => []),
      subledgerApi.getTaxonomyNodesForSubledger().catch(() => []),
      subledgerApi.getCategoryChoices().catch(() => []),
    ]).then(async ([vList, aList, treeRes, choicesRes]) => {
      setVendors(vList);
      setAllAssets(aList);
      setTaxonomyTree(treeRes);
      setCategoryChoices(choicesRes);

      if (assetToEdit) {
        setAssetCode(assetToEdit.asset_code);
        setName(assetToEdit.name);
        setAcquisitionDate(
          assetToEdit.acquisition_date
            ? assetToEdit.acquisition_date.split('T')[0]
            : new Date().toISOString().split('T')[0]
        );
        setAcquisitionCost(assetToEdit.acquisition_cost);
        setCurrentValuation(assetToEdit.current_valuation);
        setAcquisitionFundingSource(
          (assetToEdit as any).acquisition_funding_source || 'BANK_STAGING'
        );
        setStatus((assetToEdit.status as AssetStatusType) || 'ACTIVE');
        setIsMatured(
          assetToEdit.status === 'MATURED' ||
            assetToEdit.status === 'LIQUIDATED'
        );
        setLinkedGlAccount(String(assetToEdit.linked_gl_account || ''));
        setSelectedCategoryCode(assetToEdit.category || '');
        setSelectedVendorId(
          assetToEdit.vendor ? String(assetToEdit.vendor) : ''
        );
        setParentAssetId(
          (assetToEdit as any).parent_asset
            ? String((assetToEdit as any).parent_asset)
            : ''
        );

        if (
          assetToEdit.metadata_payload &&
          Object.keys(assetToEdit.metadata_payload).length > 0
        ) {
          setMetadataEntries(
            Object.entries(assetToEdit.metadata_payload).map(([k, v]) => ({
              key: k,
              value: String(v ?? ''),
            }))
          );
        } else {
          await loadMergedCategorySchema(assetToEdit.category || 'REAL_ESTATE');
        }
      } else {
        setName('');
        setAcquisitionDate(new Date().toISOString().split('T')[0]);
        setAcquisitionCost('');
        setCurrentValuation('');
        setAcquisitionFundingSource('BANK_STAGING');
        setStatus('ACTIVE');
        setIsMatured(false);
        setSelectedVendorId('');
        setParentAssetId('');
        setSelectedCategoryCode('');

        const isCash =
          (defaultSubcategory || '').toLowerCase().includes('cash') ||
          (defaultSubcategory || '').toLowerCase().includes('float');
        setAssetCode(generateDynamicCode(currentMode, undefined, isCash));

        const initialGl = defaultSubcategory || '';
        if (initialGl) handleGlTaxonomyChange(initialGl);
      }
    });
  }, [
    isOpen,
    assetToEdit,
    defaultSubcategory,
    currentMode,
    handleGlTaxonomyChange,
    loadMergedCategorySchema,
  ]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    const metadataPayload: Record<string, any> = {};
    metadataEntries.forEach((row) => {
      if (row.key.trim() && row.value.trim() !== '') {
        metadataPayload[row.key.trim()] = row.value.trim();
      }
    });

    const matchedChoice = categoryChoices.find(
      (c) =>
        c.code === selectedCategoryCode ||
        c.label.toLowerCase().includes(linkedGlAccount.toLowerCase())
    );

    const resolvedCategory = (matchedChoice?.code ||
      (currentMode === 'INCOME'
        ? 'RENTAL_STREAM'
        : currentMode === 'EXPENSE'
          ? 'VENDOR_MERCHANT'
          : 'REAL_ESTATE')) as AssetCategoryType;

    const payload: AssetSubLedgerPayload & {
      acquisition_funding_source?: string;
    } = {
      asset_code: assetCode.trim(),
      name: name.trim(),
      category: resolvedCategory,
      vendor: selectedVendorId.trim() || null,
      parent_asset: parentAssetId.trim() || null,
      acquisition_date: acquisitionDate,
      acquisition_cost: Number(acquisitionCost) || 0,
      current_valuation: isMatured ? 0 : Number(currentValuation) || 0,
      acquisition_funding_source: acquisitionFundingSource,
      ownership_type: ownershipType,
      ownership_share_pct: '100.00',
      status: isMatured ? 'MATURED' : status,
      linked_gl_account: linkedGlAccount.trim() || null,
      metadata_payload: metadataPayload,
    };

    try {
      if (assetToEdit) {
        await subledgerApi.updateAsset(assetToEdit.id, payload);
      } else {
        await subledgerApi.createAsset(payload);
      }
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(
        `Save Failed: ${JSON.stringify(err.response?.data || err.message)}`
      );
    } finally {
      setSaving(false);
    }
  };

  return {
    state: {
      assetCode,
      name,
      parentAssetId,
      acquisitionDate,
      acquisitionCost,
      currentValuation,
      acquisitionFundingSource,
      isMatured,
      linkedGlAccount,
      metadataEntries,
      vendors,
      selectedVendorId,
      saving,
      error,
      currentMode,
      isCashFormMode,
      masterAssetsOnly,
      filteredTaxonomySubcategories,
    },
    actions: {
      setAssetCode,
      setName,
      setParentAssetId,
      setAcquisitionDate,
      setAcquisitionCost,
      setCurrentValuation,
      setAcquisitionFundingSource,
      setTaxonomyTree,
      setSelectedVendorId,
      setVendors,
      setMetadataEntries,
      handleGlTaxonomyChange,
      handleSubmit,
    },
  };
};
