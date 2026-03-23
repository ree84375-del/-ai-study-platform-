from app import create_app, db
from app.models import User
app = create_app()
with app.app_context():
    u = User.query.filter_by(email='ree84375@gmail.com').first()
    if u:
        u.username = '管理員'
        db.session.commit()
        print('SUCCESS: Admin renamed to 管理員')
    else:
        print('ERROR: User not found')
