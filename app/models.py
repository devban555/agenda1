from datetime import datetime, date, time
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# =========================
# USUÁRIO
# =========================
class Usuario(db.Model):
    __tablename__ = 'usuario'

    id = db.Column(db.Integer, primary_key=True)

    # login interno
    username = db.Column(db.String(80), unique=True, nullable=False)

    # slug público (URL)
    slug = db.Column(db.String(120), unique=True, nullable=False)

    password_hash = db.Column(db.String(255), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # identidade visual
    nome_fantasia = db.Column(db.String(120), nullable=True)
    fonte_titulo = db.Column(db.String(30), default='padrao')
    tema = db.Column(db.String(30), default='principal')

    # relacionamentos
    agendamentos = db.relationship(
        'Agendamento',
        backref='usuario',
        lazy=True,
        cascade='all, delete-orphan'
    )

    servicos = db.relationship(
        'Servico',
        backref='usuario',
        lazy=True,
        cascade='all, delete-orphan'
    )

    configuracao_agenda = db.relationship(
        'ConfiguracaoAgenda',
        backref='usuario',
        uselist=False,
        cascade='all, delete-orphan'
    )

    excecoes_agenda = db.relationship(
        'ExcecaoAgenda',
        backref='usuario',
        lazy=True,
        cascade='all, delete-orphan'
    )

    # métodos de senha
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

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey('usuario.id'),
        nullable=False
    )

    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)

    data = db.Column(db.Date, nullable=False)
    horario = db.Column(db.Time, nullable=False)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# SERVIÇOS
# =========================
class Servico(db.Model):
    __tablename__ = 'servico'

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey('usuario.id'),
        nullable=False
    )

    nome = db.Column(db.String(120), nullable=False)
    duracao_minutos = db.Column(db.Integer, nullable=False)
    preco = db.Column(db.Numeric(10, 2), nullable=True)

    ativo = db.Column(db.Boolean, default=True)


# =========================
# CONFIGURAÇÃO DA AGENDA
# =========================
class ConfiguracaoAgenda(db.Model):
    __tablename__ = 'configuracao_agenda'

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey('usuario.id'),
        nullable=False,
        unique=True
    )

    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fim = db.Column(db.Time, nullable=False)

    intervalo_minutos = db.Column(db.Integer, default=30)


# =========================
# EXCEÇÕES DA AGENDA
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

    bloqueado = db.Column(db.Boolean, default=True)
