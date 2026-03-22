from app import create_app, db, bcrypt
from app.models import User, Group, GroupMessage
import os

# Absolute path for SQLite to avoid confusion
db_path = os.path.join(os.getcwd(), 'instance', 'site.db')
if not os.path.exists(os.path.dirname(db_path)):
    os.makedirs(os.path.dirname(db_path))

os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'

app = create_app()
with app.app_context():
    print(f"Initializing with DB: {db_path}")
    db.create_all()
    
    yukine = User.query.filter_by(username='雪音老師').first()
    if not yukine:
        print("Creating 雪音老師...")
        hashed_pw = bcrypt.generate_password_hash('yukine123').decode('utf-8')
        yukine = User(
            username='雪音老師',
            email='yukine@example.com',
            password=hashed_pw,
            role='teacher'
        )
        db.session.add(yukine)
        db.session.commit()
        print("Created 雪音老師.")
    else:
        print("雪音老師 already exists.")
        
    # Enable AI for all groups
    groups = Group.query.all()
    for g in groups:
        if not g.has_ai:
            g.has_ai = True
    db.session.commit()
    print("Done.")
