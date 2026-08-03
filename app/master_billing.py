import calendar
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func, or_

from .models import (
    AssinaturaUsuario,
    PagamentoAssinatura,
    PlanoSistema,
    Usuario,
    db,
)

master_financeiro = Blueprint('master_financeiro', __name__)


PLANOS_PADRAO = (
    {
        'codigo': 'basico',
        'nome': 'Plano Básico',
        'descricao': 'Plano inicial. Defina o valor antes de vinculá-lo aos usuários.',
        'ordem': 10,
    },
    {
        'codigo': 'premium',
        'nome': 'Plano Premium',
        'descricao': 'Plano intermediário. Defina o valor conforme sua operação.',
        'ordem': 20,
    },
    {
        'codigo': 'vip',
        'nome': 'Plano VIP',
        'descricao': 'Plano completo. Defina o valor conforme sua operação.',
        'ordem': 30,
    },
)


def master_required(funcao):
    @wraps(funcao)
    def wrapper(*args, **kwargs):
        usuario = db.session.get(Usuario, session.get('user_id'))
        if not usuario or not usuario.is_masteradm:
            return redirect(url_for('auth.login'))
        return funcao(*args, **kwargs)

    return wrapper


def normalizar_codigo(valor):
    texto = str(valor or '').strip().lower()
    texto = re.sub(r'[^a-z0-9]+', '-', texto).strip('-')
    return texto


def decimal_formulario(valor, padrao='0'):
    texto = str(valor if valor is not None else padrao).strip()
    texto = texto.replace('R$', '').replace(' ', '')
    if ',' in texto and '.' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    else:
        texto = texto.replace(',', '.')

    try:
        resultado = Decimal(texto)
    except (InvalidOperation, ValueError):
        resultado = Decimal(padrao)

    return max(resultado, Decimal('0'))


