from flask import Flask, send_from_directory
from config import Config, MASTERADM_KEY
from .models import db
import logging
import os

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    if not app.config.get('SECRET_KEY'):
        raise RuntimeError('SECRET_KEY não configurada no ambiente.')

    if not MASTERADM_KEY:
        raise RuntimeError('MASTERADM_KEY não configurada no ambiente.')

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

    # O service worker precisa ser servido na raiz para controlar o painel
    # inteiro. Nesta primeira versão ele não mantém páginas ou dados em cache.
    @app.get('/service-worker.js')
    def service_worker():
        response = send_from_directory(
            app.static_folder,
            'service-worker.js',
            mimetype='application/javascript',
            max_age=0,
        )
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Service-Worker-Allowed'] = '/'
        return response

    return app
