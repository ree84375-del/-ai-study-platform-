import traceback
from flask import Flask

try:
    from app import create_app
    app = create_app()
except Exception:
    error_trace = traceback.format_exc()
    app = Flask(__name__)
    
    @app.route('/')
    @app.route('/<path:path>')
    def catch_all(path=None):
        return f"""
        <div style='padding:40px; font-family:sans-serif; line-height:1.6; max-width:800px; margin:0 auto; color:#333;'>
            <h1 style='color:#e74c3c;'>應用程式啟動失敗 (Boot Crash)</h1>
            <p>Vercel 在啟動 Flask 應用程式時發生了嚴重錯誤。這通常是語法錯誤或缺少依賴導致的。</p>
            <div style='background:#f9f9f9; border:1px solid #ddd; padding:20px; border-radius:8px; margin:20px 0;'>
                <strong>Traceback:</strong>
                <pre style='white-space:pre-wrap; font-size:0.9em; margin-top:10px;'>{error_trace}</pre>
            </div>
        </div>
        """, 500

if __name__ == '__main__':
    app.run(debug=True)
