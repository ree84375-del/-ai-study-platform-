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
login_manager.login_view = 'auth.login'
login_manager.login_message = None
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
    
    # Session Persistence & Stability for Vercel
    from datetime import timedelta
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    if os.environ.get('VERCEL'):
        app.config['SESSION_COOKIE_SECURE'] = True
    
    # Jinja Helpers
    from app.utils.i18n import get_text
    from flask_login import current_user
    
    @app.context_processor
    def inject_i18n():
        from flask import session
        def translate(key, **kwargs):
            # 1. Check current_user (DB persisted)
            # 2. Check session (Guest/Ephemeral persistence)
            # 3. Default to 'zh'
            lang = session.get('language', 'zh')
            if current_user.is_authenticated:
                lang = getattr(current_user, 'language', lang)
            return get_text(key, lang, **kwargs)
        
        # Also inject current lang for template logic
        lang = session.get('language', 'zh')
        if current_user.is_authenticated:
            lang = getattr(current_user, 'language', lang)
            
        return dict(_t=translate, current_lang=lang)

    app.jinja_env.globals.update(hasattr=hasattr, getattr=getattr, any=any)

    # Register custom Jinja2 filters
    import json
    app.jinja_env.filters['from_json'] = lambda s: json.loads(s) if s else {}
    
    # Database URI processing
    db_uri = os.environ.get('DATABASE_URL')
    app.logger.info(f"Checking DATABASE_URL existence: {'Yes' if db_uri else 'No'}")
    
    if db_uri:
        if db_uri.startswith("postgres://"):
            app.logger.info("Normalizing postgres:// to postgresql+pg8000://")
            db_uri = db_uri.replace("postgres://", "postgresql+pg8000://", 1)
        elif db_uri.startswith("postgresql://"):
            app.logger.info("Normalizing postgresql:// to postgresql+pg8000://")
            db_uri = db_uri.replace("postgresql://", "postgresql+pg8000://", 1)
    else:
        app.logger.warning("No DATABASE_URL found. Using local SQLite.")
        if os.environ.get('VERCEL'):
            db_uri = 'sqlite:////tmp/site.db'
        else:
            db_uri = 'sqlite:///site.db'
    
    # --- Emergency Database Connectivity Check ---
    try:
        # Purity check without Flask overhead
        from sqlalchemy import create_engine
        engine_check = create_engine(db_uri)
        with engine_check.connect():
            pass 
        app.logger.info("Remote database connection verified.")
    except Exception as e:
        app.logger.warning(f"Remote database unreachable ({e}). Mapping to local SQLite.")
        db_uri = 'sqlite:///site.db'
    # --- End Check ---

    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Engine options for Vercel/Supabase stability
    is_sqlite = db_uri.startswith('sqlite:')
    if os.environ.get('VERCEL'):
        app.logger.info("Vercel environment detected. Optimizing connection pool.")
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
        }
        if not is_sqlite:
            app.config['SQLALCHEMY_ENGINE_OPTIONS'].update({
                'pool_size': 1,
                'max_overflow': 0,
            })
    else:
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
        }
        if not is_sqlite:
            app.config['SQLALCHEMY_ENGINE_OPTIONS'].update({
                'pool_size': 5,
                'max_overflow': 10,
            })

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    oauth.init_app(app)
    
    with app.app_context():
        from app import models

        # Auto-initialize SQLite tables if needed
        if db_uri.startswith('sqlite:'):
            db.create_all()
            app.logger.info("Local SQLite initialized/verified.")

        try:
            from app.utils.bundled_question_bank import seed_bundled_question_banks

            sync_results = seed_bundled_question_banks(logger=app.logger)
            synced_subjects = [item["subject"] for item in sync_results if item.get("status") == "synced"]
            if synced_subjects:
                app.logger.info("Bundled question banks synced: %s", ", ".join(synced_subjects))
        except Exception as exc:
            app.logger.error(f"Bundled question bank sync skipped due to error: {exc}")

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
        
        from app.utils.i18n import get_text as _t
        # Try to get user language, default to 'zh'
        lang = 'zh'
        try:
            from flask_login import current_user
            if current_user.is_authenticated:
                lang = current_user.language
        except:
            pass
            
        return f"""
        <div style='padding:40px; font-family:sans-serif; line-height:1.6; max-width:800px; margin:0 auto; color:#333;'>
            <h1 style='color:#e74c3c;'>{_t('error_500_title', lang)}</h1>
            <p>{_t('error_500_desc', lang)}</p>
            <div style='background:#f9f9f9; border:1px solid #ddd; padding:20px; border-radius:8px; margin:20px 0;'>
                <strong>{_t('error_details_label', lang)}</strong>
                <pre style='white-space:pre-wrap; font-size:0.9em; margin-top:10px;'>{error_info}</pre>
            </div>
            <p style='color:#666;'>{_t('error_hint', lang)}</p>
            <a href='/' style='display:inline-block; margin-top:10px; padding:10px 20px; background:#3498db; color:white; text-decoration:none; border-radius:5px;'>{_t('back_to_home', lang)}</a>
        </div>
        """, 500

    return app
