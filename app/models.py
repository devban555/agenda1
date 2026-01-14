from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # 🔐 login interno
    username = db.Column(db.String(80), unique=True, nullable=False)

    # 🌍 slug público (URL)
    slug = db.Column(db.String(120), unique=True, nullable=False)

    password_hash = db.Column(db.String(255), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # RELACIONAMENTOS (necessários para multiusuário)
    agendamentos = db.relationship('Agendamento', backref='usuario', lazy=True)
    servicos = db.relationship('Servico', backref='usuario', lazy=True)

    def set_password(self, senha):
        self.password_hash = generate_password_hash(senha)

    def check_password(self, senha):
        return check_password_hash(self.password_hash, senha)


class Agendamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # NOVO (vínculo com usuário)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    servico = db.Column(db.String(100), nullable=False)
    data = db.Column(db.Date, nullable=False)
    hora = db.Column(db.Time, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class Servico(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # NOVO (vínculo com usuário)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

    titulo = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.String(20), nullable=False)
    tempo = db.Column(db.String(20), nullable=False)
