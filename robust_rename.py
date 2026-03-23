import os
from app import create_app, db
from app.models import User

app = create_app()
with app.app_context():
    print(f"DATABASE_URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    u = User.query.filter_by(email='ree84375@gmail.com').first()
    if u:
        old_name = u.username
        u.username = '管理員'
        db.session.commit()
        print(f"SUCCESS: Renamed {old_name} to {u.username}")
    else:
        print("ERROR: Admin user not found by email ree84375@gmail.com")
        # List all users for debugging
        all_users = User.query.all()
        print(f"Total users: {len(all_users)}")
        for usr in all_users:
            print(f"- {usr.username} ({usr.email})")
