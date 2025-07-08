from flask import Flask, request, jsonify
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import logging

app = Flask(__name__)
CORS(app)

# --- Logging Configuration ---
# Configure logging to be more informative
logging.basicConfig(level=logging.INFO)
gunicorn_logger = logging.getLogger('gunicorn.error')
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)


# --- Constants ---
TRADING_DAYS_PER_YEAR = 252

def get_stock_data(ticker, start_date, end_date):
    """Fetches and validates historical stock data from Yahoo Finance."""
    try:
        stock_data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        if stock_data.empty:
            app.logger.warning(f"No data found for ticker: {ticker}. It might be delisted or the symbol is incorrect.")
            return None
        # Forward-fill to handle missing values (e.g., holidays) before returning
        return stock_data['Adj Close'].ffill()
    except Exception as e:
        app.logger.error(f"An exception occurred while fetching data for {ticker}: {e}")
        return None

def calculate_metrics(portfolio_values):
    """Calculates performance metrics for a given portfolio value series."""
    if portfolio_values.empty or len(portfolio_values) < 2:
        return {'cagr': 'N/A', 'mdd': 'N/A', 'sharpe_ratio': 'N/A', 'sortino_ratio': 'N/A'}

    # --- CAGR ---
    total_return = portfolio_values.iloc[-1] / portfolio_values.iloc[0] - 1
    years = (portfolio_values.index[-1] - portfolio_values.index[0]).days / 365.25
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 and total_return > -1 else 0

    # --- MDD ---
    cumulative_max = portfolio_values.cummax()
    drawdown = (portfolio_values - cumulative_max) / cumulative_max
    mdd = drawdown.min() if not drawdown.empty else 0

    # --- Sharpe & Sortino Ratios ---
    daily_returns = portfolio_values.pct_change().dropna()
    annualized_std = daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe_ratio = cagr / annualized_std if annualized_std != 0 else 0

    negative_returns = daily_returns[daily_returns < 0]
    downside_std = negative_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    sortino_ratio = cagr / downside_std if downside_std != 0 else 0

    return {
        'cagr': f"{cagr:.2%}",
        'mdd': f"{mdd:.2%}",
        'sharpe_ratio': f"{sharpe_ratio:.2f}" if annualized_std != 0 else 'N/A',
        'sortino_ratio': f"{sortino_ratio:.2f}" if downside_std != 0 else 'N/A'
    }

def run_backtest(start_date, end_date, initial_investment, rebalance_frequency, portfolios):
    """Runs the backtest for all configured portfolios with enhanced robustness."""
    all_tickers = {ticker for p in portfolios for ticker in p['allocations']}
    
    stock_data = {ticker: get_stock_data(ticker, start_date, end_date) for ticker in all_tickers}
    stock_data = {ticker: data for ticker, data in stock_data.items() if data is not None}

    results = {}
    for i, p_config in enumerate(portfolios):
        portfolio_name = p_config.get('name', f'Portfolio {i+1}')
        allocations = p_config['allocations']
        
        valid_tickers = {ticker: weight for ticker, weight in allocations.items() if ticker in stock_data and weight > 0}
        if not valid_tickers:
            app.logger.warning(f"Portfolio '{portfolio_name}' has no valid tickers with positive allocation. Skipping.")
            continue

        df = pd.DataFrame({ticker: stock_data[ticker] for ticker in valid_tickers}).dropna()
        if df.empty:
            app.logger.warning(f"No overlapping date range for tickers in portfolio '{portfolio_name}'. Skipping.")
            continue

        portfolio_values = pd.Series(index=df.index, dtype=float)
        last_rebalance_date = df.index[0]
        
        # --- Robust initial allocation ---
        current_allocations = {}
        actual_initial_investment = 0
        for ticker, weight in valid_tickers.items():
            price = df.loc[last_rebalance_date, ticker]
            if price and price > 0:
                value_to_allocate = initial_investment * (weight / 100.0)
                current_allocations[ticker] = value_to_allocate / price
                actual_initial_investment += value_to_allocate
            else:
                app.logger.warning(f"Ticker {ticker} has zero or invalid price on start date. Skipping for initial allocation.")
        
        if not current_allocations:
            app.logger.warning(f"Could not allocate any assets for portfolio '{portfolio_name}' on start date. Skipping.")
            continue
        portfolio_values.iloc[0] = actual_initial_investment
        
        # --- Main backtest loop ---
        for t in range(1, len(df.index)):
            current_date = df.index[t]
            current_value = sum(current_allocations.get(ticker, 0) * df.loc[current_date, ticker] for ticker in valid_tickers)
            portfolio_values[current_date] = current_value

            # --- Rebalancing Logic ---
            rebalance = False
            if rebalance_frequency == 'annual' and current_date.year != last_rebalance_date.year: rebalance = True
            elif rebalance_frequency == 'quarterly' and current_date.quarter != last_rebalance_date.quarter: rebalance = True
            elif rebalance_frequency == 'monthly' and current_date.month != last_rebalance_date.month: rebalance = True

            if rebalance:
                last_rebalance_date = current_date
                new_allocations = {}
                for ticker, weight in valid_tickers.items():
                    price = df.loc[current_date, ticker]
                    if price and price > 0:
                        new_allocations[ticker] = (current_value * (weight / 100.0)) / price
                current_allocations = new_allocations

        metrics = calculate_metrics(portfolio_values.dropna())
        results[portfolio_name] = {
            'metrics': metrics,
            'data': portfolio_values.dropna().reset_index().rename(columns={'index': 'date', 0: 'value'}).to_dict('records')
        }

    return results

@app.route('/api/backtest', methods=['POST'])
def backtest_endpoint():
    """API endpoint to trigger the backtest."""
    app.logger.info("Received a new backtest request.")
    try:
        config = request.json
        start_date = datetime.strptime(config['startDate'], '%Y-%m-%d')
        end_date = datetime.strptime(config['endDate'], '%Y-%m-%d')

        results = run_backtest(
            start_date,
            end_date,
            config['initialInvestment'],
            config['rebalanceFrequency'],
            config.get('dividendReinvestment', True), # Safely get config
            config['portfolios']
        )
        
        if not results:
            return jsonify({"error": "無法根據提供的股票代碼和日期範圍生成回測結果，請檢查輸入是否有效。"}), 400

        app.logger.info("Backtest completed successfully.")
        return jsonify(results)
    except Exception as e:
        app.logger.error(f"An unhandled exception occurred in backtest_endpoint: {e}", exc_info=True)
        return jsonify({"error": "伺服器發生內部錯誤，無法完成回測。"}), 500

if __name__ == '__main__':
    app.run(debug=True)
