import traceback
import sys
import os

boot_error = None
app = None

try:
    from app import create_app
    app = create_app()
except Exception:
    boot_error = traceback.format_exc()

if not app:
    from flask import Flask
    app = Flask(__name__)

    @app.route('/')
    @app.route('/<path:path>')
    def catch_all(path=None):
        return f"""
        <div style='padding:40px; font-family:sans-serif; line-height:1.6; max-width:800px; margin:0 auto; color:#333;'>
            <h1 style='color:#e74c3c;'>應用程式啟動失敗 (Boot Crash)</h1>
            <p>Vercel 在啟動 Flask 應用程式時發生了嚴重錯誤。</p>
            <div style='background:#f9f9f9; border:1px solid #ddd; padding:20px; border-radius:8px; margin:20px 0;'>
                <strong>Python Version:</strong> {sys.version}<br>
                <strong>Platform:</strong> {sys.platform}<br>
                <strong>CWD:</strong> {os.getcwd()}<br>
                <strong>PATH has app:</strong> {'app' in str(os.listdir('.'))}<br>
                <hr>
                <strong>Traceback:</strong>
                <pre style='white-space:pre-wrap; font-size:0.9em; margin-top:10px;'>{boot_error}</pre>
            </div>
        </div>
        """, 500

if __name__ == '__main__':
    app.run(debug=True)
