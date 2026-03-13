import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth

load_dotenv()

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
migrate = Migrate()
oauth = OAuth()
csrf = CSRFProtect()

def create_app(config_class=None):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_secret_key_12345')
    
    # Database Settings
    # Vercel serverless 環境檔案系統為唯讀，只有 /tmp 可寫入
    if os.environ.get('VERCEL'):
        db_path = '/tmp/app.db'
    else:
        basedir = os.path.abspath(os.path.dirname(__file__))
        db_path = os.path.join(basedir, 'app.db')
    
    db_uri = os.environ.get('DATABASE_URL', 'sqlite:///' + db_path)
    if db_uri:
        if db_uri.startswith("postgres://"):
            db_uri = db_uri.replace("postgres://", "postgresql://", 1)
        
        # FIX FOR VERCEL IPv6 ISSUE: 
        # Supabase 'db.***.supabase.co' resolves to IPv6 which Vercel doesn't support.
        # Check if the user is still using the direct connection (5432) on Vercel
        if ".supabase.co" in db_uri and ":5432" in db_uri and os.environ.get('VERCEL'):
            print("WARNING: Using direct connect (5432) on Vercel which only supports IPv6. This will fail with 'Cannot assign requested address'.")
            print("Please change your Vercel DATABASE_URL to use the Supabase Transaction Pooler (port 6543).")
        
        # Proactive fix for Supabase Pooler (port 6543) if already using pooler directly
        if ":6543/" in db_uri and "@aws-" in db_uri or "@pooler." in db_uri:
            import re
            match = re.search(r'postgresql://([^:]+):', db_uri)
            if match and "." not in match.group(1):
                # Attempt to find the project ref if it's missing from the username
                project_ref = None
                # Check if it was passed via another env var or fallback to hardcoded
                project_ref = "nphrkuzhedlvgfagaujq" # The user's project ref
                db_uri = re.sub(r'postgresql://([^:]+):', rf'postgresql://\1.{project_ref}:', db_uri, count=1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # Fix stale connections to Supabase PostgreSQL and handle Vercel IPv6 issues
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,    # Test connections before use
        'pool_recycle': 300,      # Recycle connections every 5 min
        'pool_size': 5,
        'max_overflow': 10,
        'connect_args': {
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5,
        }
    }

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    oauth.init_app(app)
    csrf.init_app(app)

    from app.main.routes import main
    from app.auth.routes import auth
    from app.study.routes import study
    from app.group.routes import group
    from app.admin.routes import admin
    
    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(study)
    app.register_blueprint(group)
    app.register_blueprint(admin)

    # 確保在建立資料表前，models 已被載入
    from app import models

    # 在 Vercel 環境上，每次冷啟動時自動建立資料表
    with app.app_context():
        try:
            db.create_all()
            # Proactive Migration: Add has_ai column if missing
            from sqlalchemy import text
            db.session.execute(text("ALTER TABLE \"group\" ADD COLUMN IF NOT EXISTS has_ai BOOLEAN DEFAULT TRUE;"))
            # AssignmentStatus extensions
            db.session.execute(text("ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS content TEXT;"))
            db.session.execute(text("ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS ai_feedback TEXT;"))
            db.session.execute(text("ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS score INTEGER;"))
            db.session.commit()
        except Exception as e:
            app.logger.error(f"Database initialization/migration failed: {e}")
            db.session.rollback()

    # 加入全域錯誤處理器，幫助除錯 Vercel 500 錯誤
    @app.errorhandler(500)
    def handle_500(error):
        import traceback
        return f"<h3>系統發生錯誤 (500)</h3><pre>{traceback.format_exc()}</pre>", 500

    return app