def data_formulario(valor):
    if not valor:
        return None
    try:
        return datetime.strptime(str(valor), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def adicionar_meses(data_base, quantidade=1):
    quantidade = max(int(quantidade or 1), 1)
    indice_mes = data_base.month - 1 + quantidade
    ano = data_base.year + indice_mes // 12
    mes = indice_mes % 12 + 1
    dia = min(data_base.day, calendar.monthrange(ano, mes)[1])
    return data_base.replace(year=ano, month=mes, day=dia)


def plano_id_da_solicitacao(pagamento):
    referencia = str(pagamento.referencia_externa or '')
    if not referencia.startswith('troca-plano:'):
        return None

    try:
        return int(referencia.split(':')[1])
    except (IndexError, TypeError, ValueError):
        return None


def solicitacoes_plano_pendentes():
    pagamentos = (
        PagamentoAssinatura.query
        .filter(
            PagamentoAssinatura.status == 'pendente',
            PagamentoAssinatura.referencia_externa.like('troca-plano:%'),
        )
        .order_by(PagamentoAssinatura.criado_em.desc())
        .all()
    )

    registros = []
    for pagamento in pagamentos:
        plano_id = plano_id_da_solicitacao(pagamento)
        plano = db.session.get(PlanoSistema, plano_id) if plano_id else None
        if not plano:
            continue
        registros.append({
            'pagamento': pagamento,
            'usuario': pagamento.usuario,
            'assinatura': pagamento.assinatura,
            'plano': plano,
        })

    return registros


def garantir_planos_padrao():
    existentes = {
        plano.codigo
        for plano in PlanoSistema.query.with_entities(PlanoSistema.codigo).all()
    }

    criados = False
    for dados in PLANOS_PADRAO:
        if dados['codigo'] in existentes:
            continue
        db.session.add(PlanoSistema(
            codigo=dados['codigo'],
            nome=dados['nome'],
            descricao=dados['descricao'],
            valor_mensal=Decimal('0'),
            ciclo_meses=1,
            ativo=True,
            ordem=dados['ordem'],
        ))
        criados = True

    if criados:
        db.session.commit()


def calcular_status_assinatura(assinatura, hoje=None):
    hoje = hoje or date.today()

    if not assinatura:
        return {
            'codigo': 'nao_configurada',
            'rotulo': 'Não configurada',
            'classe': 'neutro',
            'dias': None,
        }

    if assinatura.status == 'cancelada':
        return {
            'codigo': 'cancelada',
            'rotulo': 'Cancelada',
            'classe': 'inativo',
            'dias': None,
        }

    if assinatura.status == 'pausada':
        return {
            'codigo': 'pausada',
            'rotulo': 'Pausada',
            'classe': 'atencao',
            'dias': None,
        }

    vencimento = assinatura.proximo_vencimento
    if not vencimento:
        return {
            'codigo': 'sem_vencimento',
            'rotulo': 'Sem vencimento',
            'classe': 'neutro',
            'dias': None,
        }

    dias = (vencimento - hoje).days
    tolerancia = max(int(assinatura.dias_tolerancia or 0), 0)
    aviso = max(int(assinatura.dias_aviso or 0), 0)

    if dias < -tolerancia:
        return {
            'codigo': 'vencida',
            'rotulo': 'Vencida',
            'classe': 'vencido',
            'dias': abs(dias),
        }

    if dias < 0:
        return {
            'codigo': 'tolerancia',
            'rotulo': 'Em tolerância',
            'classe': 'atencao',
            'dias': abs(dias),
        }

    if dias == 0:
        return {
            'codigo': 'vence_hoje',
            'rotulo': 'Vence hoje',
            'classe': 'atencao',
            'dias': 0,
        }

    if dias <= aviso:
        return {
            'codigo': 'vence_em_breve',
            'rotulo': f'Vence em {dias} dia' + ('s' if dias != 1 else ''),
            'classe': 'atencao',
            'dias': dias,
        }

    return {
        'codigo': 'em_dia',
        'rotulo': 'Em dia',
        'classe': 'ativo',
        'dias': dias,
    }


def obter_aviso_assinatura(usuario_id):
    assinatura = AssinaturaUsuario.query.filter_by(usuario_id=usuario_id).first()
    status = calcular_status_assinatura(assinatura)

    if not assinatura or status['codigo'] in {
        'nao_configurada', 'sem_vencimento', 'em_dia', 'cancelada', 'pausada'
    }:
        return None

    vencimento = assinatura.proximo_vencimento.strftime('%d/%m/%Y')
    link = assinatura.checkout_url

    if status['codigo'] == 'vence_em_breve':
        mensagem = (
            f'Sua assinatura vence em {status["dias"]} '
            f'dia{"s" if status["dias"] != 1 else ""}, em {vencimento}. '
            'Quando possível, programe a renovação para manter o serviço contínuo.'
        )
        nivel = 'aviso'
    elif status['codigo'] == 'vence_hoje':
        mensagem = (
            f'Sua assinatura vence hoje ({vencimento}). '
            'A renovação pode ser feita sem interromper o uso do sistema.'
        )
        nivel = 'aviso'
    elif status['codigo'] == 'tolerancia':
        mensagem = (
            f'O vencimento da assinatura foi em {vencimento}. '
            'O acesso permanece disponível durante o período de tolerância.'
        )
        nivel = 'aviso'
    else:
        mensagem = (
            f'Identificamos que a assinatura venceu em {vencimento}. '
            'Regularize quando possível para evitar uma futura interrupção do serviço.'
        )
        nivel = 'vencido'

    return {
        'nivel': nivel,
        'mensagem': mensagem,
        'vencimento': vencimento,
        'link_pagamento': link,
        'status': status,
    }


def usuarios_com_status():
    usuarios = (
        Usuario.query
        .filter(Usuario.is_masteradm.is_(False))
        .order_by(Usuario.criado_em.desc(), Usuario.username)
        .all()
    )
    return [
        {
            'usuario': usuario,
            'assinatura': usuario.assinatura_cobranca,
            'financeiro': calcular_status_assinatura(usuario.assinatura_cobranca),
        }
        for usuario in usuarios
    ]


@master_financeiro.route('/masteradm/dashboard')
@master_required
def dashboard():
    garantir_planos_padrao()
    registros = usuarios_com_status()
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)

    total_recebido_mes = (
        db.session.query(func.coalesce(func.sum(PagamentoAssinatura.valor), 0))
        .filter(
            PagamentoAssinatura.status == 'pago',
            PagamentoAssinatura.pago_em.isnot(None),
            func.date(PagamentoAssinatura.pago_em) >= inicio_mes.isoformat(),
        )
        .scalar()
    )

    categorias = {
        'total': len(registros),
        'ativos': sum(1 for item in registros if item['usuario'].status == 'ativo'),
        'inativos': sum(1 for item in registros if item['usuario'].status != 'ativo'),
        'em_dia': sum(1 for item in registros if item['financeiro']['codigo'] == 'em_dia'),
        'avisos': sum(
            1 for item in registros
            if item['financeiro']['codigo'] in {'vence_em_breve', 'vence_hoje', 'tolerancia'}
        ),
        'vencidos': sum(1 for item in registros if item['financeiro']['codigo'] == 'vencida'),
        'sem_configuracao': sum(
            1 for item in registros
            if item['financeiro']['codigo'] in {'nao_configurada', 'sem_vencimento'}
        ),
    }

    def ordenar_por_vencimento(item):
        assinatura = item.get('assinatura')
        if assinatura and assinatura.proximo_vencimento:
            return assinatura.proximo_vencimento
        return date.max

    solicitacoes_pendentes = solicitacoes_plano_pendentes()
    assinaturas_vencidas = sorted(
        [item for item in registros if item['financeiro']['codigo'] == 'vencida'],
        key=ordenar_por_vencimento,
    )
    assinaturas_atencao = sorted(
        [
            item for item in registros
            if item['financeiro']['codigo'] in {
                'vence_em_breve', 'vence_hoje', 'tolerancia'
            }
        ],
        key=ordenar_por_vencimento,
    )

    alertas_master = {
        'solicitacoes_total': len(solicitacoes_pendentes),
        'solicitacoes_recentes': solicitacoes_pendentes[:3],
        'vencidas_total': len(assinaturas_vencidas),
        'vencidas_recentes': assinaturas_vencidas[:3],
        'atencao_total': len(assinaturas_atencao),
        'atencao_recentes': assinaturas_atencao[:3],
    }
    alertas_master['total_geral'] = (
        alertas_master['solicitacoes_total']
        + alertas_master['vencidas_total']
        + alertas_master['atencao_total']
    )

    planos = (
        PlanoSistema.query
        .order_by(PlanoSistema.ordem, PlanoSistema.nome)
        .all()
    )

    return render_template(
        'masteradm.html',
        categorias=categorias,
        planos=planos,
        total_recebido_mes=total_recebido_mes,
        usuarios_recentes=registros[:6],
        alertas_master=alertas_master,
    )


