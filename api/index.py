# 檔案路徑: /api/index.py
from flask import Flask, request, jsonify
import yfinance as yf
import pandas as pd
import numpy as np

app = Flask(__name__)

# Vercel 會自動處理 CORS，無需額外設定

def calculate_metrics(portfolio_history, risk_free_rate=0.02):
    if portfolio_history.empty or len(portfolio_history) < 2:
        return {'cagr': 0, 'mdd': 0, 'sharpe_ratio': 0, 'sortino_ratio': 0}

    end_value = portfolio_history['value'].iloc[-1]
    start_value = portfolio_history['value'].iloc[0]
    start_date = portfolio_history.index[0]
    end_date = portfolio_history.index[-1]
    years = (end_date - start_date).days / 365.25
    cagr = (end_value / start_value) ** (1 / years) - 1 if years > 0 else 0

    portfolio_history['peak'] = portfolio_history['value'].cummax()
    portfolio_history['drawdown'] = (portfolio_history['value'] - portfolio_history['peak']) / portfolio_history['peak']
    mdd = portfolio_history['drawdown'].min()

    daily_returns = portfolio_history['value'].pct_change().dropna()
    
    if len(daily_returns) < 2:
        return {'cagr': cagr, 'mdd': mdd, 'sharpe_ratio': float('inf'), 'sortino_ratio': float('inf')}

    annual_std = daily_returns.std() * np.sqrt(252)
    sharpe_ratio = (cagr - risk_free_rate) / annual_std if annual_std != 0 else float('inf')

    negative_returns = daily_returns[daily_returns < 0]
    downside_std = negative_returns.std() * np.sqrt(252) if len(negative_returns) > 1 else 0
    sortino_ratio = (cagr - risk_free_rate) / downside_std if downside_std != 0 else float('inf')

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
    return rebalance_dates[1:]

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
        if current_date in rebalancing_dates:
            current_value = (shares * df_prices.loc[current_date]).sum()
            shares = (current_value * weights) / df_prices.loc[current_date]
            portfolio_history.loc[current_date] = current_value
        else:
            portfolio_history.loc[current_date] = (shares * df_prices.loc[current_date]).sum()
            
    portfolio_history.dropna(inplace=True)
    metrics = calculate_metrics(portfolio_history.to_frame('value'))
    
    return {
        'name': portfolio_config['name'], **metrics,
        'portfolioHistory': [{'date': date.strftime('%Y-%m-%d'), 'value': value} for date, value in portfolio_history.items()]
    }

# *** FIX: Change the route to '/' to match Vercel's file-based routing ***
@app.route('/', methods=['POST'])
def handler():
    try:
        data = request.get_json()
        portfolios = data['portfolios']
        start_date_str = f"{data['startYear']}-{data['startMonth']}-01"
        end_date_str = f"{data['endYear']}-{data['endMonth']}-28"
        initial_amount = float(data['initialAmount'])

        all_tickers = sorted(list(set(ticker for p in portfolios for ticker in p['tickers'])))
        
        if not all_tickers:
            return jsonify({'error': '請至少在一個投資組合中設定一項資產。'}), 400

        df_prices_raw = yf.download(all_tickers, start=start_date_str, end=end_date_str, auto_adjust=True)['Close']
        
        if isinstance(df_prices_raw, pd.Series):
            df_prices_raw = df_prices_raw.to_frame(name=all_tickers[0])

        if df_prices_raw.isnull().all().any():
            failed_tickers = df_prices_raw.columns[df_prices_raw.isnull().all()].tolist()
            return jsonify({'error': f"無法獲取數據: {', '.join(failed_tickers)}"}), 400

        df_prices_common = df_prices_raw.dropna()

        if df_prices_common.empty:
            return jsonify({'error': '在指定的時間範圍內，找不到所有股票的共同交易日。'}), 400

        results = []
        for p_config in portfolios:
            if not p_config['tickers']: continue
            sim_result = run_simulation(p_config, df_prices_common, initial_amount)
            if sim_result: results.append(sim_result)
        
        if not results:
            return jsonify({'error': '在指定的時間範圍內，沒有足夠的共同交易日來進行回測。'}), 400

        return jsonify(results)

    except Exception as e:
        return jsonify({'error': f'伺服器發生錯誤: {str(e)}'}), 500
