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

部署選項一：完全線上化部署 (透過 GitHub)
這個方法不需要在本機安裝任何工具，所有操作都在 GitHub 和 Cloudflare 網站上完成。

步驟 1: 在 GitHub 上準備儲存庫
Fork 專案: 如果您還沒有這個專案的儲存庫，請先將其 Fork 到您自己的 GitHub 帳號下。

線上調整結構: 直接在您的 GitHub 儲存庫頁面進行以下操作：

建立 src 目錄並移動後端程式碼:

在根目錄點擊 Add file -> Create new file。

在檔名欄位輸入 src/api/index.py，然後將原始 api/index.py 的內容貼上。這會自動建立 src 和 src/api 目錄。

重複此步驟，將 api/ 目錄下的所有 Python 檔案都移動到新的 src/api/ 目錄下。

同樣地，建立 src/update_data.py 並貼上內容。

建立 functions 目錄與 Worker 檔案:

使用同樣的方法，建立 functions/api/[[path]].py 和 functions/update_data_worker.py，並將我先前提供的程式碼貼入。

移動前端頁面:

找到 backtest.html，點擊編輯，將其檔名更改為 public/index.html。GitHub 會自動處理移動。

建立 wrangler.toml:

在根目錄建立 wrangler.toml 檔案，並貼上設定內容。

刪除舊檔案:

刪除根目錄下的 vercel.json、舊的 api 目錄以及 .github 目錄。

步驟 2: 連接到 Cloudflare Pages
登入您的 Cloudflare 儀表板。

在側邊欄中，前往 Workers & Pages。

點擊 Create application -> Pages -> Connect to Git。

選擇您剛剛準備好的 GitHub 儲存庫並授權。

步驟 3: 設定建置與部署
在 "Set up builds and deployments" 頁面，進行以下設定：

Production branch: 選擇 main (或您的主要分支)。

Build command: 留空。我們不需要建置步驟。

Build output directory: 選擇 /public。

環境變數: (非必要) 如果您的應用需要，可以在這裡設定。

Cloudflare 會自動偵測到 wrangler.toml 和 functions 目錄，並知道這是一個包含靜態網站和 Python Workers 的專案。

步驟 4: 儲存並部署
點擊 Save and Deploy。

Cloudflare 將從 GitHub 拉取您的程式碼，部署 public 目錄中的檔案，並設定好您的 API 和定時任務。

部署完成後，您會得到一個 .pages.dev 的公開網址！

部署選項二：使用本機終端機 (Wrangler CLI)
這個方法適合習慣使用命令列工具的開發者。

前置作業
安裝 Node.js: Cloudflare 的命令行工具 wrangler 需要 Node.js 環境。

安裝 Wrangler CLI:

npm install -g wrangler

登入 Cloudflare:

wrangler login

這會打開瀏覽器要求您授權。

結構調整步驟
在部署之前，請務必依照「專案結構」一節的說明，在您的本機電腦上調整好專案目錄。

部署指令
完成結構調整後，在專案根目錄執行以下指令即可部署：

wrangler pages deploy public

Wrangler 會自動上傳檔案、部署 Workers 並設定路由。