@master_financeiro.route('/masteradm/usuarios')
@master_required
def usuarios():
    garantir_planos_padrao()
    busca = str(request.args.get('q') or '').strip()
    plano = str(request.args.get('plano') or '').strip()
    conta_status = str(request.args.get('conta_status') or '').strip()
    financeiro = str(request.args.get('financeiro') or '').strip()

    query = Usuario.query.filter(Usuario.is_masteradm.is_(False))

    if busca:
        termo = f'%{busca}%'
        query = query.filter(or_(
            Usuario.username.ilike(termo),
            Usuario.nome.ilike(termo),
            Usuario.empresa.ilike(termo),
            Usuario.email.ilike(termo),
        ))

    if plano:
        query = query.filter(Usuario.plano == plano)

    if conta_status:
        query = query.filter(Usuario.status == conta_status)

    lista = query.order_by(Usuario.criado_em.desc(), Usuario.username).all()
    registros = []
    for usuario in lista:
        status_financeiro = calcular_status_assinatura(usuario.assinatura_cobranca)
        if financeiro:
            if financeiro == 'sem_configuracao':
                if status_financeiro['codigo'] not in {'nao_configurada', 'sem_vencimento'}:
                    continue
            elif status_financeiro['codigo'] != financeiro:
                continue
        registros.append({
            'usuario': usuario,
            'assinatura': usuario.assinatura_cobranca,
            'financeiro': status_financeiro,
        })

    planos = PlanoSistema.query.order_by(PlanoSistema.ordem, PlanoSistema.nome).all()

    return render_template(
        'usuarios.html',
        registros=registros,
        planos=planos,
        filtros={
            'q': busca,
            'plano': plano,
            'conta_status': conta_status,
            'financeiro': financeiro,
        },
    )


