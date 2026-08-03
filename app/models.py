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
    profissionais = db.relationship(
        'Profissional',
        backref='usuario',
        lazy=True,
        cascade='all, delete-orphan'
    )

    def set_password(self, senha):
        self.password_hash = generate_password_hash(senha)

    def check_password(self, senha):
        return check_password_hash(self.password_hash, senha)


# =========================
# PROFISSIONAIS
# =========================
class Profissional(db.Model):
    __tablename__ = 'profissional'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey('usuario.id'),
        nullable=False,
        index=True
    )
    nome = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(120), nullable=False)
    especialidade = db.Column(db.String(120), nullable=True)
    foto_url = db.Column(db.String(255), nullable=True)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    principal = db.Column(db.Boolean, default=False, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            'usuario_id',
            'slug',
            name='uq_profissional_usuario_slug'
        ),
    )

    servicos_vinculados = db.relationship(
        'ProfissionalServico',
        backref='profissional',
        lazy=True,
        cascade='all, delete-orphan'
    )
    configuracao_agenda = db.relationship(
        'ConfiguracaoProfissional',
        backref='profissional',
        uselist=False,
        cascade='all, delete-orphan'
    )
    excecoes_agenda = db.relationship(
        'ExcecaoProfissional',
        backref='profissional',
        lazy=True,
        cascade='all, delete-orphan'
    )
    agendamentos_vinculados = db.relationship(
        'AgendamentoProfissional',
        backref='profissional',
        lazy=True,
        cascade='all, delete-orphan'
    )

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

    vinculo_profissional = db.relationship(
        'AgendamentoProfissional',
        backref='agendamento',
        uselist=False,
        cascade='all, delete-orphan'
    )



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

    vinculo_profissional = db.relationship(
        'ProfissionalServico',
        backref='servico',
        uselist=False,
        cascade='all, delete-orphan'
    )

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


class ProfissionalServico(db.Model):
    __tablename__ = 'profissional_servico'

    id = db.Column(db.Integer, primary_key=True)
    profissional_id = db.Column(
        db.Integer,
        db.ForeignKey('profissional.id'),
        nullable=False,
        index=True
    )
    servico_id = db.Column(
        db.Integer,
        db.ForeignKey('servico.id'),
        nullable=False,
        unique=True,
        index=True
    )
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class AgendamentoProfissional(db.Model):
    __tablename__ = 'agendamento_profissional'

    id = db.Column(db.Integer, primary_key=True)
    profissional_id = db.Column(
        db.Integer,
        db.ForeignKey('profissional.id'),
        nullable=False,
        index=True
    )
    agendamento_id = db.Column(
        db.Integer,
        db.ForeignKey('agendamento.id'),
        nullable=False,
        unique=True,
        index=True
    )
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class ConfiguracaoProfissional(db.Model):
    __tablename__ = 'configuracao_profissional'

    id = db.Column(db.Integer, primary_key=True)
    profissional_id = db.Column(
        db.Integer,
        db.ForeignKey('profissional.id'),
        nullable=False,
        unique=True,
        index=True
    )
    dias_semana = db.Column(db.JSON, nullable=False, default=list)
    horarios_base = db.Column(db.JSON, nullable=False, default=dict)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class ExcecaoProfissional(db.Model):
    __tablename__ = 'excecao_profissional'

    id = db.Column(db.Integer, primary_key=True)
    profissional_id = db.Column(
        db.Integer,
        db.ForeignKey('profissional.id'),
        nullable=False,
        index=True
    )
    data = db.Column(db.Date, nullable=False)
    dia_ativo = db.Column(db.Boolean, default=True)
    horarios_bloqueados = db.Column(db.JSON, default=list)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            'profissional_id',
            'data',
            name='uq_excecao_profissional_data'
        ),
    )

