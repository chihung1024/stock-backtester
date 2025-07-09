from flask import Flask, request, jsonify
import yfinance as yf
import pandas as pd
import numpy as np
from pandas.tseries.offsets import BDay, MonthEnd
import sys
from io import StringIO

app = Flask(__name__)

# --- 全域常數，提升可讀性與可維護性 ---
RISK_FREE_RATE = 0.02
DAYS_PER_YEAR = 365.25
MONTHS_PER_YEAR = 12
EPSILON = 1e-9 # 極小值，用於防止除以零的錯誤

# --- 核心計算函式 ---

def calculate_metrics(portfolio_history, risk_free_rate=RISK_FREE_RATE):
    """使用基於月報酬率的穩健方法計算績效指標。"""
    if portfolio_history.empty or len(portfolio_history) < 2:
        return {'cagr': 0, 'mdd': 0, 'sharpe_ratio': 0, 'sortino_ratio': 0}

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

    monthly_returns = portfolio_history['value'].resample('M').last().pct_change().dropna()

    if len(monthly_returns) < 2:
        return {'cagr': cagr, 'mdd': mdd, 'sharpe_ratio': 0, 'sortino_ratio': 0}

    monthly_risk_free_rate = (1 + risk_free_rate)**(1/MONTHS_PER_YEAR) - 1
    excess_returns = monthly_returns - monthly_risk_free_rate
    mean_excess_return = excess_returns.mean()
    std_excess_return = excess_returns.std()

    sharpe_ratio = (mean_excess_return / (std_excess_return + EPSILON)) * np.sqrt(MONTHS_PER_YEAR)

    downside_returns = excess_returns.copy()
    downside_returns[downside_returns > 0] = 0
    downside_std = np.sqrt((downside_returns**2).sum() / len(monthly_returns))

    sortino_ratio = 0.0
    if downside_std > EPSILON:
        sortino_ratio = (mean_excess_return / downside_std) * np.sqrt(MONTHS_PER_YEAR)
    elif mean_excess_return > 0:
        sortino_ratio = np.inf
    
    if not np.isfinite(sharpe_ratio) or np.isnan(sharpe_ratio): sharpe_ratio = 0.0
    if not np.isfinite(sortino_ratio) or np.isnan(sortino_ratio): sortino_ratio = 0.0

    return {'cagr': cagr, 'mdd': mdd, 'sharpe_ratio': sharpe_ratio, 'sortino_ratio': sortino_ratio}

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
    current_date = df_prices.index[0]
    initial_prices = df_prices.loc[current_date]
    shares = (initial_amount * weights) / (initial_prices + EPSILON)
    portfolio_history.loc[current_date] = initial_amount
    for i in range(1, len(df_prices)):
        current_date = df_prices.index[i]
        current_prices = df_prices.loc[current_date]
        current_value = (shares * current_prices).sum()
        portfolio_history.loc[current_date] = current_value
        if current_date in rebalancing_dates:
            shares = (current_value * weights) / (current_prices + EPSILON)
    portfolio_history.dropna(inplace=True)
    metrics = calculate_metrics(portfolio_history.to_frame('value'))
    return {'name': portfolio_config['name'], **metrics, 'portfolioHistory': [{'date': date.strftime('%Y-%m-%d'), 'value': value} for date, value in portfolio_history.items()]}

# --- 輔助函式 ---

def validate_data_completeness(df_prices_raw, all_tickers, requested_start_date):
    """
    檢查是否有任何股票的數據起始日顯著晚於請求的起始日。
    回傳有問題的股票列表，用於產生警告或備註。
    """
    problematic_tickers = []
    for ticker in all_tickers:
        # 確保 ticker 存在於 DataFrame 中
        if ticker in df_prices_raw.columns:
            first_valid_date = df_prices_raw[ticker].first_valid_index()
            if first_valid_date is not None and first_valid_date > requested_start_date + BDay(5):
                problematic_tickers.append({'ticker': ticker, 'start_date': first_valid_date.strftime('%Y-%m-%d')})
    return problematic_tickers