@master_financeiro.route('/masteradm/usuarios/<int:usuario_id>/status', methods=['POST'])
@master_required
def alternar_status_usuario(usuario_id):
    usuario = Usuario.query.filter_by(id=usuario_id, is_masteradm=False).first_or_404()
    usuario.status = 'inativo' if usuario.status == 'ativo' else 'ativo'
    db.session.commit()
    flash('Status de acesso atualizado.')
    return redirect(request.referrer or url_for('master_financeiro.usuarios'))


@master_financeiro.route('/masteradm/planos', methods=['GET', 'POST'])
@master_required
def planos():
    garantir_planos_padrao()

    if request.method == 'POST':
        codigo = normalizar_codigo(request.form.get('codigo') or request.form.get('nome'))
        nome = str(request.form.get('nome') or '').strip()

        if not codigo or not nome:
            flash('Informe nome e código do plano.')
            return redirect(url_for('master_financeiro.planos'))

        if PlanoSistema.query.filter_by(codigo=codigo).first():
            flash('Já existe um plano com esse código.')
            return redirect(url_for('master_financeiro.planos'))

        plano = PlanoSistema(
            codigo=codigo,
            nome=nome,
            descricao=str(request.form.get('descricao') or '').strip() or None,
            valor_mensal=decimal_formulario(request.form.get('valor_mensal')),
            ciclo_meses=max(request.form.get('ciclo_meses', type=int) or 1, 1),
            ativo=True,
            ordem=request.form.get('ordem', type=int) or 0,
        )
        db.session.add(plano)
        db.session.commit()
        flash('Plano criado com sucesso.')
        return redirect(url_for('master_financeiro.planos'))

    lista = PlanoSistema.query.order_by(PlanoSistema.ordem, PlanoSistema.nome).all()
    return render_template('master_planos.html', planos=lista)


@master_financeiro.route('/masteradm/planos/<int:plano_id>/editar', methods=['POST'])
@master_required
def editar_plano(plano_id):
    plano = PlanoSistema.query.get_or_404(plano_id)
    plano.nome = str(request.form.get('nome') or plano.nome).strip()
    plano.descricao = str(request.form.get('descricao') or '').strip() or None
    plano.valor_mensal = decimal_formulario(
        request.form.get('valor_mensal'),
        str(plano.valor_mensal or 0),
    )
    plano.ciclo_meses = max(request.form.get('ciclo_meses', type=int) or 1, 1)
    plano.ordem = request.form.get('ordem', type=int) or 0
    plano.ativo = request.form.get('ativo') == '1'
    db.session.commit()
    flash('Plano atualizado.')
    return redirect(url_for('master_financeiro.planos'))


@master_financeiro.route('/masteradm/pagamentos')
@master_required
def pagamentos():
    registros = usuarios_com_status()
    filtro = str(request.args.get('status') or '').strip()
    if filtro:
        if filtro == 'sem_configuracao':
            registros = [
                item for item in registros
                if item['financeiro']['codigo'] in {'nao_configurada', 'sem_vencimento'}
            ]
        else:
            registros = [item for item in registros if item['financeiro']['codigo'] == filtro]

    pagamentos_recentes = (
        PagamentoAssinatura.query
        .order_by(PagamentoAssinatura.criado_em.desc())
        .limit(20)
        .all()
    )

    return render_template(
        'master_pagamentos.html',
        registros=registros,
        pagamentos_recentes=pagamentos_recentes,
        solicitacoes_planos=solicitacoes_plano_pendentes(),
        filtro=filtro,
    )


