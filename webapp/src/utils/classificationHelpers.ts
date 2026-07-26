import type { ExtendedCluster, RemarksJSON } from '../api';

export const parseRemarks = (remarks: unknown): RemarksJSON => {
  if (!remarks) return {};
  if (typeof remarks === 'string') {
    try {
      return JSON.parse(remarks);
    } catch {
      return { display_text: remarks };
    }
  }
  return remarks as RemarksJSON;
};

export const inrFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

export const calculateSelectedMetrics = (
  clusters: ExtendedCluster[],
  selectedTxnIds: string[]
) => {
  let totalTxns = 0;
  let totalAmount = 0;

  clusters.forEach((cluster) => {
    if (cluster.items && cluster.items.length > 0) {
      cluster.items.forEach((item) => {
        if (selectedTxnIds.includes(item.id)) {
          totalTxns += 1;
          totalAmount += item.amount || 0;
        }
      });
    } else {
      const selectedInCluster = (cluster.transaction_ids || []).filter((id) =>
        selectedTxnIds.includes(id)
      );
      if (selectedInCluster.length > 0) {
        totalTxns += selectedInCluster.length;
        const ratio = selectedInCluster.length / (cluster.count || 1);
        totalAmount += (cluster.total_amount || 0) * ratio;
      }
    }
  });

  return { totalTxns, totalAmount, allTxnIds: selectedTxnIds };
};

export const filterClustersByQuery = (
  clusters: ExtendedCluster[],
  searchQuery: string
) => {
  if (!searchQuery.trim()) return clusters;
  const query = searchQuery.toLowerCase();
  return clusters.filter(
    (c) =>
      (c.pattern && c.pattern.toLowerCase().includes(query)) ||
      (c.sample_descriptions &&
        c.sample_descriptions.some((d) => d.toLowerCase().includes(query)))
  );
};
