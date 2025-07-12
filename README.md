台股策略回測系統 (Cloudflare 版本)
這是一個基於 Python Flask 和原生 JavaScript 的簡易台股策略回測工具，已成功移植到 Cloudflare Pages 和 Cloudflare Python Workers 進行部署。

功能
策略選股器: 根據多個技術指標（如均線、RSI、MACD）篩選出符合條件的股票。

歷史回測器: 對指定的股票、時間區間和交易策略進行回測，並產出績效報告和交易明細。

技術棧
前端: HTML, Tailwind CSS, 原生 JavaScript

後端: Python, Flask

部署: Cloudflare Pages (靜態網站) + Cloudflare Python Workers (Serverless API)

資料來源: yfinance

專案結構 (Cloudflare)
為了適應 Cloudflare 的部署模型，我們需要調整專案的目錄結構。

/
├── functions/                  # Cloudflare Workers 程式碼
│   ├── api/
│   │   └── [[path]].py         # 處理 API 請求的 Worker (Catch-all Route)
│   └── update_data_worker.py   # 處理定時資料更新的 Worker
│
├── public/                     # 所有靜態資源 (HTML, JS, CSS, 圖片)
│   ├── index.html              # 主要的前端頁面 (原 backtest.html)
│   └── js/                     # JavaScript 檔案
│
├── src/                        # 原始的 Python 後端原始碼
│   ├── api/                    # 原本的 api/ 目錄
│   └── update_data.py          # 原本的資料更新腳本
│
├── .gitignore                  # Git 忽略清單
├── requirements.txt            # Python 依賴套件
└── wrangler.toml               # Cloudflare 設定檔 (取代 vercel.json)

部署到 Cloudflare
前置作業
安裝 Node.js: Cloudflare 的命令行工具 wrangler 需要 Node.js 環境。

安裝 Wrangler CLI:

npm install -g wrangler

登入 Cloudflare:

wrangler login

這會打開瀏覽器要求您授權。

結構調整步驟
在部署之前，請務必依照以下步驟調整您的專案目錄：

刪除舊的設定檔:

rm vercel.json

rm -rf .github (如果您不想保留舊的 GitHub Action)

建立新目錄:

mkdir functions

mkdir functions/api

mkdir src

移動檔案和目錄:

移動後端原始碼: mv api src/

移動資料更新腳本: mv update_data.py src/

移動前端 HTML: mv backtest.html public/index.html

建立新的設定檔:

將本文件提供的 wrangler.toml 內容儲存到專案根目錄。

將 functions/api/[[path]].py 和 functions/update_data_worker.py 儲存到對應位置。

更新 .gitignore 檔案。

部署指令
完成結構調整後，在專案根目錄執行以下指令即可部署：

wrangler pages deploy public

Wrangler 會自動：

上傳 public 目錄中的靜態檔案。

偵測到 functions 目錄，並將其部署為 Cloudflare Workers。

讀取 requirements.txt 並為 Python Workers 安裝依賴。

根據 wrangler.toml 中的設定，建立 API 路由和定時任務。

部署成功後，Wrangler 會提供您一個公開的網址！
