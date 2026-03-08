from datetime import datetime, timezone
from app import db, login_manager
from flask_login import UserMixin

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    image_file = db.Column(db.String(20), nullable=False, default='default.jpg')
    password = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student') # student, teacher, guest
    experience_points = db.Column(db.Integer, default=0)
    current_streak = db.Column(db.Integer, default=0)
    last_study_date = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    mistakes = db.relationship('Mistake', backref='student', lazy=True)
    group_memberships = db.relationship('GroupMember', backref='member', lazy=True)

    def __repr__(self):
        return f"User('{self.username}', '{self.email}', Role: '{self.role}', XP: {self.experience_points})"

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(50), nullable=False) # 國文、英文、日文、數學、社會、自然
    category = db.Column(db.String(100), nullable=True) # 單元/分類
    content_text = db.Column(db.Text, nullable=False)
    content_image = db.Column(db.String(100), nullable=True) # 圖片路徑(如果有)
    option_a = db.Column(db.String(255), nullable=True)
    option_b = db.Column(db.String(255), nullable=True)
    option_c = db.Column(db.String(255), nullable=True)
    option_d = db.Column(db.String(255), nullable=True)
    correct_answer = db.Column(db.String(5), nullable=False) # A, B, C, D
    explanation = db.Column(db.Text, nullable=True) # 詳解
    
    mistakes_records = db.relationship('Mistake', backref='question', lazy=True)

    def __repr__(self):
        return f"Question('{self.subject}', '{self.content_text[:20]}...')"

class Mistake(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    mistake_count = db.Column(db.Integer, default=1)
    last_attempt_date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    is_resolved = db.Column(db.Boolean, default=False) # 是否已經複習過了

    def __repr__(self):
        return f"Mistake(User: {self.user_id}, Question: {self.question_id}, Count: {self.mistake_count})"

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    invite_code = db.Column(db.String(20), unique=True, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # Teacher relationship is handled directly by teacher_id, but we can access teacher
    teacher = db.relationship('User', foreign_keys=[teacher_id], backref=db.backref('owned_groups', lazy=True))
    members = db.relationship('GroupMember', backref='group_info', lazy=True)
    assignments = db.relationship('Assignment', backref='group', lazy=True)

    def __repr__(self):
        return f"Group('{self.name}', Code: '{self.invite_code}')"

class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    joined_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
