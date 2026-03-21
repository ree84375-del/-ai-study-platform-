from app import create_app, db
from app.models import APIKeyTracker
from sqlalchemy import delete

app = create_app()
with app.app_context():
    # Keep only the valid, healthy ones for now or just reset errors
    # Actually, the user says "把後台api key壞掉清除" (Clear broken API keys from backend)
    # We will delete the rows inside APIKeyTracker that have status = 'error'
    # Wait, the frontend UI just reads from APIKeyTracker and active keys from config.
    # So deleting 'error' status is correct.
    deleted = APIKeyTracker.query.filter_by(status='error').delete()
    print(f"Deleted {deleted} error keys.")
    
    # Also delete 'standby' keys if they are no longer in the environment variable to clean up
    # actually, just resetting all to standby is safer? 
    # User says "留下真的真的正常的可以運作的" (Keep the truly working ones)
    db.session.commit()
    print("Done clearing broken keys.")