# =========================
# PRODUTO / ESTOQUE
# =========================
class Produto(db.Model):
    __tablename__ = 'produto'

    id = db.Column(db.Integer, primary_key=True)

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey('usuario.id'),
        nullable=False
    )

    nome = db.Column(db.String(150), nullable=False)

    quantidade_atual = db.Column(db.Integer, default=0)

    valor_compra = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    valor_venda = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    estoque_minimo = db.Column(db.Integer, default=5)

    ativo = db.Column(db.Boolean, default=True)

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    usuario = db.relationship('Usuario', backref='produtos')
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

class MovimentacaoProduto(db.Model):
    __tablename__ = "movimentacao_produto"

    id = db.Column(db.Integer, primary_key=True)

    produto_id = db.Column(
        db.Integer,
        db.ForeignKey("produto.id"),
        nullable=False
    )

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuario.id"),
        nullable=False
    )

    tipo = db.Column(db.String(20), nullable=False)

    quantidade = db.Column(db.Integer, nullable=False)

    valor_unitario = db.Column(db.Float, nullable=False)

    observacao = db.Column(db.Text)

    criado_em = db.Column(
        db.DateTime,
        default=datetime.now
    )

    produto = db.relationship("Produto")

# =========================
# PLANOS / ASSINATURAS DO SISTEMA
# =========================
class PlanoSistema(db.Model):
    __tablename__ = 'plano_sistema'

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False, index=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(255), nullable=True)
    valor_mensal = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    ciclo_meses = db.Column(db.Integer, nullable=False, default=1)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    ordem = db.Column(db.Integer, nullable=False, default=0)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    assinaturas = db.relationship(
        'AssinaturaUsuario',
        back_populates='plano',
        lazy=True
    )


class AssinaturaUsuario(db.Model):
    __tablename__ = 'assinatura_usuario'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey('usuario.id'),
        nullable=False,
        unique=True,
        index=True
    )
    plano_id = db.Column(
        db.Integer,
        db.ForeignKey('plano_sistema.id'),
        nullable=True,
        index=True
    )
    valor_mensal = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    proximo_vencimento = db.Column(db.Date, nullable=True)
    dias_aviso = db.Column(db.Integer, nullable=False, default=5)
    dias_tolerancia = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(30), nullable=False, default='ativa')
    provedor = db.Column(db.String(30), nullable=False, default='manual')
    provedor_cliente_id = db.Column(db.String(120), nullable=True)
    provedor_assinatura_id = db.Column(db.String(120), nullable=True)
    checkout_url = db.Column(db.String(500), nullable=True)
    ultimo_pagamento_em = db.Column(db.DateTime, nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    usuario = db.relationship(
        'Usuario',
        backref=db.backref(
            'assinatura_cobranca',
            uselist=False
        )
    )
    plano = db.relationship('PlanoSistema', back_populates='assinaturas')
    pagamentos = db.relationship(
        'PagamentoAssinatura',
        back_populates='assinatura',
        lazy=True,
        cascade='all, delete-orphan'
    )


class PagamentoAssinatura(db.Model):
    __tablename__ = 'pagamento_assinatura'

    id = db.Column(db.Integer, primary_key=True)
    assinatura_id = db.Column(
        db.Integer,
        db.ForeignKey('assinatura_usuario.id'),
        nullable=False,
        index=True
    )
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey('usuario.id'),
        nullable=False,
        index=True
    )
    valor = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    vencimento = db.Column(db.Date, nullable=False)
    pago_em = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(30), nullable=False, default='pendente')
    forma_pagamento = db.Column(db.String(30), nullable=False, default='manual')
    provedor = db.Column(db.String(30), nullable=False, default='manual')
    referencia_externa = db.Column(db.String(150), nullable=True, index=True)
    link_pagamento = db.Column(db.String(500), nullable=True)
    pix_copia_cola = db.Column(db.Text, nullable=True)
    observacao = db.Column(db.String(255), nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    assinatura = db.relationship(
        'AssinaturaUsuario',
        back_populates='pagamentos'
    )
    usuario = db.relationship('Usuario')
