import pandas as pd
import yfinance as yf
import json
import time
import os
from pathlib import Path

# --- 設定資料儲存路徑 ---
data_folder = Path("data")
prices_folder = data_folder / "prices"
data_folder.mkdir(exist_ok=True)
prices_folder.mkdir(exist_ok=True)

PREPROCESSED_JSON_PATH = data_folder / "preprocessed_data.json"

def get_etf_holdings(etf_ticker):
    """主要方案：從指定的 ETF 獲取其成分股列表"""
    try:
        print(f"主要方案：正在嘗試從 yfinance 獲取 {etf_ticker} 持股...")
        etf = yf.Ticker(etf_ticker)
        holdings = etf.holdings
        if holdings is not None and not holdings.empty:
            tickers = holdings['symbol'].tolist()
            print(f"成功從 yfinance 獲取 {len(tickers)} 支 {etf_ticker} 持股。")
            return tickers
        else:
            print(f"主要方案警告：無法從 {etf_ticker} 獲取持股數據，將嘗試備援方案。")
            return []
    except Exception as e:
        print(f"主要方案錯誤 ({etf_ticker}): {e}，將嘗試備援方案。")
        return []

def get_sp500_from_wiki():
    """備援方案：從維基百科獲取 S&P 500 成分股列表"""
    try:
        print("備援方案：正在從維基百科獲取 S&P 500 列表...")
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        sp500_table = tables[0]
        tickers = sp500_table['Symbol'].str.replace('.', '-', regex=False).tolist()
        print(f"成功從維基百科獲取 {len(tickers)} 支 S&P 500 股票。")
        return tickers
    except Exception as e:
        print(f"備援方案失敗 (S&P 500): {e}")
        return []

def get_nasdaq100_from_wiki():
    """備援方案：從維基百科獲取 NASDAQ 100 成分股列表"""
    try:
        print("備援方案：正在從維基百科獲取 NASDAQ 100 列表...")
        url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
        tables = pd.read_html(url)
        nasdaq100_table = tables[4] 
        tickers = nasdaq100_table['Ticker'].tolist()
        print(f"成功從維基百科獲取 {len(tickers)} 支 NASDAQ 100 股票。")
        return tickers
    except Exception as e:
        print(f"備援方案失敗 (NASDAQ 100): {e}")
        return []

# (已移除) get_russell1000_from_ishares() 函式已被移除

def get_stock_info(ticker_str, max_retries=3, initial_delay=5):
    """使用 yfinance 獲取股票的詳細財務資訊，並加入重試與指數退避機制。"""
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            ticker_obj = yf.Ticker(ticker_str)
            info = ticker_obj.info
            
            if info.get('trailingPE') is None and info.get('marketCap') is None and info.get('regularMarketPrice') is None:
                 print(f"  -> {ticker_str} 的數據不完整或無效，跳過。")
                 return None

            return {
                'ticker': ticker_str,
                'marketCap': info.get('marketCap'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'averageVolume': info.get('averageVolume'),
                'trailingPE': info.get('trailingPE'),
                'forwardPE': info.get('forwardPE'),
                'priceToBook': info.get('priceToBook'),
                'pegRatio': info.get('pegRatio'),
                'priceToSales': info.get('priceToSalesTrailing12Months'),
                'revenueGrowth': info.get('revenueGrowth'),
                'earningsGrowth': info.get('earningsGrowth'),
                'returnOnEquity': info.get('returnOnEquity'),
                'grossMargins': info.get('grossMargins'),
                'operatingMargins': info.get('operatingMargins'),
                'dividendYield': info.get('dividendYield'),
            }
        except Exception as e:
            error_str = str(e).lower()
            if 'too many requests' in error_str or '429' in error_str or 'rate limit' in error_str:
                print(f"  -> 請求 {ticker_str} 時被速率限制。將在 {delay} 秒後重試... (第 {attempt + 1}/{max_retries} 次)")
                time.sleep(delay)
                delay *= 2 
            else:
                print(f"  -> 無法獲取 {ticker_str} 的數據: {e}")
                return None
    
    print(f"  -> 在 {max_retries} 次重試後，仍無法獲取 {ticker_str} 的數據。")
    return None

def update_price_data(tickers):
    """下載指定股票列表的歷史價格並儲存為 CSV"""
    print(f"\n--- 開始更新 {len(tickers)} 支股票的歷史價格數據 ---")
    for i, ticker in enumerate(tickers):
        try:
            print(f"正在下載: {ticker} ({i+1}/{len(tickers)})")
            data = yf.download(ticker, start="1990-01-01", auto_adjust=True, progress=False)
            if not data.empty:
                price_df = data[['Close']].copy()
                price_df.to_csv(prices_folder / f"{ticker}.csv")
            else:
                print(f"  -> {ticker} 沒有可下載的價格數據。")
            time.sleep(0.3)
        except Exception as e:
            print(f"  -> 下載 {ticker} 價格時發生錯誤: {e}")
    print("--- 歷史價格數據更新完成 ---")


def main():
    """主執行函式"""
    print("--- 開始更新基本面數據 ---")
    
    sp500_tickers = get_etf_holdings("VOO") or get_sp500_from_wiki()
    nasdaq100_tickers = get_etf_holdings("QQQ") or get_nasdaq100_from_wiki()
    # (已移除) 羅素 1000 的獲取邏輯
    
    sp500_set = set(sp500_tickers)
    nasdaq100_set = set(nasdaq100_tickers)
    # (已移除) 羅素 1000 的集合
    
    # (已修改) 合併股票池，不再包含羅素 1000
    all_unique_tickers = sorted(list(sp500_set.union(nasdaq100_set)))
    
    if not all_unique_tickers:
        print("錯誤：所有數據來源均無法獲取任何成分股，終止執行。")
        return

    print(f"總共找到 {len(all_unique_tickers)} 支不重複的股票。")
    
    all_stock_data = []
    for i, ticker in enumerate(all_unique_tickers):
        print(f"正在處理基本面: {ticker} ({i+1}/{len(all_unique_tickers)})")
        info = get_stock_info(ticker)
        if info:
            info['in_sp500'] = ticker in sp500_set
            info['in_nasdaq100'] = ticker in nasdaq100_set
            # (已移除) 不再標記是否在羅素 1000 中
            all_stock_data.append(info)
        time.sleep(0.2) 

    with open(PREPROCESSED_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_stock_data, f, ensure_ascii=False, indent=4)
        
    print(f"基本面數據處理完成，已儲存至 {PREPROCESSED_JSON_PATH}")

    update_price_data(all_unique_tickers)

if __name__ == '__main__':
    main()
