from flask import Flask
from config import Config
from .models import db  # ✅ usa a instância correta

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # ✅ registra o app no SQLAlchemy correto
    db.init_app(app)

    # 🔹 cria tabelas automaticamente (apenas DEV)
    with app.app_context():
        db.create_all()

    # 🔹 blueprints
    from .routes import main
    from .auth import auth

    app.register_blueprint(main)
    app.register_blueprint(auth)

    return app
