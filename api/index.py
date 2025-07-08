from flask import Flask, request, jsonify
import yfinance as yf
import pandas as pd
import numpy as np
from pandas.tseries.offsets import BDay, MonthEnd

app = Flask(__name__)

# --- Global Constants for better readability and maintenance ---
# 將魔法數字定義為常數，方便未來統一修改與管理
RISK_FREE_RATE = 0
DAYS_PER_YEAR = 365.25
MONTHS_PER_YEAR = 12
EPSILON = 1e-9 # 極小值，用於防止除以零的錯誤

# Vercel 會自動處理 CORS，無需額外設定

def calculate_metrics(portfolio_history, risk_free_rate=RISK_FREE_RATE):
    """
    使用基於月報酬率的穩健方法計算績效指標。
    """
    if portfolio_history.empty or len(portfolio_history) < 2:
        return {'cagr': 0, 'mdd': 0, 'sharpe_ratio': 0, 'sortino_ratio': 0}

    # --- 基本指標 (CAGR, MDD) ---
    end_value = portfolio_history['value'].iloc[-1]
    start_value = portfolio_history['value'].iloc[0]
    
    if start_value < EPSILON:
        return {'cagr': 0, 'mdd': -1, 'sharpe_ratio': 0, 'sortino_ratio': 0}

    start_date = portfolio_history.index[0]
    end_date = portfolio_history.index[-1]
    years = (end_date - start_date).days / DAYS_PER_YEAR
    cagr = (end_value / start_value) ** (1 / years) - 1 if years > 0 else 0

    portfolio_history['peak'] = portfolio_history['value'].cummax()
    portfolio_history['drawdown'] = (portfolio_history['value'] - portfolio_history['peak']) / (portfolio_history['peak'] + EPSILON)
    mdd = portfolio_history['drawdown'].min()

    # --- 基於月報酬率計算風險比率 ---
    monthly_returns = portfolio_history['value'].resample('M').last().pct_change().dropna()

    if len(monthly_returns) < 2:
        return {'cagr': cagr, 'mdd': mdd, 'sharpe_ratio': 0, 'sortino_ratio': 0}

    # --- 夏普比率 ---
    monthly_risk_free_rate = (1 + risk_free_rate)**(1/MONTHS_PER_YEAR) - 1
    excess_returns = monthly_returns - monthly_risk_free_rate
    
    mean_excess_return = excess_returns.mean()
    std_excess_return = excess_returns.std()

    sharpe_ratio = 0.0
    if std_excess_return > EPSILON:
        sharpe_ratio = (mean_excess_return / std_excess_return) * np.sqrt(MONTHS_PER_YEAR)

    # --- 索提諾比率 ---
    downside_returns = excess_returns.copy()
    downside_returns[downside_returns > 0] = 0
    downside_std = np.sqrt((downside_returns**2).sum() / len(monthly_returns))

    sortino_ratio = 0.0
    if downside_std > EPSILON:
        sortino_ratio = (mean_excess_return / downside_std) * np.sqrt(MONTHS_PER_YEAR)
    elif mean_excess_return > 0:
        sortino_ratio = np.inf
    
    # 處理無限大或 NaN 值，確保回傳的 JSON 格式正確
    if not np.isfinite(sharpe_ratio) or np.isnan(sharpe_ratio): sharpe_ratio = 0.0
    if not np.isfinite(sortino_ratio) or np.isnan(sortino_ratio): sortino_ratio = 0.0

    return {
        'cagr': cagr, 'mdd': mdd,
        'sharpe_ratio': sharpe_ratio, 'sortino_ratio': sortino_ratio
    }


def get_rebalancing_dates(df_prices, period):
    if period == 'never': return []
    df = df_prices.copy()
    df['year'] = df.index.year
    df['month'] = df.index.month
    if period == 'annually': rebalance_dates = df.drop_duplicates(subset=['year'], keep='first').index
    elif period == 'quarterly':
        df['quarter'] = df.index.quarter
        rebalance_dates = df.drop_duplicates(subset=['year', 'quarter'], keep='first').index
    elif period == 'monthly': rebalance_dates = df.drop_duplicates(subset=['year', 'month'], keep='first').index
    else: return []
    return rebalance_dates[1:] if len(rebalance_dates) > 1 else []

