try:
    import flask
    import flask_sqlalchemy
    import flask_login
    import flask_bcrypt
    import flask_migrate
    import flask_wtf
    import dotenv
    import authlib
    import google.generativeai
    from PIL import Image
    print("SUCCESS: All core dependencies imported correctly.")
except ImportError as e:
    print(f"FAILURE: Missing dependency: {e}")
except Exception as e:
    print(f"ERROR: {e}")