@master_financeiro.route(
    '/masteradm/solicitacoes-planos/<int:pagamento_id>/confirmar',
    methods=['POST'],
)
@master_required
def confirmar_solicitacao_plano(pagamento_id):
    pagamento = PagamentoAssinatura.query.filter_by(
        id=pagamento_id,
        status='pendente',
    ).first_or_404()

    plano_id = plano_id_da_solicitacao(pagamento)
    plano = db.session.get(PlanoSistema, plano_id) if plano_id else None
    assinatura = pagamento.assinatura
    usuario = pagamento.usuario

    if not plano or not assinatura or not usuario:
        flash('A solicitação não possui dados suficientes para ser confirmada.')
        return redirect(url_for('master_financeiro.pagamentos'))

    hoje = date.today()
    ciclo = max(int(plano.ciclo_meses or 1), 1)
    base_vencimento = assinatura.proximo_vencimento
    if not base_vencimento or base_vencimento < hoje:
        base_vencimento = hoje

    assinatura.plano = plano
    assinatura.valor_mensal = plano.valor_mensal
    assinatura.status = 'ativa'
    assinatura.provedor = pagamento.provedor or 'manual'
    assinatura.ultimo_pagamento_em = datetime.now()
    assinatura.proximo_vencimento = adicionar_meses(base_vencimento, ciclo)

    usuario.plano = plano.codigo

    pagamento.status = 'pago'
    pagamento.pago_em = datetime.now()
    pagamento.forma_pagamento = request.form.get('forma_pagamento') or 'manual'
    pagamento.observacao = (
        (pagamento.observacao or '').strip()
        + ' Pagamento confirmado e plano aplicado pelo MASTER ADM.'
    ).strip()

    db.session.commit()
    flash(f'Plano {plano.nome} ativado para {usuario.nome or usuario.username}.')
    return redirect(url_for('master_financeiro.pagamentos'))


@master_financeiro.route(
    '/masteradm/solicitacoes-planos/<int:pagamento_id>/cancelar',
    methods=['POST'],
)
@master_required
def cancelar_solicitacao_plano(pagamento_id):
    pagamento = PagamentoAssinatura.query.filter_by(
        id=pagamento_id,
        status='pendente',
    ).first_or_404()

    if plano_id_da_solicitacao(pagamento) is None:
        flash('Este registro não é uma solicitação de mudança de plano.')
        return redirect(url_for('master_financeiro.pagamentos'))

    pagamento.status = 'cancelado'
    pagamento.observacao = (
        (pagamento.observacao or '').strip()
        + ' Solicitação cancelada pelo MASTER ADM.'
    ).strip()
    db.session.commit()
    flash('Solicitação de mudança cancelada.')
    return redirect(url_for('master_financeiro.pagamentos'))


@master_financeiro.route('/masteradm/usuarios/<int:usuario_id>/assinatura', methods=['GET', 'POST'])
@master_required
def assinatura_usuario(usuario_id):
    garantir_planos_padrao()
    usuario = Usuario.query.filter_by(id=usuario_id, is_masteradm=False).first_or_404()
    assinatura = usuario.assinatura_cobranca

    if request.method == 'POST':
        plano_id = request.form.get('plano_id', type=int)
        plano = PlanoSistema.query.filter_by(id=plano_id, ativo=True).first()

        if not plano:
            flash('Selecione um plano válido.')
            return redirect(url_for(
                'master_financeiro.assinatura_usuario',
                usuario_id=usuario.id,
            ))

        if not assinatura:
            assinatura = AssinaturaUsuario(usuario_id=usuario.id)
            db.session.add(assinatura)

        assinatura.plano = plano
        assinatura.valor_mensal = decimal_formulario(
            request.form.get('valor_mensal'),
            str(plano.valor_mensal or 0),
        )
        assinatura.proximo_vencimento = data_formulario(
            request.form.get('proximo_vencimento')
        )
        assinatura.dias_aviso = max(request.form.get('dias_aviso', type=int) or 0, 0)
        assinatura.dias_tolerancia = max(
            request.form.get('dias_tolerancia', type=int) or 0,
            0,
        )
        assinatura.status = request.form.get('status') or 'ativa'
        assinatura.provedor = request.form.get('provedor') or 'manual'
        assinatura.checkout_url = str(request.form.get('checkout_url') or '').strip() or None
        usuario.plano = plano.codigo
        db.session.commit()
        flash('Assinatura atualizada com sucesso.')
        return redirect(url_for(
            'master_financeiro.assinatura_usuario',
            usuario_id=usuario.id,
        ))

    planos = PlanoSistema.query.filter_by(ativo=True).order_by(
        PlanoSistema.ordem,
        PlanoSistema.nome,
    ).all()
    historico = []
    if assinatura:
        historico = (
            PagamentoAssinatura.query
            .filter_by(assinatura_id=assinatura.id)
            .order_by(PagamentoAssinatura.vencimento.desc())
            .all()
        )

    return render_template(
        'master_assinatura_usuario.html',
        usuario=usuario,
        assinatura=assinatura,
        status_financeiro=calcular_status_assinatura(assinatura),
        planos=planos,
        historico=historico,
        now_date=date.today().isoformat(),
    )


