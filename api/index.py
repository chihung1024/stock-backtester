from flask import Flask, request, jsonify
import yfinance as yf
import pandas as pd
import numpy as np
from pandas.tseries.offsets import BDay # Import Business Day

app = Flask(__name__)

# Vercel 會自動處理 CORS，無需額外設定

def calculate_metrics(portfolio_history, risk_free_rate=0.02):
    """
    [FIXED] Calculates performance metrics using a more robust method based on monthly returns.
    """
    epsilon = 1e-9
    if portfolio_history.empty or len(portfolio_history) < 2:
        return {'cagr': 0, 'mdd': 0, 'sharpe_ratio': 0, 'sortino_ratio': 0}

    # --- Basic metrics (CAGR, MDD) ---
    end_value = portfolio_history['value'].iloc[-1]
    start_value = portfolio_history['value'].iloc[0]
    
    # Ensure start_value is not zero to avoid division errors
    if start_value < epsilon:
        return {'cagr': 0, 'mdd': -1, 'sharpe_ratio': 0, 'sortino_ratio': 0}

    start_date = portfolio_history.index[0]
    end_date = portfolio_history.index[-1]
    years = (end_date - start_date).days / 365.25
    cagr = (end_value / start_value) ** (1 / years) - 1 if years > 0 else 0

    portfolio_history['peak'] = portfolio_history['value'].cummax()
    # Add epsilon to prevent division by zero if peak is ever zero
    portfolio_history['drawdown'] = (portfolio_history['value'] - portfolio_history['peak']) / (portfolio_history['peak'] + epsilon)
    mdd = portfolio_history['drawdown'].min()

    # --- Ratio Calculation based on Monthly Returns ---
    # Resample to get the last value of each month, then calculate percentage change
    monthly_returns = portfolio_history['value'].resample('M').last().pct_change().dropna()

    # Need at least 2 months of returns to calculate standard deviation
    if len(monthly_returns) < 2:
        return {'cagr': cagr, 'mdd': mdd, 'sharpe_ratio': 0, 'sortino_ratio': 0}

    # --- Sharpe Ratio ---
    monthly_risk_free_rate = (1 + risk_free_rate)**(1/12) - 1
    excess_returns = monthly_returns - monthly_risk_free_rate
    
    mean_excess_return = excess_returns.mean()
    std_excess_return = excess_returns.std()

    sharpe_ratio = 0.0
    if std_excess_return > epsilon:
        # Annualize the Sharpe Ratio (from monthly data)
        sharpe_ratio = (mean_excess_return / std_excess_return) * np.sqrt(12)

    # --- Sortino Ratio ---
    # Create a series of downside returns, with non-downside returns set to 0
    downside_returns = excess_returns.copy()
    downside_returns[downside_returns > 0] = 0
    
    # Calculate downside deviation from this series
    downside_std = np.sqrt((downside_returns**2).sum() / len(monthly_returns))

    sortino_ratio = 0.0
    if downside_std > epsilon:
        # Annualize from monthly data
        sortino_ratio = (mean_excess_return / downside_std) * np.sqrt(12)
    elif mean_excess_return > 0:
        # If there's no downside risk and returns are positive, ratio is infinite
        sortino_ratio = np.inf
    
    # Handle potential infinity/nan values for JSON compatibility
    if not np.isfinite(sharpe_ratio) or np.isnan(sharpe_ratio): sharpe_ratio = 0.0
    if not np.isfinite(sortino_ratio) or np.isnan(sortino_ratio): sortino_ratio = 0.0

    return {
        'cagr': cagr,
        'mdd': mdd,
        'sharpe_ratio': sharpe_ratio,
        'sortino_ratio': sortino_ratio
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
    # Exclude the very first day from rebalancing dates
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
    shares = (initial_amount * weights) / df_prices.loc[current_date]
    portfolio_history.loc[current_date] = initial_amount
    
    for i in range(1, len(df_prices)):
        current_date = df_prices.index[i]
        # Use previous day's price for calculation to avoid lookahead bias on rebalance day
        prev_date = df_prices.index[i-1]
        
        if current_date in rebalancing_dates:
            current_value = (shares * df_prices.loc[prev_date]).sum()
            shares = (current_value * weights) / df_prices.loc[current_date]
            portfolio_history.loc[current_date] = (shares * df_prices.loc[current_date]).sum()
        else:
            portfolio_history.loc[current_date] = (shares * df_prices.loc[current_date]).sum()
            
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
        start_date_str = f"{data['startYear']}-{data['startMonth']}-01"
        end_date_str = f"{data['endYear']}-{data['endMonth']}-28" # Use a safe end date
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
        
        # --- NEW: VALIDATION & WARNING LOGIC ---
        requested_start_date = pd.to_datetime(start_date_str)
        problematic_tickers = []
        for ticker in all_tickers:
            first_valid_date = df_prices_raw[ticker].first_valid_index()
            if first_valid_date is not None and first_valid_date > requested_start_date + BDay(5):
                problematic_tickers.append(f"{ticker} (從 {first_valid_date.strftime('%Y-%m-%d')} 開始)")

        warning_message = None
        if problematic_tickers:
            warning_message = f"部分資產的數據起始日晚於您的選擇。回測已自動調整至最早的共同可用日期。週期受影響的資產：{', '.join(problematic_tickers)}"
        # --- END NEW LOGIC ---

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

        # --- MODIFIED: Return data object with results and optional warning ---
        return jsonify({'data': results, 'warning': warning_message})

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': f'伺服器發生未預期的錯誤: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def index():
    return "Python backend is running."
