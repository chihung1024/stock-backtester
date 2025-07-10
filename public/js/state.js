// state.js: 集中管理應用的所有狀態

// 使用一個物件來包裝所有狀態，確保在模組間傳遞時能正確地修改
export const state = {
    assets: [{ ticker: 'QQQ' }, { ticker: 'SOXX' }],
    portfolios: [{ name: '投組 1' }, { name: '投組 2' }],
    weights: [
        { '投組 1': 100, '投組 2': 0 },
        { '投組 1': 0, '投組 2': 100 }
    ],
    chartInstance: null,
    scanResultsData: [],
    scanSortState: { key: 'cagr', direction: 'desc' },
    allAvailableTickers: [],
    selectedScanTickers: [],
    activeSuggestionIndex: -1,
    COLORS: ['#4f46e5', '#db2777', '#16a34a', '#d97706', '#0891b2']
};

// 為了方便，也直接導出個別狀態的 getter 和 setter
export function setChartInstance(instance) {
    state.chartInstance = instance;
}
