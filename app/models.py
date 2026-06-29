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

    username = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False)

    password_hash = db.Column(db.String(255), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    nome_fantasia = db.Column(db.String(120), nullable=True)
    fonte_titulo = db.Column(db.String(30), default='padrao')
    tema = db.Column(db.String(30), default='principal')

    # 🔥 NOVO CAMPO (MASTER ADM)
    is_masteradm = db.Column(db.Boolean, default=False)

    # 🔥 NOVOS CAMPOS (cadastro completo)
    nome = db.Column(db.String(150), nullable=True)
    email = db.Column(db.String(150), nullable=True)
    telefone = db.Column(db.String(50), nullable=True)
    cpf = db.Column(db.String(20), nullable=True)
    empresa = db.Column(db.String(150), nullable=True)
    plano = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default='ativo')
    obs = db.Column(db.String(255), nullable=True)

    agendamentos = db.relationship('Agendamento', backref='usuario', lazy=True, cascade='all, delete-orphan')
    servicos = db.relationship('Servico', backref='usuario', lazy=True, cascade='all, delete-orphan')

    configuracao_agenda = db.relationship('ConfiguracaoAgenda', backref='usuario', uselist=False, cascade='all, delete-orphan')
    excecoes_agenda = db.relationship('ExcecaoAgenda', backref='usuario', lazy=True, cascade='all, delete-orphan')

    def set_password(self, senha):
        self.password_hash = generate_password_hash(senha)

    def check_password(self, senha):
        return check_password_hash(self.password_hash, senha)

# =========================
# CLIENTE
# =========================
class Cliente(db.Model):
    __tablename__ = 'cliente'

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)

    recorrente = db.Column(db.String(10), default='nao')  # sim / nao
    ativo_crm = db.Column(db.Boolean, default=True)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    usuario = db.relationship('Usuario', backref='clientes')

    __table_args__ = (
        db.UniqueConstraint('usuario_id', 'telefone', name='uq_cliente_usuario_telefone'),
    )

# =========================
# AGENDAMENTO (ATUALIZADO)
# =========================
class Agendamento(db.Model):
    __tablename__ = 'agendamento'

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=True)
    cliente = db.relationship('Cliente')
    
    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)

    # 🔴 NOVO CAMPO
    servico_id = db.Column(db.Integer, db.ForeignKey('servico.id'))
    servico = db.relationship('Servico')

    data = db.Column(db.Date, nullable=False)
    horario = db.Column(db.Time, nullable=False)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)



# =========================
# SERVIÇOS
# =========================
class Servico(db.Model):
    __tablename__ = 'servico'

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

    titulo = db.Column(db.String(120), nullable=False)
    duracao_minutos = db.Column(db.Integer, nullable=False)
    preco = db.Column(db.Numeric(10, 2), nullable=True)

    ativo = db.Column(db.Boolean, default=True)

    cor = db.Column(db.String(30), default='azul')

    @property
    def tempo(self):
        return self.duracao_minutos

    @tempo.setter
    def tempo(self, value):
        if value is None:
            self.duracao_minutos = 0
            return

        if isinstance(value, int):
            self.duracao_minutos = value
            return

        value = str(value).strip()

        if ':' in value:
            horas, minutos = value.split(':')
            self.duracao_minutos = int(horas) * 60 + int(minutos)
        else:
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
# CONFIGURAÇÃO
# =========================
class ConfiguracaoAgenda(db.Model):
    __tablename__ = 'configuracao_agenda'

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False, unique=True)

    dias_semana = db.Column(db.JSON, nullable=False)
    horarios_base = db.Column(db.JSON, nullable=False)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

class WhatsappSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True)
    session_id = db.Column(db.String(100))
    status = db.Column(db.String(20))  # connected / disconnected / qr

# =========================
# EXCEÇÕES
# =========================
class ExcecaoAgenda(db.Model):
    __tablename__ = 'excecao_agenda'

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

    data = db.Column(db.Date, nullable=False)
    dia_ativo = db.Column(db.Boolean, default=True)
    horarios_bloqueados = db.Column(db.JSON, default=list)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('usuario_id', 'data'),
    )