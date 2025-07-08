from flask import Flask, request, jsonify
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Define constants for better readability and maintenance
TRADING_DAYS_PER_YEAR = 252

def get_stock_data(ticker, start_date, end_date):
    """Fetches historical stock data from Yahoo Finance."""
    try:
        stock_data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        if stock_data.empty:
            print(f"No data found for {ticker}, symbol may be delisted or invalid.")
            return None
        return stock_data['Adj Close']
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None

def calculate_metrics(portfolio_values):
    """Calculates performance metrics for a given portfolio value series."""
    if portfolio_values.empty or len(portfolio_values) < 2:
        return {
            'cagr': 'N/A',
            'mdd': 'N/A',
            'sharpe_ratio': 'N/A',
            'sortino_ratio': 'N/A'
        }

    # --- 1. Calculate Compounded Annual Growth Rate (CAGR) ---
    total_return = portfolio_values.iloc[-1] / portfolio_values.iloc[0] - 1
    years = (portfolio_values.index[-1] - portfolio_values.index[0]).days / 365.25
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

    # --- 2. Calculate Maximum Drawdown (MDD) ---
    cumulative_max = portfolio_values.cummax()
    drawdown = (portfolio_values - cumulative_max) / cumulative_max
    mdd = drawdown.min()

    # --- 3. Calculate Sharpe Ratio ---
    # The Sharpe Ratio measures the performance of an investment compared to a risk-free asset, after adjusting for its risk.
    daily_returns = portfolio_values.pct_change().dropna()
    annualized_std = daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    
    # Assuming risk-free rate is 0. Handle division by zero.
    sharpe_ratio = cagr / annualized_std if annualized_std != 0 else 0

    # --- 4. Calculate Sortino Ratio ---
    # The Sortino Ratio is a variation of the Sharpe Ratio that only factors in the downside, or negative, volatility.
    negative_returns = daily_returns[daily_returns < 0]
    downside_std = negative_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    
    # Handle division by zero.
    sortino_ratio = cagr / downside_std if downside_std != 0 else 0

    return {
        'cagr': f"{cagr:.2%}",
        'mdd': f"{mdd:.2%}",
        'sharpe_ratio': f"{sharpe_ratio:.2f}" if annualized_std != 0 else 'N/A',
        'sortino_ratio': f"{sortino_ratio:.2f}" if downside_std != 0 else 'N/A'
    }


def run_backtest(start_date, end_date, initial_investment, rebalance_frequency, dividend_reinvestment, portfolios):
    """Runs the backtest for all configured portfolios."""
    all_tickers = set()
    for p in portfolios:
        for ticker in p['allocations']:
            all_tickers.add(ticker)

    stock_data = {}
    for ticker in all_tickers:
        data = get_stock_data(ticker, start_date, end_date)
        if data is not None:
            stock_data[ticker] = data

    results = {}
    for i, p_config in enumerate(portfolios):
        portfolio_name = p_config.get('name', f'Portfolio {i+1}')
        allocations = p_config['allocations']
        
        valid_tickers = {ticker: weight for ticker, weight in allocations.items() if ticker in stock_data and not stock_data[ticker].empty}
        if not valid_tickers:
            continue

        # Align data to common index
        df = pd.DataFrame({ticker: stock_data[ticker] for ticker in valid_tickers})
        df.dropna(inplace=True)

        if df.empty:
            continue

        # Simplified rebalancing logic
        portfolio_values = pd.Series(index=df.index, dtype=float)
        portfolio_values.iloc[0] = initial_investment
        
        last_rebalance_date = df.index[0]
        
        # Calculate initial number of shares
        current_allocations = {ticker: (initial_investment * (weight / 100.0)) / df.loc[last_rebalance_date, ticker] for ticker, weight in valid_tickers.items()}

        for t in range(1, len(df.index)):
            current_date = df.index[t]
            
            # Rebalance if needed
            rebalance = False
            if rebalance_frequency == 'annual' and current_date.year != last_rebalance_date.year:
                rebalance = True
            elif rebalance_frequency == 'quarterly' and (current_date.quarter != last_rebalance_date.quarter or current_date.year != last_rebalance_date.year):
                rebalance = True
            elif rebalance_frequency == 'monthly' and (current_date.month != last_rebalance_date.month or current_date.year != last_rebalance_date.year):
                rebalance = True

            # Calculate current portfolio value
            current_value = sum(current_allocations[ticker] * df.loc[current_date, ticker] for ticker in valid_tickers)
            portfolio_values[current_date] = current_value

            if rebalance:
                # Re-calculate number of shares based on new total value and target allocations
                current_allocations = {ticker: (current_value * (weight / 100.0)) / df.loc[current_date, ticker] for ticker, weight in valid_tickers.items()}
                last_rebalance_date = current_date
        
        portfolio_values.dropna(inplace=True)
        metrics = calculate_metrics(portfolio_values)
        
        results[portfolio_name] = {
            'metrics': metrics,
            'data': portfolio_values.reset_index().rename(columns={'index': 'date', 0: 'value'}).to_dict('records')
        }

    return results

@app.route('/api/backtest', methods=['POST'])
def backtest_endpoint():
    """API endpoint to trigger the backtest."""
    try:
        config = request.json
        start_date = datetime.strptime(config['startDate'], '%Y-%m-%d')
        end_date = datetime.strptime(config['endDate'], '%Y-%m-%d')

        results = run_backtest(
            start_date,
            end_date,
            config['initialInvestment'],
            config['rebalanceFrequency'],
            config['dividendReinvestment'],
            config['portfolios']
        )
        return jsonify(results)
    except Exception as e:
        print(f"An error occurred in backtest_endpoint: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
