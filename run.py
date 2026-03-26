# DIAGNOSTIC RUN.PY - Tests if Python works on Vercel at all
# Does NOT import Flask or any dependency - pure stdlib only
import sys
import os
import traceback

# Phase 1: Test bare Python
diagnostics = []
diagnostics.append(f"Python: {sys.version}")
diagnostics.append(f"Platform: {sys.platform}")
diagnostics.append(f"CWD: {os.getcwd()}")
diagnostics.append(f"Files: {sorted(os.listdir('.'))}")

# Phase 2: Test if Flask can be imported
flask_ok = False
flask_error = None
try:
    from flask import Flask
    flask_ok = True
    diagnostics.append("Flask import: OK")
except Exception as e:
    flask_error = traceback.format_exc()
    diagnostics.append(f"Flask import: FAILED - {e}")

# Phase 3: Test if app can be imported
app_error = None
real_app = None
if flask_ok:
    try:
        from app import create_app
        real_app = create_app()
        diagnostics.append("App init: OK")
    except Exception as e:
        app_error = traceback.format_exc()
        diagnostics.append(f"App init: FAILED - {e}")

# Build the WSGI app
if real_app:
    app = real_app
else:
    if flask_ok:
        from flask import Flask
        app = Flask(__name__)
        
        @app.route('/')
        @app.route('/<path:path>')
        def catch_all(path=None):
            error_html = ""
            if app_error:
                error_html = f"<h2>App Init Error</h2><pre style='white-space:pre-wrap;overflow:auto;background:#f5f5f5;padding:15px;border-radius:8px;font-size:13px;'>{app_error}</pre>"
            return f"""<div style='padding:40px;font-family:sans-serif;max-width:900px;margin:0 auto;'>
                <h1 style='color:#e74c3c;'>Boot Crash Diagnostics</h1>
                <ul>{''.join(f'<li>{d}</li>' for d in diagnostics)}</ul>
                {error_html}
            </div>""", 500
    else:
        # Flask itself failed to import - use raw WSGI
        def app(environ, start_response):
            status = '500 Internal Server Error'
            body = f"""<html><body style='padding:40px;font-family:sans-serif;max-width:900px;margin:0 auto;'>
                <h1 style='color:#e74c3c;'>Flask Import Failed</h1>
                <ul>{''.join(f'<li>{d}</li>' for d in diagnostics)}</ul>
                <h2>Flask Error</h2>
                <pre style='white-space:pre-wrap;overflow:auto;background:#f5f5f5;padding:15px;'>{flask_error}</pre>
            </body></html>"""
            response_headers = [('Content-Type', 'text/html'), ('Content-Length', str(len(body)))]
            start_response(status, response_headers)
            return [body.encode('utf-8')]

if __name__ == '__main__':
    if hasattr(app, 'run'):
        app.run(debug=True)
