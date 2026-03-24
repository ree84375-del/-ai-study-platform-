from app import create_app, db
from app.models import User

app = create_app()
with app.app_context():
    users = User.query.filter(User.username.like('%雪音%')).all()
    print(f"Found {len(users)} users matching '雪音'")
    for u in users:
        print(f"ID: {u.id} | Name: {u.username} | Email: {u.email} | Avatar: {u.avatar_url} | File: {u.image_file}")
