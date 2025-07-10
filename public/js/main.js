// main.js: 應用程式的主入口點

import { state } from './state.js';
import { dom } from './dom.js';
import * as ui from './ui.js';
import * as api from './api.js';
import * as handlers from './handlers.js';

function attachEventListeners() {
    // --- 主要功能按鈕 ---
    dom.runBacktestBtn.addEventListener('click', handlers.handleRunBacktest);
    dom.runScanBtn.addEventListener('click', handlers.handleRunScan);
    dom.runScreenerBtn.addEventListener('click', handlers.handleRunScreener);

    // --- 投資組合表格 ---
    const portfolioGrid = dom.portfolioGrid;
    
    // 按鈕（新增/刪除等會導致完整重繪的操作）
    document.getElementById('add-asset-btn').addEventListener('click', () => {
        state.assets.push({ ticker: '' });
        const newWeightRow = {};
        state.portfolios.forEach(p => newWeightRow[p.name] = 0);
        state.weights.push(newWeightRow);
        ui.renderGrid();
    });
    document.getElementById('add-portfolio-btn').addEventListener('click', () => {
        if (state.portfolios.length >= 5) {
            alert('最多只能比較 5 組投資組合。');
            return;
        }
        const newName = `投組 ${state.portfolios.length + 1}`;
        state.portfolios.push({ name: newName });
        state.weights.forEach(weightRow => { weightRow[newName] = 0; });
        ui.renderGrid();
    });

    // 使用事件委派處理表格內的互動
    portfolioGrid.addEventListener('input', (e) => {
        const target = e.target;
        if (target.classList.contains('weight-input')) {
            const assetIndex = target.dataset.assetIndex;
            const portfolioName = target.dataset.portfolioName;
            state.weights[assetIndex][portfolioName] = parseFloat(target.value) || 0;
            ui.updateTotals(); // 只更新總計，不重繪表格
        }
        if (target.classList.contains('ticker-input')) {
            state.assets[target.dataset.assetIndex].ticker = target.value.toUpperCase();
        }
    });

    portfolioGrid.addEventListener('change', (e) => {
        const target = e.target;
        if (target.classList.contains('portfolio-name-input')) {
            const oldName = target.dataset.oldName;
            const newName = target.value;
            if (oldName === newName) return;
            const portfolioToUpdate = state.portfolios.find(p => p.name === oldName);
            if (portfolioToUpdate) portfolioToUpdate.name = newName;
            state.weights.forEach(weightRow => {
                if (weightRow[oldName] !== undefined) {
                    weightRow[newName] = weightRow[oldName];
                    delete weightRow[oldName];
                }
            });
            ui.renderGrid(); // 更改名稱需要完整重繪
        }
    });

    portfolioGrid.addEventListener('click', (e) => {
        const removeAssetBtn = e.target.closest('.remove-asset-btn');
        if (removeAssetBtn) {
            const assetIndex = parseInt(removeAssetBtn.dataset.assetIndex);
            state.assets.splice(assetIndex, 1);
            state.weights.splice(assetIndex, 1);
            ui.renderGrid();
        }
        const clearPortfolioBtn = e.target.closest('.clear-portfolio-btn');
        if (clearPortfolioBtn) {
            const portfolioToClear = clearPortfolioBtn.dataset.portfolioName;
            state.weights.forEach(weightRow => {
                if (weightRow[portfolioToClear] !== undefined) weightRow[portfolioToClear] = 0;
            });
            ui.renderGrid();
        }
        const clearTickersBtn = e.target.closest('.clear-tickers-btn');
        if(clearTickersBtn) {
            state.assets.forEach(asset => { asset.ticker = ''; });
            ui.renderGrid();
        }
    });

    // --- 智慧型標籤輸入框 ---
    dom.tagInputField.addEventListener('keyup', handlers.handleTagInput);
    dom.tagInputField.addEventListener('keydown', handlers.handleTagInputKeydown);
    dom.tagInputContainer.addEventListener('click', () => dom.tagInputField.focus());
    dom.autocompleteSuggestions.addEventListener('click', (e) => {
        if (e.target.classList.contains('suggestion-item')) {
            handlers.addTag(e.target.textContent);
        }
    });
    document.addEventListener('click', (e) => {
        if (!dom.tagInputContainer.contains(e.target)) {
            dom.autocompleteSuggestions.classList.add('hidden');
        }
    });

    // --- 掃描結果表格排序 ---
    dom.scanSummaryTable.addEventListener('click', (e) => {
        const th = e.target.closest('.sortable');
        if (th) {
            handlers.handleSortScanTable(th.dataset.sortKey);
        }
    });
}

async function initialize() {
    ui.populateDateSelectors('startYear', 'startMonth', 'endYear', 'endMonth');
    ui.populateDateSelectors('scan-startYear', 'scan-startMonth', 'scan-endYear', 'scan-endMonth');
    ui.renderGrid();
    attachEventListeners();
    state.allAvailableTickers = await api.fetchAvailableTickers();
}

// 啟動應用程式
initialize();
