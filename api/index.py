from flask import Flask, request, jsonify
import yfinance as yf
import pandas as pd
import numpy as np
from pandas.tseries.offsets import BDay, MonthEnd
import sys
from io import StringIO

app = Flask(__name__)

# --- 全域常數 ---
RISK_FREE_RATE = 0
TRADING_DAYS_PER_YEAR = 252
DAYS_PER_YEAR = 365.25
EPSILON = 1e-9

# --- 核心計算函式 ---

def calculate_metrics(portfolio_history, benchmark_history=None, risk_free_rate=RISK_FREE_RATE):
    """
    [ENHANCED] 計算績效指標，新增年化波動率。
    """
    if portfolio_history.empty or len(portfolio_history) < 2:
        return {'cagr': 0, 'mdd': 0, 'volatility': 0, 'sharpe_ratio': 0, 'sortino_ratio': 0, 'beta': None, 'alpha': None}

    # --- 基本指標 (CAGR, MDD) ---
    end_value = portfolio_history['value'].iloc[-1]
    start_value = portfolio_history['value'].iloc[0]
    
    if start_value < EPSILON:
        return {'cagr': 0, 'mdd': -1, 'volatility': 0, 'sharpe_ratio': 0, 'sortino_ratio': 0, 'beta': None, 'alpha': None}

    start_date = portfolio_history.index[0]
    end_date = portfolio_history.index[-1]
    years = (end_date - start_date).days / DAYS_PER_YEAR
    cagr = (end_value / start_value) ** (1 / years) - 1 if years > 0 else 0

    portfolio_history['peak'] = portfolio_history['value'].cummax()
    portfolio_history['drawdown'] = (portfolio_history['value'] - portfolio_history['peak']) / (portfolio_history['peak'] + EPSILON)
    mdd = portfolio_history['drawdown'].min()

    # --- 風險比率計算 ---
    daily_returns = portfolio_history['value'].pct_change().dropna()

    if len(daily_returns) < 2:
        return {'cagr': cagr, 'mdd': mdd, 'volatility': 0, 'sharpe_ratio': 0, 'sortino_ratio': 0, 'beta': None, 'alpha': None}

    # --- 新增：年化波動率 ---
    annual_std = daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)

    annualized_excess_return = cagr - risk_free_rate
    sharpe_ratio = annualized_excess_return / (annual_std + EPSILON)

    daily_risk_free_rate = (1 + risk_free_rate)**(1/TRADING_DAYS_PER_YEAR) - 1
    downside_returns = daily_returns - daily_risk_free_rate
    downside_returns[downside_returns > 0] = 0
    downside_std = np.sqrt((downside_returns**2).mean()) * np.sqrt(TRADING_DAYS_PER_YEAR)
    
    sortino_ratio = 0.0
    if downside_std > EPSILON:
        sortino_ratio = annualized_excess_return / downside_std

    # --- Beta 和 Alpha 計算 ---
    beta, alpha = None, None
    if benchmark_history is not None and not benchmark_history.empty:
        benchmark_returns = benchmark_history['value'].pct_change().dropna()
        aligned_returns = pd.concat([daily_returns, benchmark_returns], axis=1, join='inner')
        aligned_returns.columns = ['portfolio', 'benchmark']
        
        if len(aligned_returns) > 1:
            covariance_matrix = aligned_returns.cov()
            covariance = covariance_matrix.iloc[0, 1]
            benchmark_variance = covariance_matrix.iloc[1, 1]
            
            if benchmark_variance > EPSILON:
                beta = covariance / benchmark_variance
                
                bench_end_value = benchmark_history['value'].iloc[-1]
                bench_start_value = benchmark_history['value'].iloc[0]
                bench_cagr = (bench_end_value / bench_start_value) ** (1 / years) - 1 if years > 0 else 0
                
                expected_return = risk_free_rate + beta * (bench_cagr - risk_free_rate)
                alpha = cagr - expected_return

    # 最終格式化
    if not np.isfinite(sharpe_ratio) or np.isnan(sharpe_ratio): sharpe_ratio = 0.0
    if not np.isfinite(sortino_ratio) or np.isnan(sortino_ratio): sortino_ratio = 0.0
    if beta is not None and (not np.isfinite(beta) or np.isnan(beta)): beta = None
    if alpha is not None and (not np.isfinite(alpha) or np.isnan(alpha)): alpha = None

    return {'cagr': cagr, 'mdd': mdd, 'volatility': annual_std, 'sharpe_ratio': sharpe_ratio, 'sortino_ratio': sortino_ratio, 'beta': beta, 'alpha': alpha}


