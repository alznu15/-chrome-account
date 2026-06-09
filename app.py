import os
import time
import zipfile
import subprocess
import shutil
from threading import Timer
from flask import Flask, request, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "super_secret_history_key")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# --- 參數設定 ---
IDLE_LIMIT = 15 * 60         
BUFFER_TIME = 15             
UPLOAD_TRIGGER = IDLE_LIMIT - BUFFER_TIME  
SHIELD_FILE_NAME = 'History_Project_Research_Notes_Backup.zip'
LOCAL_COOKIE_DIR = '/app/chromium_profile'  
SCOPES = ['https://www.googleapis.com/auth/drive']

last_activity_time = time.time()
uploaded_file_id = None  
user_credentials = None  
chrome_process = None  

def get_redirect_uri():
    # 🎯 直接綁定你在 Google Console 設定好的 Render 專屬網址
    return 'https://chrome-account.onrender.com/oauth2callback'

def get_drive_service():
    if not user_credentials: return None
    return build('drive', 'v3', credentials=user_credentials)

def download_and_cleanup_from_drive():
    service = get_drive_service()
    if not service: return
    try:
        results = service.files().list(
            q=f"name='{SHIELD_FILE_NAME}' and trashed=false",
            fields="files(id, name)"
        ).execute()
        files = results.get('files', [])
        
        if files:
            file_id = files[0]['id']
            request_media = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request_media)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            if os.path.exists(LOCAL_COOKIE_DIR):
                shutil.rmtree(LOCAL_COOKIE_DIR)
            os.makedirs(LOCAL_COOKIE_DIR, exist_ok=True)
            
            fh.seek(0)
            with zipfile.ZipFile(fh, 'r') as zip_ref:
                zip_ref.extractall(LOCAL_COOKIE_DIR)
            
            service.files().delete(fileId=file_id).execute()
            print("✅ 成功拉回歷史驗證 Cookie 與個人 Profile！")
    except Exception as e:
        print(f"雲端載入錯誤: {e}")

    launch_cloud_chrome()

def launch_cloud_chrome():
    global chrome_process
    try:
        if chrome_process and chrome_process.poll() is None:
            chrome_process.terminate()
            chrome_process.wait()

        print("🖥️ 正在配置虛擬螢幕與桌面環境...")
        subprocess.Popen(["Xvfb", ":1", "-screen", "0", "1280x720x24"])
        time.sleep(1)
        
        subprocess.Popen(["fluxbox"])
        subprocess.Popen(["x11vnc", "-display", ":1", "-nopw", "-forever", "-shared"])
        
        print("🖥️ 啟動 Websocket 影像轉發 (Port 6080)...")
        subprocess.Popen(["websockify", "--web", "/usr/share/novnc", "6080", "127.0.0.1:5900"])
        
        os.makedirs(LOCAL_COOKIE_DIR, exist_ok=True)
        print("🚀 啟動 Chromium 瀏覽器核心...")
        chrome_process = subprocess.Popen([
            "chromium-browser",
            f"--user-data-dir={LOCAL_COOKIE_DIR}",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--start-maximized",
            "https://www.google.com"
        ])
    except Exception as e:
        print(f"啟動瀏覽器錯誤: {e}")