@master_financeiro.route(
    '/masteradm/usuarios/<int:usuario_id>/pagamentos/registrar',
    methods=['POST'],
)
@master_required
def registrar_pagamento(usuario_id):
    usuario = Usuario.query.filter_by(id=usuario_id, is_masteradm=False).first_or_404()
    assinatura = usuario.assinatura_cobranca

    if not assinatura or not assinatura.proximo_vencimento:
        flash('Configure a assinatura e o vencimento antes de registrar o pagamento.')
        return redirect(url_for(
            'master_financeiro.assinatura_usuario',
            usuario_id=usuario.id,
        ))

    pago_em_data = data_formulario(request.form.get('pago_em')) or date.today()
    pagamento = PagamentoAssinatura(
        assinatura_id=assinatura.id,
        usuario_id=usuario.id,
        valor=decimal_formulario(
            request.form.get('valor'),
            str(assinatura.valor_mensal or 0),
        ),
        vencimento=data_formulario(request.form.get('vencimento'))
        or assinatura.proximo_vencimento,
        pago_em=datetime.combine(pago_em_data, datetime.now().time()),
        status='pago',
        forma_pagamento=request.form.get('forma_pagamento') or 'manual',
        provedor=request.form.get('provedor') or assinatura.provedor or 'manual',
        referencia_externa=str(request.form.get('referencia_externa') or '').strip() or None,
        observacao=str(request.form.get('observacao') or '').strip() or None,
    )
    db.session.add(pagamento)
    assinatura.ultimo_pagamento_em = pagamento.pago_em

    if request.form.get('avancar_vencimento') == '1':
        ciclo = assinatura.plano.ciclo_meses if assinatura.plano else 1
        assinatura.proximo_vencimento = adicionar_meses(
            assinatura.proximo_vencimento,
            ciclo,
        )

    db.session.commit()
    flash('Pagamento registrado com sucesso.')
    return redirect(url_for(
        'master_financeiro.assinatura_usuario',
        usuario_id=usuario.id,
    ))


@master_financeiro.route('/masteradm/avisos')
@master_required
def avisos():
    registros = [
        item for item in usuarios_com_status()
        if item['financeiro']['codigo'] in {
            'vence_em_breve', 'vence_hoje', 'tolerancia', 'vencida'
        }
    ]
    registros.sort(
        key=lambda item: item['assinatura'].proximo_vencimento
        if item['assinatura'] and item['assinatura'].proximo_vencimento
        else date.max
    )
    return render_template('master_avisos.html', registros=registros)


@master_financeiro.route('/masteradm/integracoes')
@master_required
def integracoes():
    asaas_api_key_configurada = bool(os.getenv('ASAAS_API_KEY'))
    asaas_ambiente = str(os.getenv('ASAAS_ENVIRONMENT') or 'sandbox').lower()

    assinaturas_asaas = AssinaturaUsuario.query.filter(
        AssinaturaUsuario.provedor == 'asaas'
    ).count()

    return render_template(
        'master_integracoes.html',
        asaas_api_key_configurada=asaas_api_key_configurada,
        asaas_ambiente=asaas_ambiente,
        assinaturas_asaas=assinaturas_asaas,
    )
