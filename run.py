import sys
import os
import traceback

# Try to boot the real app
app = None
boot_error = None

try:
    from app import create_app
    app = create_app()
except Exception:
    boot_error = traceback.format_exc()

# Fallback error page if app fails to start
if not app:
    from flask import Flask
    app = Flask(__name__)

    @app.route('/')
    @app.route('/<path:path>')
    def catch_all(path=None):
        return f"""<div style='padding:40px;font-family:sans-serif;max-width:900px;margin:0 auto;'>
            <h1 style='color:#e74c3c;'>應用程式啟動失敗 (Boot Crash)</h1>
            <p><b>Python:</b> {sys.version}</p>
            <pre style='white-space:pre-wrap;overflow:auto;background:#f5f5f5;padding:15px;border-radius:8px;font-size:13px;'>{boot_error}</pre>
        </div>""", 500

if __name__ == '__main__':
    app.run(debug=True)
