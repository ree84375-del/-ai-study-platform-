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
        
        # Proactive fix for Supabase Pooler (port 6543)
        # If it's port 6543 and the user is just 'postgres', it needs the project ref
        if ":6543/" in db_uri and "postgres:" in db_uri and "@db." not in db_uri:
            # Try to find project ref from hostname if it's a supabase pooler
            # Note: The user's ref is 'nphrkuzhedlvgfagaujq'
            if "nphrkuzhedlvgfagaujq" in db_uri and "postgres." not in db_uri:
                db_uri = db_uri.replace("postgres:", "postgres.nphrkuzhedlvgfagaujq:", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
    
    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(study)
    app.register_blueprint(group)

    # 確保在建立資料表前，models 已被載入
    from app import models

    # 在 Vercel 環境上，每次冷啟動時自動建立資料表
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            app.logger.error(f"Database creation failed: {e}")

    # 加入全域錯誤處理器，幫助除錯 Vercel 500 錯誤
    @app.errorhandler(500)
    def handle_500(error):
        import traceback
        return f"<h3>系統發生錯誤 (500)</h3><pre>{traceback.format_exc()}</pre>", 500

    return app