def run_simulation(portfolio_config, price_data, initial_amount):
    tickers = portfolio_config['tickers']
    weights = np.array(portfolio_config['weights']) / 100.0
    rebalancing_period = portfolio_config['rebalancingPeriod']
    df_prices = price_data[tickers].copy()
    
    if df_prices.empty: return None

    portfolio_history = pd.Series(index=df_prices.index, dtype=float, name="value")
    rebalancing_dates = get_rebalancing_dates(df_prices, rebalancing_period)
    
    # 初始投資
    current_date = df_prices.index[0]
    initial_prices = df_prices.loc[current_date]
    # 優化：在分母加上 EPSILON，防止股價為0時出錯
    shares = (initial_amount * weights) / (initial_prices + EPSILON)
    portfolio_history.loc[current_date] = initial_amount
    
    # 迭代後續的每一天
    for i in range(1, len(df_prices)):
        current_date = df_prices.index[i]
        current_prices = df_prices.loc[current_date]
        
        # 步驟 1: 無論如何，都先根據現有持股計算當日價值
        current_value = (shares * current_prices).sum()
        portfolio_history.loc[current_date] = current_value
        
        # 步驟 2: 然後，判斷當天是否為再平衡日，若是，則更新持股數，供下一日使用
        if current_date in rebalancing_dates:
            shares = (current_value * weights) / (current_prices + EPSILON)
            
    portfolio_history.dropna(inplace=True)
    metrics = calculate_metrics(portfolio_history.to_frame('value'))
    
    return {
        'name': portfolio_config['name'], **metrics,
        'portfolioHistory': [{'date': date.strftime('%Y-%m-%d'), 'value': value} for date, value in portfolio_history.items()]
    }

@app.route('/api/backtest', methods=['POST'])
def backtest_handler():
    try:
        data = request.get_json()
        portfolios = data['portfolios']
        
        # 優化：更精確地處理結束日期
        start_date_str = f"{data['startYear']}-{data['startMonth']}-01"
        end_date = pd.to_datetime(f"{data['endYear']}-{data['endMonth']}-01") + MonthEnd(0)
        end_date_str = end_date.strftime('%Y-%m-%d')
        
        initial_amount = float(data['initialAmount'])
        all_tickers = sorted(list(set(ticker for p in portfolios for ticker in p['tickers'])))
        
        if not all_tickers:
            return jsonify({'error': '請至少在一個投資組合中設定一項資產。'}), 400

        df_prices_raw = yf.download(all_tickers, start=start_date_str, end=end_date_str, auto_adjust=True)['Close']
        
        if isinstance(df_prices_raw, pd.Series):
            df_prices_raw = df_prices_raw.to_frame(name=all_tickers[0])

        if df_prices_raw.isnull().all().any():
            failed_tickers = df_prices_raw.columns[df_prices_raw.isnull().all()].tolist()
            return jsonify({'error': f"無法獲取以下股票代碼的數據: {', '.join(failed_tickers)}"}), 400
        
        # 驗證與警告邏輯
        requested_start_date = pd.to_datetime(start_date_str)
        problematic_tickers = []
        for ticker in all_tickers:
            first_valid_date = df_prices_raw[ticker].first_valid_index()
            if first_valid_date is not None and first_valid_date > requested_start_date + BDay(5):
                problematic_tickers.append(f"{ticker} (從 {first_valid_date.strftime('%Y-%m-%d')} 開始)")

        warning_message = None
        if problematic_tickers:
            warning_message = f"部分資產的數據起始日晚於您的選擇。回測已自動調整至最早的共同可用日期。週期受影響的資產：{', '.join(problematic_tickers)}"
        
        df_prices_common = df_prices_raw.dropna()

        if df_prices_common.empty:
            return jsonify({'error': '在指定的時間範圍內，找不到所有股票的共同交易日。這可能是因為選擇的資產在不同時期上市。'}), 400

        results = []
        for p_config in portfolios:
            if not p_config['tickers']: continue
            sim_result = run_simulation(p_config, df_prices_common, initial_amount)
            if sim_result: results.append(sim_result)
        
        if not results:
            return jsonify({'error': '在指定的時間範圍內，沒有足夠的共同交易日來進行回測。'}), 400

        return jsonify({'data': results, 'warning': warning_message})

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': f'伺服器發生未預期的錯誤: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def index():
    return "Python backend is running."
