from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


# =========================
# USUÁRIO
# =========================
class Usuario(db.Model):
    __tablename__ = 'usuario'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    agendamentos = db.relationship('Agendamento', backref='usuario', lazy=True)
    servicos = db.relationship('Servico', backref='usuario', lazy=True)

    configuracao_agenda = db.relationship(
        'ConfiguracaoAgenda',
        backref='usuario',
        uselist=False,
        lazy=True
    )

    excecoes_agenda = db.relationship(
        'ExcecaoAgenda',
        backref='usuario',
        lazy=True
    )

    def set_password(self, senha):
        self.password_hash = generate_password_hash(senha)

    def check_password(self, senha):
        return check_password_hash(self.password_hash, senha)


# =========================
# AGENDAMENTO
# =========================
class Agendamento(db.Model):
    __tablename__ = 'agendamento'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    servico = db.Column(db.String(100), nullable=False)
    data = db.Column(db.Date, nullable=False)
    hora = db.Column(db.Time, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# SERVIÇOS
# =========================
class Servico(db.Model):
    __tablename__ = 'servico'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

    titulo = db.Column(db.String(100), nullable=False)
    valor = db.Column(db.String(20), nullable=False)
    tempo = db.Column(db.String(20), nullable=False)


# =========================
# CONFIGURAÇÃO PADRÃO DA AGENDA
# =========================
class ConfiguracaoAgenda(db.Model):
    __tablename__ = 'configuracao_agenda'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey('usuario.id'),
        unique=True,
        nullable=False
    )

    dias_semana = db.Column(db.JSON, nullable=False)
    horarios_base = db.Column(db.JSON, nullable=False)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# EXCEÇÕES POR DATA
# =========================
class ExcecaoAgenda(db.Model):
    __tablename__ = 'excecao_agenda'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey('usuario.id'),
        nullable=False
    )

    data = db.Column(db.Date, nullable=False)
    dia_ativo = db.Column(db.Boolean, default=True)

    horarios_bloqueados = db.Column(db.JSON, default=lambda: [])

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('usuario_id', 'data', name='uix_usuario_data'),
    )
