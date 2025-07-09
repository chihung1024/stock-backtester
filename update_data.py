import pandas as pd
import yfinance as yf
import json
import time

def get_etf_holdings(etf_ticker):
    """從指定的 ETF 獲取其成分股列表"""
    try:
        etf = yf.Ticker(etf_ticker)
        holdings = etf.holdings
        if holdings is not None and not holdings.empty:
            return holdings['symbol'].tolist()
        else:
            print(f"警告：無法從 {etf_ticker} 獲取持股數據。")
            return []
    except Exception as e:
        print(f"獲取 {etf_ticker} 持股時發生錯誤: {e}")
        return []

def get_stock_info(ticker_str):
    """使用 yfinance 獲取股票的詳細財務資訊"""
    try:
        ticker_obj = yf.Ticker(ticker_str)
        info = ticker_obj.info
        
        # 提取我們需要的核心數據，如果數據不存在則提供預設值
        return {
            'ticker': ticker_str,
            'marketCap': info.get('marketCap', 0),
            'sector': info.get('sector', 'N/A'),
            'industry': info.get('industry', 'N/A'),
            'averageVolume': info.get('averageVolume', 0),
            'revenueGrowth': info.get('revenueGrowth'), # 可能為 None
            'forwardEps': info.get('forwardEps'),       # 可能為 None
        }
    except Exception as e:
        print(f"無法獲取 {ticker_str} 的數據: {e}")
        return None

def main():
    """主執行函式"""
    print("開始從 ETF 獲取指數成分股...")
    sp500_tickers = set(get_etf_holdings("VOO"))
    nasdaq100_tickers = set(get_etf_holdings("QQQ"))
    russell3000_tickers = set(get_etf_holdings("IWV")) # MODIFIED: Changed from IWM to IWV
    
    all_unique_tickers = sorted(list(sp500_tickers.union(nasdaq100_tickers).union(russell3000_tickers)))
    
    if not all_unique_tickers:
        print("錯誤：無法獲取任何成分股，終止執行。")
        return

    print(f"總共找到 {len(all_unique_tickers)} 支不重複的股票。")
    
    all_stock_data = []
    for i, ticker in enumerate(all_unique_tickers):
        print(f"正在處理: {ticker} ({i+1}/{len(all_unique_tickers)})")
        info = get_stock_info(ticker)
        if info:
            # 標記該股票屬於哪個指數
            info['in_sp500'] = ticker in sp500_tickers
            info['in_nasdaq100'] = ticker in nasdaq100_tickers
            info['in_russell3000'] = ticker in russell3000_tickers # MODIFIED: Changed key name
            all_stock_data.append(info)
        # 為了避免對 API 造成太大負擔，每處理一筆就稍微延遲一下
        time.sleep(0.1) 

    # 將所有數據寫入一個名為 preprocessed_data.json 的檔案
    with open('preprocessed_data.json', 'w', encoding='utf-8') as f:
        json.dump(all_stock_data, f, ensure_ascii=False, indent=4)
        
    print("數據處理完成，已儲存至 preprocessed_data.json")

if __name__ == '__main__':
    main()
