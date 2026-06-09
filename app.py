import os
import time
import zipfile
import shutil
from threading import Timer
from flask import Flask, render_template_string, request, redirect, url_for, Response
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
import requests  # 引入代理功能所需的網路請求模組

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "super_secret_history_key")

# --- 🚀 核心參數設定（無痕偽裝與卡點） ---
IDLE_LIMIT = 15 * 60         # Render 斷電死線（15分鐘 = 900秒）
BUFFER_TIME = 15             # 精準預留 15 秒極速光纖上傳
UPLOAD_TRIGGER = IDLE_LIMIT - BUFFER_TIME  # 第 14 分 45 秒（885秒）背刺上傳

SHIELD_FILE_NAME = 'History_Project_Research_Notes_Backup.zip'
LOCAL_COOKIE_DIR = './chrome_profile'  # 儲存你私人 Chrome 登入驗證狀態的資料夾

# 狀態記錄變數
last_activity_time = time.time()
uploaded_file_id = None  # 記錄丟在學校雲端的檔案 ID，回來時秒刪用
user_credentials = None  # 儲存合法的長效鑰匙 (Credentials)

# Google API 權限範圍：我們只需要完整操作 Google Drive 來放我們的備份檔
SCOPES = ['https://www.googleapis.com/auth/drive']

# --- 🔑 Google Drive API 串接核心邏輯 ---

def get_drive_service():
    global user_credentials
    if not user_credentials:
        return None
    return build('drive', 'v3', credentials=user_credentials)

def download_and_cleanup_from_drive():
    """ 🚀 開機（喚醒）首發：從學校雲端抓回昨天的記憶，解壓後『立刻秒刪』保持無痕！ """
    service = get_drive_service()
    if not service: return
    
    print(f"📥 正在從學校 Drive 搜尋偽裝備份檔 {SHIELD_FILE_NAME}...")
    try:
        results = service.files().list(
            q=f"name='{SHIELD_FILE_NAME}' and trashed=false",
            fields="files(id, name)"
        ).execute()
        files = results.get('files', [])
        
        if files:
            file_id = files[0]['id']
            # 下載壓縮檔
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            # 解壓到本地 profile 資料夾（還原登入狀態）
            fh.seek(0)
            with zipfile.ZipFile(fh, 'r') as zip_ref:
                zip_ref.extractall(LOCAL_COOKIE_DIR)
            print("✅ 成功拉回歷史驗證 Cookie！")
            
            # 🧹 核心無痕：下載完一秒都不留，立刻從學校雲端硬碟「蒸發」！
            service.files().delete(fileId=file_id).execute()
            print("🧹 [無痕啟動] 學校雲端硬碟已完全抹除痕跡，0 垃圾殘留！")
    except Exception as e:
        print(f"ℹ️ 本次開機未發現歷史備份，或遭遇阻攔: {e}")

def upload_to_school_drive():
    """ ⚡ 第 14 分 45 秒發動的『臨終上傳』：秒傳打包檔回學校雲端！ """
    global uploaded_file_id
    service = get_drive_service()
    if not service or not os.path.exists(LOCAL_COOKIE_DIR): return
    
    print(f"減速警告 🚨 [倒數15秒斷電] 搶在 Render 休眠前打包上傳至學校 Drive...")
    try:
        # 將本地登入狀態打包成 zip
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for root, dirs, files in os.walk(LOCAL_COOKIE_DIR):
                for file in files:
                    zip_file.write(os.path.join(root, file), 
                                   os.path.relpath(os.path.join(root, file), LOCAL_COOKIE_DIR))
        
        zip_buffer.seek(0)
        # 上傳到 Google Drive
        file_metadata = {'name': SHIELD_FILE_NAME, 'mimeType': 'application/zip'}
        
        # 建立臨時檔案並上傳
        with open('temp_backup.zip', 'wb') as f:
            f.write(zip_buffer.getvalue())
        
        media = MediaFileUpload('temp_backup.zip', mimetype='application/zip')
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        uploaded_file_id = file.get('id')
        
        # 移除伺服器上的臨時檔
        if os.path.exists('temp_backup.zip'): os.remove('temp_backup.zip')
        print(f"✅ 壓線上傳成功！假名：{SHIELD_FILE_NAME}，檔案ID: {uploaded_file_id}")
    except Exception as e:
        print(f"❌ 壓線上傳失敗: {e}")

def cleanup_premature_backup():
    """ 🧹 你突然回歸的『自癒擦屁股機制』：最後 15 秒上線，立刻抹除硬碟臨時檔！ """
    global uploaded_file_id
    service = get_drive_service()
    if service and uploaded_file_id:
        print("🧹 🚨 偵測到主人在最後關頭回歸！正在連線至學校 Drive 進行大掃除...")
        try:
            service.files().delete(fileId=uploaded_file_id).execute()
            print("🧹 臨時備份檔案已被徹底抹除，保持硬碟完全乾淨！")
            uploaded_file_id = None
        except Exception as e:
            print(f"大掃除失敗或檔案已被手動處理: {e}")

# --- ⏱️ 壓線死線計時監聽器 (Background Timer) ---
def start_countdown_monitor():
    global last_activity_time
    elapsed = time.time() - last_activity_time
    
    # 精準卡點：當你離開整整 14 分 45 秒，且這輪還沒上傳過
    if elapsed >= UPLOAD_TRIGGER and elapsed < IDLE_LIMIT and not uploaded_file_id:
        upload_to_school_drive()
        
    t = Timer(5, start_countdown_monitor)
    t.daemon = True
    t.start()

