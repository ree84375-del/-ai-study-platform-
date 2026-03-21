from datetime import datetime, timezone
import logging
from app import db, login_manager
from flask_login import UserMixin
from sqlalchemy import desc


@login_manager.user_loader
def load_user(user_id):
    # Attempt 1: Normal query
    try:
        user = db.session.get(User, int(user_id))
        if not user:
            logging.warning(f"User loader: User ID {user_id} not found.")
        return user
    except Exception as e:
        logging.error(f"Error loading user {user_id} (attempt 1): {e}")
        # IMPORTANT: Use rollback() instead of remove().
        # remove() destroys the scoped session entirely, causing Flask-Login
        # to lose track of the user on the next request → unexpected logout.
        # rollback() only cancels the failed transaction but keeps the session alive.
        try:
            db.session.rollback()
        except Exception:
            pass
        # Attempt 2: Retry with a rolled-back (clean) session
        try:
            user = db.session.get(User, int(user_id))
            return user
        except Exception as e2:
            logging.error(f"Error loading user {user_id} (attempt 2): {e2}")
            try:
                db.session.rollback()
            except Exception:
                pass
            return None

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    image_file = db.Column(db.String(20), nullable=False, default='default.jpg')
    avatar_url = db.Column(db.String(255), nullable=True)
    password = db.Column(db.String(60), nullable=False)
    auth_provider = db.Column(db.String(20), nullable=True, default='local')  # 'local', 'google', 'guest'
    role = db.Column(db.String(20), nullable=False, default='student') # student, teacher, guest, admin
    last_login = db.Column(db.DateTime, nullable=True, default=lambda: datetime.now(timezone.utc))
 
    @property
    def is_admin(self):
        return self.role == 'admin' or self.email == 'ree84375@gmail.com'

    @property
    def display_name(self):
        if self.is_admin:
            return "管理員"
        return self.username

    @property
    def ai_avatar_filename(self):
        if self.ai_personality in ['ai_coach', '雷恩教練', '魔鬼教練', '雪音-嚴格型', '雪音-严格型']:
            return 'img/coach_avatar.png'
        elif self.ai_personality in ['ai_guy', '阿哲學長', '雪音-幽默型']:
            return 'img/senior_avatar.png'
        else:
            return 'img/yukine_avatar.png'
            
    @property
    def ai_scene_prefix(self):
        if self.ai_personality in ['ai_coach', '雷恩教練', '魔鬼教練', '雪音-嚴格型', '雪音-严格型']:
            return 'img/coach_scene'
        elif self.ai_personality in ['ai_guy', '阿哲學長', '雪音-幽默型']:
            return 'img/senior_scene'
        else:
            return 'img/yukine_scene'
 
    # current_streak = db.Column(db.Integer, default=0)
    # last_study_date = db.Column(db.DateTime, nullable=True)
    has_seen_tour = db.Column(db.Boolean, default=False)
    
    # 個人簡介與 AI 性格設定
    bio = db.Column(db.Text, nullable=True)
    learning_goals = db.Column(db.Text, nullable=True)
    ai_personality = db.Column(db.String(50), default='ai_personality_gentle') # 溫柔型, 嚴厲型, 幽默型
    language = db.Column(db.String(5), default='zh') # zh, ja, en
    
    # 網站偏好設定
    preferred_theme = db.Column(db.String(20), default='sakura') # sakura, moon, classic, midnight, etc.
    # pomodoro_duration = db.Column(db.Integer, default=25)
    
    # Study Roadmap
    # exam_date = db.Column(db.Date, nullable=True)
    # study_plan_json = db.Column(db.Text, nullable=True)
    
    last_active_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    mistakes = db.relationship('Mistake', backref='student', lazy=True)
    group_memberships = db.relationship('GroupMember', backref='member', lazy=True)

    @staticmethod
    def is_name_forbidden(name):
        forbidden_keywords = ['管理員', '官網人員', '官方', '雪音老師', 'yukine', 'admin', 'administrator', 'root', 'staff', 'moderator', 'system']
        name_lower = name.lower()
        return any(kw in name_lower for kw in forbidden_keywords)

    def __repr__(self):
        return f"User('{self.username}', '{self.email}', Role: '{self.role}')"

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
    tags = db.Column(db.String(100), nullable=True) # 標籤 (e.g. "語法,單字")
    difficulty = db.Column(db.Integer, default=1) # 1-5 難度
    
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
    
    # SRS (Spaced Repetition System)
    srs_level = db.Column(db.Integer, default=0) # 0-7 等級
    next_review_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_interval = db.Column(db.Integer, default=0) # 上次間隔(天數)

    def __repr__(self):
        return f"Mistake(User: {self.user_id}, Question: {self.question_id}, Count: {self.mistake_count})"

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    invite_code = db.Column(db.String(20), unique=True, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    has_ai = db.Column(db.Boolean, default=True)
    group_type = db.Column(db.String(20), nullable=False, default='class') # 'class', 'discussion'
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # Collaborative Zen Garden
    garden_exp = db.Column(db.Integer, default=0)
    garden_level = db.Column(db.Integer, default=1)
    
    # Teacher relationship is handled directly by teacher_id, but we can access teacher
    teacher = db.relationship('User', foreign_keys=[teacher_id], backref=db.backref('owned_groups', lazy=True))
    members = db.relationship('GroupMember', backref='group_info', lazy=True, cascade="all, delete-orphan")
    assignments = db.relationship('Assignment', backref='group', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"Group('{self.name}', Code: '{self.invite_code}', Type: '{self.group_type}')"

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
    reference_answer = db.Column(db.Text, nullable=True) # Teacher's correct answer/key
    reference_image = db.Column(db.String(255), nullable=True) # Image path for key
    question_image = db.Column(db.String(255), nullable=True) # Image path for question
    due_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    statuses = db.relationship('AssignmentStatus', backref='assignment', lazy=True, cascade="all, delete-orphan")

class AssignmentStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=True) # Student submission (final text)
    submission_image = db.Column(db.String(255), nullable=True) # Path to student's upload
    recognized_content = db.Column(db.Text, nullable=True) # AI's initial OCR result
    ai_feedback = db.Column(db.Text, nullable=True) # Yukine's comments (brief)
    ai_explanation = db.Column(db.Text, nullable=True) # Yukine's detailed explanation
    score = db.Column(db.Integer, nullable=True) # 0-100
    is_completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)

