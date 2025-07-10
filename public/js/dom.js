// dom.js: 集中管理所有 DOM 元素的獲取

export const dom = {
    runBacktestBtn: document.getElementById('run-backtest'),
    runScanBtn: document.getElementById('run-scan-btn'),
    runScreenerBtn: document.getElementById('run-screener-btn'),
    
    // 標籤輸入框
    tagInputContainer: document.getElementById('tag-input-container'),
    tagInputField: document.getElementById('tag-input-field'),
    autocompleteSuggestions: document.getElementById('autocomplete-suggestions'),
    
    // 錯誤訊息容器
    errorContainer: document.getElementById('error-container'),
    scanErrorContainer: document.getElementById('scan-error-container'),
    screenerErrorContainer: document.getElementById('screener-error-container'),
    
    // 投資組合表格
    portfolioGrid: document.getElementById('portfolio-grid'),

    // 回測結果面板
    resultsPanel: document.getElementById('results-panel'),
    loader: document.getElementById('loader'),
    warningContainer: document.getElementById('warning-container'),
    resultsContent: document.getElementById('results-content'),
    portfolioChartCanvas: document.getElementById('portfolio-chart'),
    summaryTable: document.getElementById('summary-table'),

    // 掃描結果面板
    scanResultsPanel: document.getElementById('scan-results-panel'),
    scanLoader: document.getElementById('scan-loader'),
    scanResultsContent: document.getElementById('scan-results-content'),
    scanSummaryTable: document.getElementById('scan-summary-table'),
};