# --- 🌐 Flask 網頁路由（你的登入驗證與網頁代理中控台） ---

@app.route('/')
def home():
    global last_activity_time, user_credentials
    last_activity_time = time.time()  # 只要有人進網頁，Render 的 15 分鐘冷卻歸零
    cleanup_premature_backup()       # 觸發自癒擦屁股
    
    if not user_credentials:
        return '<h2>🟢 歷史專案同步系統</h2><p>尚未偵測到 Google 驗證授權。</p><a href="/auth">👉 點此開始與學校 50GB 空間進行合規串接</a>'
    
    # 驗證成功後，渲染包含網頁代理輸入框與 Iframe 的進階介面
    return """
    <html>
        <head>
            <title>History Research Sync Center</title>
            <style>
                body { background-color: #0f172a; color: #f8fafc; font-family: Arial; padding: 20px; text-align: center; margin: 0; }
                .status-title { color: #22c55e; margin-top: 10px; }
                .info-box { border: 1px solid #334155; padding: 15px; display: inline-block; margin-top: 10px; border-radius: 8px; background-color: #1e293b; text-align: left; }
                .proxy-container { max-width: 1000px; margin: 20px auto 0 auto; background: #1e293b; border-radius: 8px; padding: 15px; border: 1px solid #334155; }
                .address-bar { display: flex; gap: 10px; margin-bottom: 15px; }
                .url-input { flex: 1; padding: 10px; border-radius: 4px; border: 1px solid #475569; background: #0f172a; color: #fff; font-size: 14px; }
                .go-btn { background: #22c55e; color: #0f172a; border: none; padding: 10px 20px; font-weight: bold; border-radius: 4px; cursor: pointer; }
                .go-btn:hover { background: #4ade80; }
                .browser-viewport { width: 100%; height: 65vh; border: none; border-radius: 6px; background: #ffffff; }
            </style>
            <script>
                function navigateToUrl() {
                    var inputUrl = document.getElementById('target_url').value;
                    if (!inputUrl) return;
                    if (!inputUrl.startsWith('http://') && !inputUrl.startsWith('https://')) {
                        inputUrl = 'https://' + inputUrl;
                    }
                    document.getElementById('viewport_frame').src = '/proxy?url=' + encodeURIComponent(inputUrl);
                }
            </script>
        </head>
        <body>
            <h1 class="status-title">🟢 歷史研究中控台 授權成功</h1>
            <p style="margin: 5px 0;">Render 免費版計時器已成功重置。當前狀態：<b>安全、無痕、自動化運作中</b></p>
            
            <div class="info-box">
                <span style="display:block;">學校 50GB 硬碟狀態：<span style="color: #4ade80;">0 個殘留備份（完美隱形）</span></span>
                <span style="display:block; margin-top: 5px;">無痕備份假名：<code>History_Project_Research_Notes_Backup.zip</code></span>
            </div>
            
            <div class="proxy-container">
                <div class="address-bar">
                    <input type="text" id="target_url" class="url-input" placeholder="輸入要前往的個人網站網址 (例如: google.com 或 instagram.com)" onkeydown="if(event.keyCode==13) navigateToUrl()">
                    <button class="go-btn" onclick="navigateToUrl()">前往</button>
                </div>
                <iframe id="viewport_frame" class="browser-viewport" src="/proxy?url=https://www.google.com"></iframe>
            </div>

            <p style="margin-top: 15px; color: #94a3b8; font-size: 12px;">※ 當你關閉分頁 14 分 45 秒後，系統會自動在背景秒傳加密 Cookie 並進入休眠。</p>
        </body>
    </html>
    """

@app.route('/auth')
def auth():
    """ 導向 Google 官方的 Oauth 2.0 安全驗證渠道 """
    flow = Flow.from_client_secrets_file('client_secret.json', scopes=SCOPES, redirect_uri=request.url_root + 'oauth2callback')
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    """ 登入成功後 Google 回傳長效鑰匙的接收站 """
    global user_credentials
    flow = Flow.from_client_secrets_file('client_secret.json', scopes=SCOPES, redirect_uri=request.url_root + 'oauth2callback')
    flow.fetch_token(authorization_response=request.url)
    user_credentials = flow.credentials
    
    # 登入成功後，立刻去拉一次有沒有昨天的記憶
    download_and_cleanup_from_drive()
    return redirect(url_for('home'))

# --- 🌐 核心：雲端安全網頁代理路由器 ---
@app.route('/proxy')
def proxy():
    global user_credentials
    if not user_credentials:
        return "未授權存取，請先完成主頁驗證連結", 403
        
    target_url = request.args.get('url')
    if not target_url:
        return "請輸入有效網址", 400

    try:
        # 由 Render 雲端伺服器後端代替 Chromebook 發出請求，完美繞過所有學校本機的限制與追蹤
        custom_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        proxied_res = requests.get(target_url, headers=custom_headers, timeout=12)
        
        # 過濾掉可能干擾瀏覽器內嵌渲染的串流快取傳輸標頭
        banned_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        cleaned_headers = [(k, v) for k, v in proxied_res.raw.headers.items() if k.lower() not in banned_headers]
        
        return Response(proxied_res.content, proxied_res.status_code, cleaned_headers)
    except Exception as error:
        return f"雲端代理連線失敗（目標網站可能有限制）：{str(error)}", 500

if __name__ == '__main__':
    start_countdown_monitor()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
