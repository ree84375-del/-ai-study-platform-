import os
from flask import render_template
from app import create_app, db

app = create_app()
app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for testing

with app.app_context():
    template_dir = os.path.join(app.root_path, 'templates')
    for root, dirs, files in os.walk(template_dir):
        for file in files:
            if file.endswith('.html'):
                rel_path = os.path.relpath(os.path.join(root, file), template_dir)
                try:
                    # just try parsing to find syntax errors
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        source = f.read()
                    app.jinja_env.parse(source)
                    print(f"OK (Parse): {rel_path}")
                except Exception as e:
                    print(f"ERROR (Parse) in {rel_path}: {e}")
