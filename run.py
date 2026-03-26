# Phase 1: Absolute minimum test - does Python even work on this Vercel project?
from flask import Flask

app = Flask(__name__)

@app.route('/')
@app.route('/<path:path>')
def catch_all(path=None):
    import sys
    import os
    
    # Phase 2: Try importing the actual app and catch ANY error
    boot_error = None
    try:
        from app import create_app
        real_app = create_app()
        # If we get here, the app works - redirect to home
        return real_app.make_response(real_app.view_functions.get('main.home', lambda: 'OK')())
    except Exception as e:
        import traceback
        boot_error = traceback.format_exc()
    
    return f"""
    <div style='padding:40px; font-family:sans-serif; line-height:1.6; max-width:900px; margin:0 auto; color:#333;'>
        <h1 style='color:#e74c3c;'>應用程式啟動失敗 (Boot Crash)</h1>
        <p><strong>Python:</strong> {sys.version}</p>
        <p><strong>Platform:</strong> {sys.platform}</p>
        <p><strong>CWD:</strong> {os.getcwd()}</p>
        <p><strong>Files in CWD:</strong> {', '.join(sorted(os.listdir('.')))}</p>
        <div style='background:#f9f9f9; border:1px solid #ddd; padding:20px; border-radius:8px; margin:20px 0; overflow:auto;'>
            <strong>Traceback:</strong>
            <pre style='white-space:pre-wrap; font-size:0.85em; margin-top:10px;'>{boot_error}</pre>
        </div>
    </div>
    """, 500

if __name__ == '__main__':
    app.run(debug=True)
