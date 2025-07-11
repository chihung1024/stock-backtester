import pandas as pd
import yfinance as yf
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# --- 設定資料儲存路徑 ---
data_folder = Path("data")
prices_folder = data_folder / "prices"
data_folder.mkdir(exist_ok=True)
prices_folder.mkdir(exist_ok=True)
PREPROCESSED_JSON_PATH = data_folder / "preprocessed_data.json"

# --- 平行下載設定 ---
# 同時開啟的下載執行緒數量，可根據需求調整
MAX_WORKERS = 20

# --- 數據源獲取函式 (維持不變) ---
def get_etf_holdings(etf_ticker):
    try:
        etf = yf.Ticker(etf_ticker)
        holdings = etf.holdings
        if holdings is not None and not holdings.empty:
            return holdings['symbol'].tolist()
        return []
    except Exception:
        return []

def get_sp500_from_wiki():
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        return tables[0]['Symbol'].str.replace('.', '-', regex=False).tolist()
    except Exception:
        return []

def get_nasdaq100_from_wiki():
    try:
        url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
        tables = pd.read_html(url)
        return tables[4]['Ticker'].tolist()
    except Exception:
        return []

# --- 單一股票處理函式 (優化核心) ---
def fetch_stock_info(ticker):
    """獲取單支股票的詳細財務資訊"""
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
        if info.get('trailingPE') is None and info.get('marketCap') is None:
            return None
        return {
            'ticker': ticker, 'marketCap': info.get('marketCap'), 'sector': info.get('sector'),
            'trailingPE': info.get('trailingPE'), 'forwardPE': info.get('forwardPE'),
            'dividendYield': info.get('dividendYield'), 'returnOnEquity': info.get('returnOnEquity'),
            'revenueGrowth': info.get('revenueGrowth'), 'earningsGrowth': info.get('earningsGrowth')
        }
    except Exception as e:
        # 在平行處理中，我們只印出錯誤，讓主流程繼續
        # print(f"  -> 無法獲取 {ticker} 的基本面數據: {e}")
        return None

def fetch_price_history(ticker):
    """下載單支股票的歷史價格並儲存為 CSV"""
    try:
        data = yf.download(ticker, start="1990-01-01", auto_adjust=True, progress=False)
        if not data.empty:
            price_df = data[['Close']].copy()
            price_df.to_csv(prices_folder / f"{ticker}.csv")
            return ticker, True # 回傳成功標記
        return ticker, False # 回傳失敗標記
    except Exception as e:
        # print(f"  -> 下載 {ticker} 價格時發生錯誤: {e}")
        return ticker, False

# --- 主執行函式 (已重構為平行處理) ---
def main():
    """主執行函式"""
    print("--- 開始獲取指數成分股列表 ---")
    sp500_tickers = get_etf_holdings("VOO") or get_sp500_from_wiki()
    nasdaq100_tickers = get_etf_holdings("QQQ") or get_nasdaq100_from_wiki()
    
    sp500_set = set(sp500_tickers)
    nasdaq100_set = set(nasdaq100_tickers)
    all_unique_tickers = sorted(list(sp500_set.union(nasdaq100_set)))

    if not all_unique_tickers:
        print("錯誤：所有數據來源均無法獲取任何成分股，終止執行。")
        return
    print(f"總共找到 {len(all_unique_tickers)} 支不重複的股票。")

    # --- 平行處理基本面數據 ---
    print("\n--- 步驟 1/2: 平行下載基本面數據 ---")
    all_stock_data = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 將下載任務提交到執行緒池
        future_to_ticker = {executor.submit(fetch_stock_info, ticker): ticker for ticker in all_unique_tickers}
        # 使用 tqdm 顯示進度條
        for future in tqdm(as_completed(future_to_ticker), total=len(all_unique_tickers), desc="獲取基本面"):
            info = future.result()
            if info:
                # 補上指數成員標記
                info['in_sp500'] = info['ticker'] in sp500_set
                info['in_nasdaq100'] = info['ticker'] in nasdaq100_set
                all_stock_data.append(info)

    with open(PREPROCESSED_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_stock_data, f, ensure_ascii=False, indent=4)
    print(f"基本面數據處理完成，共獲取 {len(all_stock_data)} 筆有效資料。")

    # --- 平行處理歷史價格 ---
    print("\n--- 步驟 2/2: 平行下載歷史價格數據 ---")
    success_count = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_ticker = {executor.submit(fetch_price_history, ticker): ticker for ticker in all_unique_tickers}
        for future in tqdm(as_completed(future_to_ticker), total=len(all_unique_tickers), desc="下載價格"):
            _ticker, success = future.result()
            if success:
                success_count += 1
    
    print(f"歷史價格數據更新完成，共成功下載 {success_count} 支股票。")

if __name__ == '__main__':
    main()
