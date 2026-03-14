import os
import re
import logging
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from sqlalchemy import text

load_dotenv()

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info'
migrate = Migrate()
csrf = CSRFProtect()
oauth = OAuth()

def create_app():
    app = Flask(__name__)
    
    # Configure logging for Vercel
    if not app.debug:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        app.logger.addHandler(stream_handler)
        app.logger.setLevel(logging.INFO)

    app.logger.info("Initializing app...")

    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '5791628bb0b13ce0c676dfde280ba245')
    
    # Jinja Helpers
    app.jinja_env.globals.update(hasattr=hasattr, getattr=getattr, any=any)
    
    # Database URI processing
    db_uri = os.environ.get('DATABASE_URL')
    app.logger.info(f"Checking DATABASE_URL existence: {'Yes' if db_uri else 'No'}")
    
    if db_uri:
        if db_uri.startswith("postgres://"):
            app.logger.info("Normalizing postgres:// to postgresql://")
            db_uri = db_uri.replace("postgres://", "postgresql://", 1)
        
        # General Supabase precaution: pooler address sometimes needs tweaking, 
        # but we will rely on SQLAlchemy options mostly.
    else:
        app.logger.warning("No DATABASE_URL found. Using local SQLite.")
        db_uri = 'sqlite:///site.db'
    
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Engine options for Vercel/Supabase stability
    if os.environ.get('VERCEL'):
        app.logger.info("Vercel environment detected. Optimizing connection pool.")
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_size': 1,
            'max_overflow': 0,
        }
    else:
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_size': 5,
            'max_overflow': 10,
        }

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    oauth.init_app(app)
    
    app.logger.info("Extensions initialized.")

    # Blueprints
    from app.main.routes import main
    from app.group.routes import group
    from app.study.routes import study
    from app.auth.routes import auth
    from app.admin.routes import admin
    app.register_blueprint(main)
    app.register_blueprint(group)
    app.register_blueprint(study)
    app.register_blueprint(auth)
    app.register_blueprint(admin)
    
    app.logger.info("Blueprints registered correctly.")

    # Database initialization is now moved to a separate step or handled lazily
    # to avoid Vercel timeouts during cold starts.
    # We will ONLY rely on migrations via /debug/setup_db or manual scripts.
    # if os.environ.get('SKIP_DB_INIT') != 'true':
    #     with app.app_context():
    #         try:
    #             db.create_all()
    #             app.logger.info("db.create_all() executed.")
    #         except Exception as e:
    #             app.logger.error(f"Lazy DB setup error (non-fatal): {e}")

    # Global Error Handler
    @app.errorhandler(500)
    def handle_500(error):
        import traceback
        error_info = traceback.format_exc()
        app.logger.error(f"Server Error 500 [RequestPath: {request.path}]: {error_info}")
        return f"""
        <div style='padding:40px; font-family:sans-serif; line-height:1.6; max-width:800px; margin:0 auto; color:#333;'>
            <h1 style='color:#e74c3c;'>系統發生錯誤 (500)</h1>
            <p>很抱歉，這可能是由於最近的系統更新導致的穩定性問題。我們已經記錄了此錯誤，開發團隊會盡快修復。</p>
            <div style='background:#f9f9f9; border:1px solid #ddd; padding:20px; border-radius:8px; margin:20px 0;'>
                <strong>錯誤詳細資訊：</strong>
                <pre style='white-space:pre-wrap; font-size:0.9em; margin-top:10px;'>{error_info}</pre>
            </div>
            <p style='color:#666;'>提示：請嘗試清除瀏覽器緩存或稍後再試。</p>
            <a href='/' style='display:inline-block; margin-top:10px; padding:10px 20px; background:#3498db; color:white; text-decoration:none; border-radius:5px;'>回到首頁</a>
        </div>
        """, 500

    return app
