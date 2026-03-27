
import os
import sys
sys.path.append(os.getcwd())
from app import create_app, db
from app.models import APIKeyTracker
from datetime import datetime, timezone

app = create_app()
with app.app_context():
    trackers = APIKeyTracker.query.all()
    now = datetime.now(timezone.utc)
    print(f"Current UTC: {now}")
    for t in trackers:
        print(f"{t.provider}: {t.status}, CD: {t.cooldown_until}")