def run_simulation(portfolio_config, price_data, initial_amount, benchmark_history=None):
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
    metrics = calculate_metrics(portfolio_history.to_frame('value'), benchmark_history)
    
    return {'name': portfolio_config['name'], **metrics, 'portfolioHistory': [{'date': date.strftime('%Y-%m-%d'), 'value': value} for date, value in portfolio_history.items()]}

# --- 輔助函式 ---
def get_rebalancing_dates(df_prices, period):
    if period == 'never': return []
    df = df_prices.copy(); df['year'] = df.index.year; df['month'] = df.index.month
    if period == 'annually': rebalance_dates = df.drop_duplicates(subset=['year'], keep='first').index
    elif period == 'quarterly': df['quarter'] = df.index.quarter; rebalance_dates = df.drop_duplicates(subset=['year', 'quarter'], keep='first').index
    elif period == 'monthly': rebalance_dates = df.drop_duplicates(subset=['year', 'month'], keep='first').index
    else: return []
    return rebalance_dates[1:] if len(rebalance_dates) > 1 else []

def validate_data_completeness(df_prices_raw, all_tickers, requested_start_date):
    problematic_tickers = []
    for ticker in all_tickers:
        if ticker in df_prices_raw.columns:
            first_valid_date = df_prices_raw[ticker].first_valid_index()
            if first_valid_date is not None and first_valid_date > requested_start_date + BDay(5):
                problematic_tickers.append({'ticker': ticker, 'start_date': first_valid_date.strftime('%Y-%m-%d')})
    return problematic_tickers

def download_data_silently(tickers, start_date, end_date):
    old_stdout = sys.stdout; sys.stdout = StringIO()
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
        
        all_tickers = set(ticker for p in data['portfolios'] for ticker in p['tickers'])
        benchmark_ticker = data.get('benchmark')
        if benchmark_ticker:
            all_tickers.add(benchmark_ticker)
        
        all_tickers = sorted(list(all_tickers))
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
        
        initial_amount = float(data['initialAmount'])
        benchmark_result = None
        benchmark_history = None
        if benchmark_ticker and benchmark_ticker in df_prices_common.columns:
            benchmark_config = {'name': benchmark_ticker, 'tickers': [benchmark_ticker], 'weights': [100], 'rebalancingPeriod': 'never'}
            benchmark_result = run_simulation(benchmark_config, df_prices_common, initial_amount)
            if benchmark_result:
                benchmark_history = pd.DataFrame(benchmark_result['portfolioHistory']).set_index('date')
                benchmark_history.index = pd.to_datetime(benchmark_history.index)

        results = [res for p_config in data['portfolios'] if p_config['tickers'] and (res := run_simulation(p_config, df_prices_common, initial_amount, benchmark_history))]
        if not results: return jsonify({'error': '沒有足夠的共同交易日來進行回測。'}), 400
        
        if benchmark_result:
            benchmark_result['beta'] = 1.00
            benchmark_result['alpha'] = 0.00
            temp_metrics = calculate_metrics(benchmark_history)
            benchmark_result.update(temp_metrics)

        return jsonify({'data': results, 'benchmark': benchmark_result, 'warning': warning_message})
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
        
        available_tickers = df_prices_raw.columns.tolist() if hasattr(df_prices_raw, 'columns') else [df_prices_raw.name]

        for ticker in tickers:
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