def upload_to_school_drive():
    global uploaded_file_id, chrome_process
    service = get_drive_service()
    if not service or not os.path.exists(LOCAL_COOKIE_DIR): return
    
    if chrome_process and chrome_process.poll() is None:
        chrome_process.terminate()
        chrome_process.wait()
        
    print("🚨 [系統即將休眠] 打包 Chrome 狀態上傳至 Drive...")
    try:
        zip_file_path = '/tmp/temp_backup.zip'
        with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for root, dirs, files in os.walk(LOCAL_COOKIE_DIR):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, LOCAL_COOKIE_DIR)
                    zip_file.write(full_path, rel_path)
        
        file_metadata = {'name': SHIELD_FILE_NAME, 'mimeType': 'application/zip'}
        media = MediaFileUpload(zip_file_path, mimetype='application/zip', resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        uploaded_file_id = file.get('id')
        
        if os.path.exists(zip_file_path): os.remove(zip_file_path)
    except Exception as e:
        print(f"上傳備份錯誤: {e}")

def cleanup_premature_backup():
    global uploaded_file_id
    service = get_drive_service()
    if service and uploaded_file_id:
        try:
            service.files().delete(fileId=uploaded_file_id).execute()
            uploaded_file_id = None
            if not chrome_process or chrome_process.poll() is not None:
                launch_cloud_chrome()
        except Exception as e:
            print(f"大掃除錯誤: {e}")

def start_countdown_monitor():
    global last_activity_time
    elapsed = time.time() - last_activity_time
    if elapsed >= UPLOAD_TRIGGER and elapsed < IDLE_LIMIT and not uploaded_file_id:
        upload_to_school_drive()
    t = Timer(5, start_countdown_monitor)
    t.daemon = True
    t.start()

@app.route('/')
def home():
    global last_activity_time, user_credentials
    last_activity_time = time.time()  
    cleanup_premature_backup()       
    
    if not user_credentials:
        return '''
        <style>
            body { background-color: #0f172a; color: #f8fafc; font-family: sans-serif; text-align: center; padding-top: 100px; }
            a { display: inline-block; background-color: #22c55e; color: white; padding: 12px 24px; text-transform: uppercase; text-decoration: none; border-radius: 6px; font-weight: bold; margin-top: 20px; }
            a:hover { background-color: #16a34a; }
        </style>
        <h2>🟢 歷史專案同步系統 (Render 穩定版)</h2>
        <a href="/auth">👉 點此與學校雲端空間進行安全串接</a>
        '''
    
    return """
    <html>
        <head><title>History Research Sync Center</title></head>
        <body style="background-color: #0f172a; color: #f8fafc; font-family: Arial; padding: 20px; text-align: center; margin: 0;">
            <h1 style="color: #22c55e; margin: 10px 0;">🟢 歷史研究中控台 授權成功</h1>
            <div style="max-width: 1280px; margin: 20px auto; border: 4px solid #334155; border-radius: 8px; overflow: hidden; background: #000;">
                <iframe src="/vnc/vnc.html?autoconnect=true&resize=scale&path=vnc/websockify" style="width: 100%; height: 720px; border: none;"></iframe>
            </div>
        </body>
    </html>
    """

@app.route('/auth')
def auth():
    try:
        flow = Flow.from_client_secrets_file('client_secret.json', scopes=SCOPES, redirect_uri=get_redirect_uri())
        authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
        return redirect(authorization_url)
    except Exception as e:
        return f"<h2 style='color:red;'>系統錯誤：找不到憑證</h2><p>錯誤細節: {str(e)}</p>"

@app.route('/oauth2callback')
def oauth2callback():
    global user_credentials
    flow = Flow.from_client_secrets_file('client_secret.json', scopes=SCOPES, redirect_uri=get_redirect_uri())
    
    # 解決 HTTPS 代理降級問題
    current_url = request.url
    if current_url.startswith("http://"):
        current_url = current_url.replace("http://", "https://")
        
    flow.fetch_token(authorization_response=current_url)
    user_credentials = flow.credentials
    download_and_cleanup_from_drive()
    return redirect(url_for('home'))

def start_internal_proxy():
    """動態生成 Nginx 設定檔，解決 Render 單一 Port 限制"""
    # 抓取 Render 平台給的外部 Port (預設通常是 10000)
    render_port = os.environ.get("PORT", "10000")
    print(f"🔗 正在綁定 Render 對外 Port: {render_port}")
    
    nginx_conf = f"""
    events {{ worker_connections 1024; }}
    http {{
        include /etc/nginx/mime.types;
        server {{
            listen {render_port};
            
            # 路由 1: 桌面影像串流轉發到 6080
            location /vnc/ {{
                proxy_pass http://127.0.0.1:6080/;
                proxy_http_version 1.1;
                proxy_set_header Upgrade $http_upgrade;
                proxy_set_header Connection "Upgrade";
            }}
            
            # 路由 2: 中控網頁轉發到 Flask (5000)
            location / {{
                proxy_pass http://127.0.0.1:5000/;
                proxy_set_header Host $host;
                proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                proxy_set_header X-Forwarded-Proto $scheme;
            }}
        }}
    }}
    """
    with open("/tmp/render_nginx.conf", "w") as f:
        f.write(nginx_conf)
    
    # 在背景啟動 Nginx 代理器
    subprocess.Popen(["nginx", "-c", "/tmp/render_nginx.conf"])

if __name__ == '__main__':
    start_countdown_monitor()
    
    # 啟動內部 Nginx 路由，負責接手 Render 進來的所有流量
    start_internal_proxy()
    
    # Flask 安穩地跑在內部 5000 Port 即可
    app.run(host='127.0.0.1', port=5000)
