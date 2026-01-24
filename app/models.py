from datetime import datetime
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

    titulo = db.Column(db.String(120), nullable=False)
    duracao_minutos = db.Column(db.Integer, nullable=False)
    preco = db.Column(db.Numeric(10, 2), nullable=True)

    ativo = db.Column(db.Boolean, default=True)

    # =========================
    # COMPATIBILIDADE COM SISTEMA ANTIGO
    # =========================
    @property
    def tempo(self):
        return self.duracao_minutos

    @tempo.setter
    def tempo(self, value):
        """
        Aceita:
        - int (60)
        - '60'
        - '01:00'
        - '1:30'
        """
        if value is None:
            self.duracao_minutos = 0
            return

        # já é número
        if isinstance(value, int):
            self.duracao_minutos = value
            return

        value = str(value).strip()

        # formato HH:MM
        if ':' in value:
            horas, minutos = value.split(':')
            self.duracao_minutos = int(horas) * 60 + int(minutos)
        else:
            # string numérica simples
            self.duracao_minutos = int(value)

    @property
    def valor(self):
        return self.preco

    @valor.setter
    def valor(self, value):
        if value in (None, ''):
            self.preco = None
        else:
            self.preco = value

# =========================
# CONFIGURAÇÃO DA AGENDA (BASE)
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

    # dias da semana permitidos (0=segunda … 6=domingo)
    dias_semana = db.Column(db.JSON, nullable=False)

    # horários base disponíveis (ex: ["08:00","09:00"])
    horarios_base = db.Column(db.JSON, nullable=False)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# EXCEÇÕES DA AGENDA (POR DATA)
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

    # dia ativo ou totalmente bloqueado
    dia_ativo = db.Column(db.Boolean, default=True)

    # horários bloqueados especificamente nesse dia
    horarios_bloqueados = db.Column(db.JSON, default=list)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('usuario_id', 'data'),
    )
