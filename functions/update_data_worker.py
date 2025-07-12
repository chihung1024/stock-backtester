# functions/update_data_worker.py
# 這個 Worker 用於處理由 wrangler.toml 中 [triggers] crons 設定的定時任務。

import sys
import os

# 將 'src' 目錄添加到 Python 的搜尋路徑中
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# 導入原始的更新腳本中的主函式
# 注意：我們假設 `update_data.py` 中有一個 `main()` 函式
try:
    from update_data import main as run_update_main
except ImportError:
    # 如果導入失敗，定義一個備用函式以避免 Worker 崩潰
    def run_update_main():
        print("錯誤：無法從 'src/update_data.py' 導入 'main' 函式。")
        print("請確保該檔案存在且包含一個名為 'main' 的函式。")

async def scheduled(event, env, ctx):
    """
    由 Cron 觸發器定時呼叫的處理函式。
    """
    print(f"定時任務觸發於：{event.scheduledTime}")
    try:
        print("開始執行資料更新腳本...")
        # 執行更新資料的邏輯
        run_update_main()
        print("資料更新腳本執行完畢。")
    except Exception as e:
        # 捕捉並記錄執行過程中的任何錯誤
        error_message = f"執行定時更新任務時發生錯誤：{e}"
        print(error_message)

