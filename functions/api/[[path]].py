# functions/api/[[path]].py
# 這個檔案是 Cloudflare Python Worker，它會攔截所有 /api/* 的請求。
# 它扮演一個橋樑的角色，將傳入的請求轉換為 Flask (WSGI) 可以理解的格式。

import sys
import os
from io import BytesIO
from urllib.parse import urlparse

# 導入 Cloudflare 環境中可用的 Web-standard API
from js import Response, Headers

# --- 專案結構設定 ---
# 將 'src' 目錄添加到 Python 的搜尋路徑中。
# 這樣我們才能正確導入位於 src/api/ 的 Flask 應用。
# 我們的專案結構會是：
# /
# ├── functions/
# ├── src/
# │   └── api/
# └── ...
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# 從我們搬移到 src/api/ 的原始程式碼中導入 Flask app
from api.index import app as flask_app

# --- Cloudflare Worker 主處理函式 ---
async def on_fetch(request, env):
    """
    每個 API 請求都會進入這個函式。
    """
    try:
        # --- WSGI 橋接器 ---
        # 將 Cloudflare 的 Request 物件轉換為 Flask/Werkzeug 需要的 WSGI 環境變數。
        parsed_url = urlparse(request.url)

        # 複製請求主體，因為它只能被讀取一次。
        request_body_bytes = await request.clone().bytes()

        environ = {
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': parsed_url.scheme,
            'wsgi.input': BytesIO(request_body_bytes),
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'REQUEST_METHOD': request.method,
            'PATH_INFO': parsed_url.path,
            'QUERY_STRING': parsed_url.query,
            'CONTENT_TYPE': request.headers.get('Content-Type', ''),
            'CONTENT_LENGTH': str(len(request_body_bytes)),
            'SERVER_NAME': parsed_url.hostname,
            'SERVER_PORT': str(parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)),
            'SERVER_PROTOCOL': 'HTTP/1.1',
        }

        # 將 HTTP 標頭加入環境變數
        for key, value in request.headers.items():
            key = 'HTTP_' + key.upper().replace('-', '_')
            environ[key] = value

        # Flask 會呼叫這個函式來設定回應的狀態和標頭
        response_headers = []
        response_status = ""
        def start_response(status, headers, exc_info=None):
            nonlocal response_status, response_headers
            response_status = status
            response_headers = headers

        # --- 呼叫 Flask 應用 ---
        result = flask_app(environ, start_response)
        body = b"".join(result)
        
        # --- 建立 Cloudflare 回應 ---
        status_code = int(response_status.split(' ')[0])
        
        # 建立新的 Headers 物件
        headers = Headers()
        for key, value in response_headers:
            headers.append(key, value)
        
        # 確保 CORS 標頭存在，以便前端可以呼叫 API
        headers.set('Access-Control-Allow-Origin', '*')
        headers.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        headers.set('Access-Control-Allow-Headers', 'Content-Type')

        return Response(body, status=status_code, headers=headers)

    except Exception as e:
        # 錯誤處理
        error_message = f"Worker Error: {type(e).__name__}: {e}"
        print(error_message)
        return Response(error_message, status=500)