class GroupAnnouncement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    group_ref = db.relationship('Group', backref=db.backref('group_announcements', lazy=True, cascade="all, delete-orphan"))

class ChatSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    messages = db.relationship('ChatMessage', backref='session', lazy=True, cascade="all, delete-orphan")

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_session.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'user' or 'ai'
    content = db.Column(db.Text, nullable=False)
    image_data = db.Column(db.Text, nullable=True) # Base64 image data
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_ai_generated = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    author = db.relationship('User', foreign_keys=[created_by_id])
    
    def __repr__(self):
        return f"Announcement('{self.title}', '{self.created_at}')"

class GroupMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_data = db.Column(db.Text, nullable=True) # Base64 image data
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # New fields for enhanced chat
    parent_id = db.Column(db.Integer, db.ForeignKey('group_message.id'), nullable=True)
    is_edited = db.Column(db.Boolean, default=False)
    is_recalled = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    
    # Relationships
    author = db.relationship('User', backref=db.backref('group_messages', lazy=True))
    group_ref = db.relationship('Group', backref=db.backref('messages', lazy=True, cascade="all, delete-orphan"))
    replies = db.relationship('GroupMessage', backref=db.backref('parent', remote_side=[id]), lazy=True)

class Omikuji(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    fortune_level = db.Column(db.String(20), nullable=False) # 大吉, 吉, 小吉, 凶, etc.
    message = db.Column(db.Text, nullable=False) # AI generated message
    drawn_date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    language = db.Column(db.String(5), nullable=True, default='zh') # Language used when drawing
    
    user = db.relationship('User', backref=db.backref('omikujis', lazy=True))

class Ema(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.String(100), nullable=False)
    is_public = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    user = db.relationship('User', backref=db.backref('emas', lazy=True))
    
class Daruma(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    goal = db.Column(db.String(100), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)
    
    user = db.relationship('User', backref=db.backref('darumas', lazy=True))

class GlobalStat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    zen_xp = db.Column(db.Integer, default=0)
    garden_level = db.Column(db.Integer, default=1)
    last_weather_check = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    current_weather = db.Column(db.String(50), default='weather_fair')
    active_users_count = db.Column(db.Integer, default=0)

    @classmethod
    def get_instance(cls):
        instance = cls.query.first()
        if not instance:
            instance = cls(zen_xp=0, garden_level=1)
            db.session.add(instance)
            db.session.commit()
        return instance

class APIKeyTracker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False) # 'gemini', 'groq', 'ollama'
    api_key = db.Column(db.String(255), unique=True, nullable=False)
    status = db.Column(db.String(20), default='standby') # 'active', 'standby', 'cooldown', 'error', 'busy'
    last_used = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    cooldown_until = db.Column(db.DateTime, nullable=True)
    retry_count = db.Column(db.Integer, default=0)

class UserMemory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    memory_content = db.Column(db.Text, nullable=True) # Legacy distilled context
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('memory', uselist=False, lazy=True))

class MemoryFragment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50), default='general') # 'preference', 'academic', 'personal', 'event'
    content = db.Column(db.Text, nullable=False)
    importance = db.Column(db.Integer, default=1) # 1-5
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref=db.backref('fragments', lazy=True, cascade="all, delete-orphan"))