def download_data_silently(tickers, start_date, end_date):
    """
    下載數據並抑制 yfinance 的輸出。
    """
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        data = yf.download(tickers, start=start_date, end=end_date, auto_adjust=True, progress=False)['Close']
    finally:
        sys.stdout = old_stdout
    return data

# --- API 端點 ---

@app.route('/api/backtest', methods=['POST'])
def backtest_handler():
    try:
        data = request.get_json()
        start_date_str = f"{data['startYear']}-{data['startMonth']}-01"
        end_date = pd.to_datetime(f"{data['endYear']}-{data['endMonth']}-01") + MonthEnd(0)
        end_date_str = end_date.strftime('%Y-%m-%d')
        all_tickers = sorted(list(set(ticker for p in data['portfolios'] for ticker in p['tickers'])))
        if not all_tickers: return jsonify({'error': '請至少在一個投資組合中設定一項資產。'}), 400
        
        df_prices_raw = download_data_silently(all_tickers, start_date_str, end_date_str)
        if isinstance(df_prices_raw, pd.Series): df_prices_raw = df_prices_raw.to_frame(name=all_tickers[0])
        if df_prices_raw.isnull().all().any():
            failed_tickers = df_prices_raw.columns[df_prices_raw.isnull().all()].tolist()
            return jsonify({'error': f"無法獲取以下股票代碼的數據: {', '.join(failed_tickers)}"}), 400
        
        problematic_tickers_info = validate_data_completeness(df_prices_raw, all_tickers, pd.to_datetime(start_date_str))
        warning_message = None
        if problematic_tickers_info:
            tickers_str = ", ".join([f"{item['ticker']} (從 {item['start_date']} 開始)" for item in problematic_tickers_info])
            warning_message = f"部分資產的數據起始日晚於您的選擇。回測已自動調整至最早的共同可用日期。週期受影響的資產：{tickers_str}"
        
        df_prices_common = df_prices_raw.dropna()
        if df_prices_common.empty: return jsonify({'error': '在指定的時間範圍內，找不到所有股票的共同交易日。'}), 400
        
        results = [res for p_config in data['portfolios'] if p_config['tickers'] and (res := run_simulation(p_config, df_prices_common, float(data['initialAmount'])))]
        if not results: return jsonify({'error': '沒有足夠的共同交易日來進行回測。'}), 400
        
        return jsonify({'data': results, 'warning': warning_message})
    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({'error': f'伺服器發生未預期的錯誤: {str(e)}'}), 500

@app.route('/api/scan', methods=['POST'])
def scan_handler():
    try:
        data = request.get_json()
        tickers = data['tickers']
        start_date_str = f"{data['startYear']}-{data['startMonth']}-01"
        end_date = pd.to_datetime(f"{data['endYear']}-{data['endMonth']}-01") + MonthEnd(0)
        end_date_str = end_date.strftime('%Y-%m-%d')

        if not tickers:
            return jsonify({'error': '股票代碼列表不可為空。'}), 400

        df_prices_raw = download_data_silently(tickers, start_date_str, end_date_str)
        if isinstance(df_prices_raw, pd.Series):
            df_prices_raw = df_prices_raw.to_frame(name=tickers[0])

        results = []
        requested_start_date = pd.to_datetime(start_date_str)
        
        # 獲取實際下載到的股票代碼列表
        available_tickers = df_prices_raw.columns.tolist()

        for ticker in tickers:
            # 如果請求的 ticker 不在下載到的資料中，直接標記為錯誤
            if ticker not in available_tickers:
                results.append({'ticker': ticker, 'error': '找不到數據'})
                continue

            stock_prices = df_prices_raw[ticker].dropna()
            if stock_prices.empty:
                results.append({'ticker': ticker, 'error': '指定範圍內無數據'})
                continue

            note = None
            problematic_info = validate_data_completeness(df_prices_raw, [ticker], requested_start_date)
            if problematic_info:
                note = f"(從 {problematic_info[0]['start_date']} 開始)"

            history_df = stock_prices.to_frame(name='value')
            metrics = calculate_metrics(history_df)
            results.append({'ticker': ticker, **metrics, 'note': note})

        return jsonify(results)

    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({'error': f'伺服器發生未預期的錯誤: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def index():
    return "Python backend is running."
