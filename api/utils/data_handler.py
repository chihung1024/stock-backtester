import os
import sys
from io import StringIO
import requests
import yfinance as yf
import pandas as pd
from pandas.tseries.offsets import BDay
from cachetools import cached, TTLCache

# --- 快取設定 ---
cache = TTLCache(maxsize=128, ttl=600)

# --- 從環境變數讀取 Gist Raw URL ---
GIST_RAW_URL = os.environ.get('GIST_RAW_URL')

@cached(cache)
def download_data_silently(tickers, start_date, end_date):
    """
    使用快取機制下載數據，並抑制 yfinance 的輸出。
    """
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        data = yf.download(list(tickers), start=start_date, end=end_date, auto_adjust=True, progress=False)['Close']
    finally:
        sys.stdout = old_stdout
    return data

@cached(cache)
def get_preprocessed_data():
    """從 Gist 下載並快取預處理好的數據"""
    if not GIST_RAW_URL:
        raise ValueError("錯誤：GIST_RAW_URL 環境變數未設定。請在 Vercel 專案設定中新增此變數。")
    response = requests.get(GIST_RAW_URL)
    response.raise_for_status() # 如果下載失敗會拋出錯誤
    return response.json()

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
