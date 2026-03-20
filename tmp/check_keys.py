import sys
import os
sys.path.append(os.getcwd())
from app import create_app, db
from app.models import APIKeyTracker

app = create_app()
with app.app_context():
    keys = APIKeyTracker.query.all()
    print("--- API KEY AUDIT START ---")
    for k in keys:
        print(f"ID: {k.id} | Provider: {k.provider} | Key: {k.api_key[:15]}... | Status: {k.status} | Error: {k.error_message}")
    print("--- API KEY AUDIT END ---")
