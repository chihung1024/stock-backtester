from flask import Flask, request, jsonify
import pandas as pd
from pandas.tseries.offsets import MonthEnd
import traceback

# 從 utils 模組匯入核心邏輯，取代原本在此檔案中的重複實作
from .utils.data_handler import download_data_silently, get_preprocessed_data, validate_data_completeness
from .utils.simulation import run_simulation
from .utils.calculations import calculate_metrics

app = Flask(__name__)

# --- API 端點 ---

@app.route('/api/backtest', methods=['POST'])
def backtest_handler():
    """
    處理投資組合回測請求。
    現在此函式專注於請求處理和流程控制，核心計算已移至 utils 模組。
    """
    try:
        data = request.get_json()
        start_date_str = f"{data['startYear']}-{data['startMonth']}-01"
        end_date = pd.to_datetime(f"{data['endYear']}-{data['endMonth']}-01") + MonthEnd(0)
        end_date_str = end_date.strftime('%Y-%m-%d')
        
        all_tickers = set(ticker for p in data['portfolios'] for ticker in p['tickers'])
        benchmark_ticker = data.get('benchmark')
        if benchmark_ticker:
            all_tickers.add(benchmark_ticker)
            
        all_tickers_tuple = tuple(sorted(list(all_tickers)))
        if not all_tickers_tuple:
            return jsonify({'error': '請至少在一個投資組合中設定一項資產。'}), 400
            
        # 使用從 data_handler 匯入的函式
        df_prices_raw = download_data_silently(all_tickers_tuple, start_date_str, end_date_str)
        
        if isinstance(df_prices_raw, pd.Series):
            df_prices_raw = df_prices_raw.to_frame(name=all_tickers_tuple[0])
            
        if df_prices_raw.isnull().all().any():
            failed_tickers = df_prices_raw.columns[df_prices_raw.isnull().all()].tolist()
            return jsonify({'error': f"無法獲取以下股票代碼的數據: {', '.join(failed_tickers)}"}), 400
            
        # 使用從 data_handler 匯入的函式
        problematic_tickers_info = validate_data_completeness(df_prices_raw, all_tickers_tuple, pd.to_datetime(start_date_str))
        warning_message = None
        if problematic_tickers_info:
            tickers_str = ", ".join([f"{item['ticker']} (從 {item['start_date']} 開始)" for item in problematic_tickers_info])
            warning_message = f"部分資產的數據起始日晚於您的選擇。回測已自動調整至最早的共同可用日期。週期受影響的資產：{tickers_str}"
            
        df_prices_common = df_prices_raw.dropna()
        if df_prices_common.empty:
            return jsonify({'error': '在指定的時間範圍內，找不到所有股票的共同交易日。'}), 400
            
        initial_amount = float(data['initialAmount'])
        benchmark_result = None
        benchmark_history = None
        
        if benchmark_ticker and benchmark_ticker in df_prices_common.columns:
            benchmark_config = {'name': benchmark_ticker, 'tickers': [benchmark_ticker], 'weights': [100], 'rebalancingPeriod': 'never'}
            # 使用從 simulation 匯入的函式
            benchmark_result = run_simulation(benchmark_config, df_prices_common, initial_amount)
            if benchmark_result:
                benchmark_history = pd.DataFrame(benchmark_result['portfolioHistory']).set_index('date')
                benchmark_history.index = pd.to_datetime(benchmark_history.index)
                
        results = [res for p_config in data['portfolios'] if p_config['tickers'] and (res := run_simulation(p_config, df_prices_common, initial_amount, benchmark_history))]
        
        if not results:
            return jsonify({'error': '沒有足夠的共同交易日來進行回測。'}), 400
            
        if benchmark_result and benchmark_history is not None:
            # 使用從 calculations 匯入的函式來補全 benchmark 指標
            temp_metrics = calculate_metrics(benchmark_history)
            benchmark_result.update(temp_metrics)
            benchmark_result['beta'] = 1.0
            benchmark_result['alpha'] = 0.00

        return jsonify({'data': results, 'benchmark': benchmark_result, 'warning': warning_message})
        
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': f'伺服器發生未預期的錯誤: {str(e)}'}), 500

