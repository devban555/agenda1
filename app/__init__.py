from flask import Flask
from config import Config
from .models import db
import logging
import os

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # =========================
    # LOGS (NOVO)
    # =========================
    log_path = os.path.join(os.getcwd(), 'app.log')

    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s'
    )

    # =========================
    # DB
    # =========================
    db.init_app(app)

    # 🔹 cria tabelas automaticamente (DEV)
    with app.app_context():
        db.create_all()

    # =========================
    # ERROS AUTOMÁTICOS (NOVO)
    # =========================
    @app.errorhandler(Exception)
    def handle_exception(e):
        app.logger.error(f"Erro: {str(e)}")
        return "Erro interno no servidor", 500

    # =========================
    # BLUEPRINTS
    # =========================
    from .routes import main
    from .auth import auth

    app.register_blueprint(main)
    app.register_blueprint(auth)

    return app