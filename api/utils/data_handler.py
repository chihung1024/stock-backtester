import os
import pandas as pd
from pandas.tseries.offsets import BDay
from cachetools import cached, TTLCache
import json
from pathlib import Path

# --- 快取設定 ---
# 快取現在用於緩存從檔案讀取的 DataFrame，避免重複的 I/O 操作
cache = TTLCache(maxsize=256, ttl=1800) # 快取 30 分鐘

# --- 資料路徑設定 ---
# 使用相對路徑來定位部署包內的 data 資料夾
# Path(__file__) 會取得目前檔案 (data_handler.py) 的路徑
# .parent.parent 會往上兩層，到達 api/ 的同層目錄
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FOLDER = BASE_DIR / "data"
PRICES_FOLDER = DATA_FOLDER / "prices"
PREPROCESSED_JSON_PATH = DATA_FOLDER / "preprocessed_data.json"


@cached(cache)
def read_price_data_from_repo(tickers: tuple, start_date_str: str, end_date_str: str) -> pd.DataFrame:
    """
    從倉庫中的 CSV 檔案讀取指定股票的價格數據，並合併成一個 DataFrame。
    """
    all_prices = []
    for ticker in tickers:
        file_path = PRICES_FOLDER / f"{ticker}.csv"
        if file_path.exists():
            df = pd.read_csv(file_path, index_col='Date', parse_dates=True)
            df.rename(columns={'Close': ticker}, inplace=True)
            all_prices.append(df)
        else:
            print(f"警告：找不到股票 {ticker} 的價格檔案。")

    if not all_prices:
        return pd.DataFrame()

    # 合併所有股票的價格數據
    combined_df = pd.concat(all_prices, axis=1)
    
    # 根據請求的日期範圍篩選數據
    mask = (combined_df.index >= start_date_str) & (combined_df.index <= end_date_str)
    return combined_df.loc[mask]


@cached(cache)
def get_preprocessed_data():
    """從倉庫中的 JSON 檔案讀取並快取預處理好的數據"""
    if not PREPROCESSED_JSON_PATH.exists():
         raise ValueError("錯誤：找不到 preprocessed_data.json 檔案。")
    with open(PREPROCESSED_JSON_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def validate_data_completeness(df_prices_raw, all_tickers, requested_start_date):
    """
    檢查是否有任何股票的數據起始日顯著晚於請求的起始日。
    回傳有問題的股票列表，用於產生警告或備註。
    """
    problematic_tickers = []
    for ticker in all_tickers:
        if ticker in df_prices_raw.columns:
            first_valid_date = df_prices_raw[ticker].first_valid_index()
            if first_valid_date is not None and first_valid_date > requested_start_date + BDay(5):
                problematic_tickers.append({'ticker': ticker, 'start_date': first_valid_date.strftime('%Y-%m-%d')})
    return problematic_tickers