@app.route('/api/scan', methods=['POST'])
def scan_handler():
    """
    處理個股掃描請求。
    """
    try:
        data = request.get_json()
        tickers = data['tickers']
        benchmark_ticker = data.get('benchmark')
        start_date_str = f"{data['startYear']}-{data['startMonth']}-01"
        end_date = pd.to_datetime(f"{data['endYear']}-{data['endMonth']}-01") + MonthEnd(0)
        end_date_str = end_date.strftime('%Y-%m-%d')
        
        if not tickers:
            return jsonify({'error': '股票代碼列表不可為空。'}), 400
            
        all_tickers_to_download = set(tickers)
        if benchmark_ticker:
            all_tickers_to_download.add(benchmark_ticker)
            
        all_tickers_tuple = tuple(sorted(list(all_tickers_to_download)))
        df_prices_raw = download_data_silently(all_tickers_tuple, start_date_str, end_date_str)
        
        if isinstance(df_prices_raw, pd.Series):
            df_prices_raw = df_prices_raw.to_frame(name=all_tickers_tuple[0])
            
        benchmark_history = None
        if benchmark_ticker and benchmark_ticker in df_prices_raw.columns:
            benchmark_prices = df_prices_raw[[benchmark_ticker]].dropna()
            if not benchmark_prices.empty:
                benchmark_history = benchmark_prices.rename(columns={benchmark_ticker: 'value'})
                
        results = []
        requested_start_date = pd.to_datetime(start_date_str)
        available_tickers = df_prices_raw.columns.tolist() if hasattr(df_prices_raw, 'columns') else [df_prices_raw.name]
        
        for ticker in tickers:
            try:
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
                # 使用從 calculations 匯入的函式
                metrics = calculate_metrics(history_df, benchmark_history)
                results.append({'ticker': ticker, **metrics, 'note': note})
                
            except Exception as e:
                print(f"處理 {ticker} 時發生錯誤: {e}")
                results.append({'ticker': ticker, 'error': '計算錯誤'})
                
        return jsonify(results)
        
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': f'伺服器發生未預期的錯誤: {str(e)}'}), 500

@app.route('/api/screener', methods=['POST'])
def screener_handler():
    """
    處理股票篩選請求。
    """
    try:
        data = request.get_json()
        index = data.get('index', 'sp500')
        filters = data.get('filters', {})
        sector = data.get('sector', 'any')

        # 使用從 data_handler 匯入的函式
        all_stocks = get_preprocessed_data()

        if index == 'sp500':
            base_pool = [s for s in all_stocks if s.get('in_sp500')]
        elif index == 'nasdaq100':
            base_pool = [s for s in all_stocks if s.get('in_nasdaq100')]
        elif index == 'russell1000':
            base_pool = [s for s in all_stocks if s.get('in_russell1000')]
        else:
            base_pool = all_stocks

        filtered_stocks = []
        for stock in base_pool:
            if sector != 'any' and stock.get('sector') != sector:
                continue
            
            match = True
            for key, limits in filters.items():
                stock_value = stock.get(key)
                if stock_value is None or not isinstance(stock_value, (int, float)):
                    match = False
                    break
                
                if limits.get('min') is not None and stock_value < limits['min']:
                    match = False
                    break
                
                if limits.get('max') is not None and stock_value > limits['max']:
                    match = False
                    break
            
            if match:
                filtered_stocks.append(stock['ticker'])

        return jsonify(filtered_stocks)
    except ValueError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': f'篩選器發生錯誤: {str(e)}'}), 500

@app.route('/', methods=['GET'])
def index():
    """
    根路由，用於健康檢查。
    """
    return "Python backend is running."
