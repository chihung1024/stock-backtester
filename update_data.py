import pandas as pd
import yfinance as yf
import json
import time

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

def get_russell3000_from_ishares():
    """備援方案：從 iShares 官網獲取 Russell 3000 成分股列表"""
    try:
        print("備援方案：正在從 iShares 官網獲取 Russell 3000 列表...")
        url = 'https://www.ishares.com/us/products/239714/ishares-russell-3000-etf/1467271812596.ajax?fileType=csv&fileName=IWV_holdings&dataType=fund'
        df = pd.read_csv(url, skiprows=9)
        df = df[df['Asset Class'] == 'Equity']
        tickers = df['Ticker'].dropna().unique().tolist()
        print(f"成功從 iShares 獲取 {len(tickers)} 支 Russell 3000 股票。")
        return tickers
    except Exception as e:
        print(f"備援方案失敗 (Russell 3000): {e}")
        return []

def get_stock_info(ticker_str):
    """使用 yfinance 獲取股票的詳細財務資訊"""
    try:
        ticker_obj = yf.Ticker(ticker_str)
        info = ticker_obj.info
        
        # 提取所有我們需要的財務指標，若不存在則提供 None 或 0
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
        print(f"  -> 無法獲取 {ticker_str} 的財務數據: {e}")
        return None

def main():
    """主執行函式"""
    print("開始獲取指數成分股...")
    
    # S&P 500 with fallback
    sp500_tickers = get_etf_holdings("VOO")
    if not sp500_tickers:
        sp500_tickers = get_sp500_from_wiki()
    
    # NASDAQ 100 with fallback
    nasdaq100_tickers = get_etf_holdings("QQQ")
    if not nasdaq100_tickers:
        nasdaq100_tickers = get_nasdaq100_from_wiki()

    # Russell 3000 with fallback
    russell3000_tickers = get_etf_holdings("IWV")
    if not russell3000_tickers:
        russell3000_tickers = get_russell3000_from_ishares()

    sp500_set = set(sp500_tickers)
    nasdaq100_set = set(nasdaq100_tickers)
    russell3000_set = set(russell3000_tickers)
    
    all_unique_tickers = sorted(list(sp500_set.union(nasdaq100_set).union(russell3000_set)))
    
    if not all_unique_tickers:
        print("錯誤：所有數據來源均無法獲取任何成分股，終止執行。")
        return

    print(f"總共找到 {len(all_unique_tickers)} 支不重複的股票。")
    
    all_stock_data = []
    for i, ticker in enumerate(all_unique_tickers):
        print(f"正在處理: {ticker} ({i+1}/{len(all_unique_tickers)})")
        info = get_stock_info(ticker)
        if info:
            info['in_sp500'] = ticker in sp500_set
            info['in_nasdaq100'] = ticker in nasdaq100_set
            info['in_russell3000'] = ticker in russell3000_set
            all_stock_data.append(info)
        time.sleep(0.1) 

    with open('preprocessed_data.json', 'w', encoding='utf-8') as f:
        json.dump(all_stock_data, f, ensure_ascii=False, indent=4)
        
    print("數據處理完成，已儲存至 preprocessed_data.json")

if __name__ == '__main__':
    main()
