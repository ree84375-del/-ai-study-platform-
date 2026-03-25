import os
from dotenv import load_dotenv
from app import create_app, db
from app.models import APIKeyTracker
from sqlalchemy import text

def sync_keys():
    app = create_app()
    with app.app_context():
        print("--- Starting API Key Sync ---")
        
        # 1. Ensure the is_blocked column exists (redundancy for safety)
        try:
            db.session.execute(text("ALTER TABLE api_key_tracker ADD COLUMN is_blocked BOOLEAN DEFAULT FALSE"))
            db.session.commit()
            print("Added is_blocked column.")
        except Exception:
            db.session.rollback()
            print("is_blocked column already exists or table not found.")

        # 2. Load keys from .env
        load_dotenv()
        gemini_keys = [k.strip() for k in os.environ.get('GEMINI_API_KEYS', '').split(',') if k.strip()]
        groq_keys = [k.strip() for k in os.environ.get('GROQ_API_KEYS', '').split(',') if k.strip()]
        
        all_new_keys = {
            'gemini': gemini_keys,
            'groq': groq_keys
        }
        
        print(f"Found {len(gemini_keys)} Gemini keys and {len(groq_keys)} Groq keys in .env")

        # 3. Mark all existing keys NOT in .env as blocked and error (cleanup)
        existing_trackers = APIKeyTracker.query.all()
        new_key_strings = gemini_keys + groq_keys
        
        deactivated_count = 0
        for tracker in existing_trackers:
            if tracker.api_key not in new_key_strings:
                tracker.is_blocked = True
                tracker.status = 'error'
                tracker.error_message = "Deactivated during manual key rotation."
                deactivated_count += 1
        
        print(f"Deactivated {deactivated_count} old keys.")

        # 4. Add or Reactivate keys from .env
        added_count = 0
        reactivated_count = 0
        
        for provider, keys in all_new_keys.items():
            for key in keys:
                tracker = APIKeyTracker.query.filter_by(api_key=key).first()
                if not tracker:
                    new_tracker = APIKeyTracker(
                        provider=provider,
                        api_key=key,
                        status='standby',
                        is_blocked=False
                    )
                    db.session.add(new_tracker)
                    added_count += 1
                else:
                    tracker.is_blocked = False
                    tracker.status = 'standby'
                    tracker.error_message = None
                    tracker.retry_count = 0
                    tracker.cooldown_until = None
                    reactivated_count += 1
        
        db.session.commit()
        print(f"Added {added_count} new keys. Reactivated/Reset {reactivated_count} keys.")
        print("--- Sync Complete ---")

if __name__ == "__main__":
    sync_keys()
