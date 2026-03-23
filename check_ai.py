from app import create_app, db
from app.models import Group

app = create_app()
with app.app_context():
    groups = Group.query.all()
    print(f"Total groups found: {len(groups)}")
    for g in groups:
        print(f"Group ID: {g.id}, Name: {g.name}, Has AI: {g.has_ai}")
