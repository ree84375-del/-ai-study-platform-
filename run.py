import sys
import os
import traceback

# Diagnostic info captured at module level
_boot_diag = {
    'python': sys.version,
    'platform': sys.platform,
    'cwd': os.getcwd(),
}

# Phase 1: Try importing Flask
try:
    from flask import Flask
    _boot_diag['flask'] = 'OK'
except Exception as e:
    _boot_diag['flask'] = traceback.format_exc()

# Phase 2: Try creating the actual app
_real_app = None
_boot_error = None
try:
    from app import create_app
    _real_app = create_app()
    _boot_diag['app'] = 'OK'
except Exception as e:
    _boot_error = traceback.format_exc()
    _boot_diag['app'] = _boot_error

# Phase 3: Build final app
if _real_app:
    app = _real_app
elif _boot_diag.get('flask') == 'OK':
    app = Flask(__name__)

    @app.route('/')
    @app.route('/<path:path>')
    def catch_all(path=None):
        items = ''.join(f'<li><b>{k}:</b> {v}</li>' for k, v in _boot_diag.items())
        error_block = ""
        if _boot_error:
            error_block = f"<pre style='white-space:pre-wrap;overflow:auto;background:#f5f5f5;padding:15px;border-radius:8px;font-size:13px;max-height:600px;'>{_boot_error}</pre>"
        return f"""<div style='padding:40px;font-family:sans-serif;max-width:900px;margin:0 auto;'>
            <h1 style='color:#e74c3c;'>應用程式啟動失敗 (Boot Crash)</h1>
            <ul>{items}</ul>
            {error_block}
        </div>""", 500
else:
    # Raw WSGI - Flask itself failed
    _diag_html = ''.join(f'<li><b>{k}:</b> <pre>{v}</pre></li>' for k, v in _boot_diag.items())
    _body = f"<html><body style='padding:40px;font-family:sans-serif;'><h1>Fatal: Flask Import Failed</h1><ul>{_diag_html}</ul></body></html>".encode('utf-8')
    
    def app(environ, start_response):
        start_response('500 Internal Server Error', [('Content-Type', 'text/html'), ('Content-Length', str(len(_body)))])
        return [_body]

if __name__ == '__main__':
    if hasattr(app, 'run'):
        app.run(debug=True)
