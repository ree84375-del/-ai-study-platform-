from app import create_app, db
from app.models import APIKeyTracker
import os

app = create_app()
with app.app_context():
    try:
        from collections import defaultdict
        provider_keys = defaultdict(list)
        all_records = APIKeyTracker.query.all()
        for r in all_records:
            provider_keys[r.provider.lower()].append(r.api_key)
        
        for provider, keys in provider_keys.items():
            print(f"{provider.upper()}_ALL_KEYS={','.join(keys)}")
            if len(keys) == 1:
                print(f"{provider.upper()}_API_KEY={keys[0]}")
    except Exception as e:
        print(f"Error: {e}")
