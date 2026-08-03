from flask import Blueprint, render_template, request, redirect, flash, url_for, jsonify, session
from functools import wraps
from datetime import datetime
from copy import deepcopy
from collections import Counter
import re
import unicodedata
from sqlalchemy import extract, func, or_
from flask import current_app
from . import db
from .models import (
    Agendamento,
    Cliente,
    Produto,
    MovimentacaoProduto,
    Profissional,
    ProfissionalServico,
    AgendamentoProfissional,
    ConfiguracaoProfissional,
    ExcecaoProfissional,
)
from app.models import Servico, Usuario, ConfiguracaoAgenda, ExcecaoAgenda
from .themes import (
    TEMAS_VALIDOS,
    normalizar_fonte_titulo,
    normalizar_tema,
)

main = Blueprint('main', __name__)

from flask import session, redirect
from app.models import Usuario  # ajusta conforme seu projeto
from functools import wraps
from datetime import datetime, date, timedelta

def master_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user_id = session.get('user_id')
        user = Usuario.query.get(user_id)

        if not user or not user.is_masteradm:
            return redirect('/login')

        return f(*args, **kwargs)
    return wrapper
# =========================
# AUTH DECORATOR
# =========================
@main.route('/criar-masteradm')
def criar_masteradm():
    return render_template('criar_masteradm.html')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function


def slug_profissional(nome):
    texto = unicodedata.normalize('NFKD', str(nome or ''))
    texto = texto.encode('ascii', 'ignore').decode('ascii').lower()
    texto = re.sub(r'[^a-z0-9]+', '-', texto).strip('-')
    return texto or 'profissional'


def garantir_profissional_principal(usuario):
    principal = Profissional.query.filter_by(
        usuario_id=usuario.id,
        principal=True
    ).first()

    if principal:
        return principal

    existente = Profissional.query.filter_by(usuario_id=usuario.id).first()
    if existente:
        existente.principal = True
        db.session.commit()
        return existente

    nome = usuario.nome_fantasia or usuario.nome or usuario.username
    principal = Profissional(
        usuario_id=usuario.id,
        nome=nome,
        slug=slug_profissional(nome),
        especialidade='Profissional principal',
        ativo=True,
        principal=True
    )
    db.session.add(principal)
    db.session.commit()
    return principal


def garantir_servicos_profissional_principal(usuario, principal=None):
    principal = principal or garantir_profissional_principal(usuario)

    servicos_sem_profissional = (
        Servico.query
        .outerjoin(
            ProfissionalServico,
            ProfissionalServico.servico_id == Servico.id
        )
        .filter(
            Servico.usuario_id == usuario.id,
            ProfissionalServico.id.is_(None)
        )
        .all()
    )

    if not servicos_sem_profissional:
        return principal

    for servico in servicos_sem_profissional:
        db.session.add(ProfissionalServico(
            profissional_id=principal.id,
            servico_id=servico.id
        ))

    db.session.commit()
    return principal


def garantir_configuracao_profissional(profissional):
    if profissional.configuracao_agenda:
        return profissional.configuracao_agenda

    origem = None
    if not profissional.principal:
        principal = Profissional.query.filter_by(
            usuario_id=profissional.usuario_id,
            principal=True
        ).first()
        if principal and principal.configuracao_agenda:
            origem = principal.configuracao_agenda

    if origem is None:
        origem = ConfiguracaoAgenda.query.filter_by(
            usuario_id=profissional.usuario_id
        ).first()

    dias_semana = deepcopy(origem.dias_semana) if origem else []
    horarios_base = deepcopy(origem.horarios_base) if origem else {
        'semana': [],
        'sabado': []
    }

    if isinstance(dias_semana, str):
        try:
            dias_semana = [
                int(item.strip())
                for item in dias_semana.split(',')
                if item.strip()
            ]
        except ValueError:
            dias_semana = []

    if isinstance(horarios_base, str):
        horarios_base = {
            'semana': [
                item.strip()
                for item in horarios_base.split(',')
                if item.strip()
            ],
            'sabado': []
        }
    elif isinstance(horarios_base, list):
        horarios_base = {
            'semana': horarios_base,
            'sabado': []
        }

    configuracao = ConfiguracaoProfissional(
        profissional_id=profissional.id,
        dias_semana=dias_semana,
        horarios_base=horarios_base
    )
    db.session.add(configuracao)
    db.session.commit()
    return configuracao


def garantir_agendas_profissionais(usuario):
    principal = garantir_servicos_profissional_principal(usuario)
    profissionais = Profissional.query.filter_by(usuario_id=usuario.id).all()

    for profissional in profissionais:
        garantir_configuracao_profissional(profissional)

    excecoes_legadas = ExcecaoAgenda.query.filter_by(usuario_id=usuario.id).all()
    for excecao in excecoes_legadas:
        existente = ExcecaoProfissional.query.filter_by(
            profissional_id=principal.id,
            data=excecao.data
        ).first()
        if not existente:
            db.session.add(ExcecaoProfissional(
                profissional_id=principal.id,
                data=excecao.data,
                dia_ativo=excecao.dia_ativo,
                horarios_bloqueados=deepcopy(excecao.horarios_bloqueados or [])
            ))

    agendamentos_sem_profissional = (
        Agendamento.query
        .outerjoin(
            AgendamentoProfissional,
            AgendamentoProfissional.agendamento_id == Agendamento.id
        )
        .filter(
            Agendamento.usuario_id == usuario.id,
            AgendamentoProfissional.id.is_(None)
        )
        .all()
    )

    for agendamento in agendamentos_sem_profissional:
        profissional_id = principal.id
        if agendamento.servico and agendamento.servico.vinculo_profissional:
            profissional_id = agendamento.servico.vinculo_profissional.profissional_id
        db.session.add(AgendamentoProfissional(
            profissional_id=profissional_id,
            agendamento_id=agendamento.id
        ))

    db.session.commit()
    return principal


def profissional_do_servico(servico):
    usuario = db.session.get(Usuario, servico.usuario_id)
    garantir_agendas_profissionais(usuario)
    if servico.vinculo_profissional:
        return servico.vinculo_profissional.profissional
    return garantir_profissional_principal(usuario)


# =========================
# ROTAS PÚBLICAS
# =========================
@main.route('/', methods=['GET', 'POST'])
def home():
    return redirect('/service')


@main.route('/agendar/<int:servico_id>')
def agendar_por_id(servico_id):
    servico = Servico.query.get_or_404(servico_id)
    usuario = Usuario.query.get_or_404(servico.usuario_id)
    profissional = profissional_do_servico(servico)

    return render_template(
        'agendar_servico.html',
        servico=servico,
        usuario=usuario,
        profissional=profissional
    )


@main.route('/confirmar_agendamento', methods=['POST'])
def confirmar_agendamento():
    servico_id = request.form.get('servico_id')
    data_str = request.form.get('data')
    hora_str = request.form.get('hora')

    if not servico_id or not data_str or not hora_str:
        return "Dados insuficientes.", 400

    servico = Servico.query.get_or_404(int(servico_id))
    usuario = Usuario.query.get_or_404(servico.usuario_id)
    profissional = profissional_do_servico(servico)

    try:
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
        inicio_novo = horario_para_datetime(data_obj, hora_str)
    except Exception:
        return "Data ou horário inválido.", 400

    duracao = minutos_servico(servico)
    fim_novo = inicio_novo + timedelta(minutes=duracao)

    horarios_base = obter_horarios_base_profissional(
        profissional.id,
        data_obj
    )

    if not servico_cabe_no_expediente(
            data_obj,
            horarios_base,
            inicio_novo,
            fim_novo
    ):
        return (
            "Este serviço não possui tempo disponível para este horário.",
            409
        )

    if inicio_novo <= datetime.now():
        return "Horário indisponível. Escolha outro horário.", 409

    conflito = existe_conflito_agendamento(
        usuario_id=servico.usuario_id,
        profissional_id=profissional.id,
        data=data_obj,
        inicio_novo=inicio_novo,
        fim_novo=fim_novo
    )

    if conflito:
        return "Horário indisponível para a duração deste serviço. Escolha outro horário.", 409

    return render_template(
        'confirmar_dados.html',
        servico=servico.titulo,
        data=data_str,
        hora=hora_str,
        servico_id=servico.id,
        usuario=servico.usuario,
        profissional=profissional
    )


from flask import current_app

@main.route('/salvar_agendamento', methods=['POST'])
def salvar_agendamento():
    from flask import request, render_template, current_app
    from datetime import datetime
    import time

    print("FORM RECEBIDO:", request.form)

    nome = request.form.get('nome')
    telefone = request.form.get('telefone')
    data_str = request.form.get('data')
    hora_str = request.form.get('hora')
    sid = request.form.get('servico_id')

    # 🔴 validação básica
    if not all([nome, telefone, data_str, hora_str, sid]):
        current_app.logger.warning("Falha agendamento: dados incompletos")
        return "Erro: dados incompletos no envio", 400

    nome = ' '.join(nome.strip().split())

    partes_nome = nome.split()

    if len(partes_nome) < 2:
        return "Informe nome e sobrenome.", 400

    # ==============================
    # 🔒 VALIDA TELEFONE (SIMPLES)
    # ==============================
    telefone_limpo = ''.join(filter(str.isdigit, telefone))

    if not telefone_limpo:
        return "Digite apenas números no telefone", 400

    # aceita padrão com DDD (10 ou 11 dígitos)
    if len(telefone_limpo) < 10 or len(telefone_limpo) > 11:
        return "Telefone inválido. Use DDD + número (ex: 19999999999)", 400

    telefone = telefone_limpo

    try:
        data = datetime.strptime(data_str, '%Y-%m-%d').date()
        hora = datetime.strptime(hora_str, '%H:%M').time()
        sid = int(sid)
    except Exception as e:
        current_app.logger.error(f"Erro ao processar dados agendamento: {e}")
        return f"Erro ao processar dados: {e}", 400

    servico = Servico.query.get_or_404(sid)
    usuario = Usuario.query.get_or_404(servico.usuario_id)
    profissional = profissional_do_servico(servico)

    inicio_novo = datetime.combine(data, hora)
    duracao = minutos_servico(servico)
    fim_novo = inicio_novo + timedelta(minutes=duracao)

    horarios_base = obter_horarios_base_profissional(
        profissional.id,
        data
    )

    if not servico_cabe_no_expediente(
            data,
            horarios_base,
            inicio_novo,
            fim_novo
    ):
        return (
            "Este serviço não possui tempo disponível para este horário.",
            409
        )

    if inicio_novo <= datetime.now():
        return "Horário indisponível. Escolha outro horário.", 409

    conflito = existe_conflito_agendamento(
        usuario_id=servico.usuario_id,
        profissional_id=profissional.id,
        data=data,
        inicio_novo=inicio_novo,
        fim_novo=fim_novo
    )

    if conflito:
        return "Horário indisponível para a duração deste serviço. Escolha outro horário.", 409

    # =====================================
    # LOCALIZA OU CRIA O CLIENTE
    # =====================================
    cliente = Cliente.query.filter_by(
        usuario_id=servico.usuario_id,
        telefone=telefone
    ).first()

    if not cliente:
        cliente = Cliente(
            usuario_id=servico.usuario_id,
            nome=nome,
            telefone=telefone,
            recorrente='nao'
        )

        db.session.add(cliente)
        db.session.flush()  # gera o ID antes do commit

    else:
        # Atualiza o nome caso tenha sido alterado
        cliente.nome = nome

    novo = Agendamento(
        usuario_id=servico.usuario_id,
        cliente_id=cliente.id,
        nome=nome,
        telefone=telefone,
        data=data,
        horario=hora,
        servico_id=servico.id
    )

    db.session.add(novo)
    db.session.flush()
    db.session.add(AgendamentoProfissional(
        profissional_id=profissional.id,
        agendamento_id=novo.id
    ))
    db.session.commit()

    current_app.logger.info(
        f"Agendamento criado | usuario_id={servico.usuario_id} | nome={nome} | servico={servico.titulo} | data={data} {hora}"
    )

    # ==============================
    # 🚀 ENVIO WHATSAPP (BACKGROUND)
    # ==============================
    try:
        # 🔥 número já limpo
        numero = telefone

        if numero.startswith("0"):
            numero = numero[1:]

        if not numero.startswith("55"):
            numero = "55" + numero

        print("ENVIANDO PARA:", numero)

        mensagem_cliente = f"""📅 *Agendamento Confirmado!*

👤 Nome: {nome}
💼 Profissional: {profissional.nome}
🛠️ Serviço: {servico.titulo}
📆 Data: {data.strftime('%d/%m/%Y')}
⏰ Hora: {hora.strftime('%H:%M')}

✅ Seu horário está reservado!
"""

        grupo_id = "120363406795388890@g.us"

        mensagem_grupo = f"""📢 *Novo Agendamento*

👤 {nome}
📞 {telefone}
💼 {profissional.nome}
🛠️ {servico.titulo}
📆 {data.strftime('%d/%m/%Y')}
⏰ {hora.strftime('%H:%M')}
"""

        import threading

        threading.Thread(
            target=envio_whatsapp_background,
            args=(
                servico.usuario_id,
                numero,
                mensagem_cliente,
                grupo_id,
                mensagem_grupo
            ),
            daemon=True
        ).start()

    except Exception as e:
        print("ERRO WHATSAPP:", e)
        current_app.logger.error(
            f"WhatsApp FAIL | usuario_id={servico.usuario_id} | nome={nome} | telefone={telefone} | erro={str(e)}"
        )

    # ==============================

    slug = servico.usuario.slug
    retorno_url = url_for(
        'main.agenda_profissional_publica',
        slug=slug,
        profissional_slug=profissional.slug
    )

    return render_template(
        'confirmacao.html',
        nome=nome,
        servico=servico.titulo,
        data_str=data.strftime('%d/%m'),
        hora_str=hora.strftime('%H:%M'),
        slug=slug,
        usuario=servico.usuario,
        profissional=profissional,
        retorno_url=retorno_url
    )

@main.route('/cancelar/<int:id>', methods=['POST'])
def cancelar(id):
    from flask import redirect, flash
    import threading

    agendamento = Agendamento.query.get_or_404(id)

    slug = agendamento.servico.usuario.slug
    user_id = agendamento.servico.usuario_id

    telefone = agendamento.telefone
    nome = agendamento.nome if hasattr(agendamento, 'nome') else ''
    servico_nome = agendamento.servico.titulo if agendamento.servico else 'Serviço'
    data = agendamento.data.strftime('%d/%m/%Y')
    hora = agendamento.horario.strftime('%H:%M')

    db.session.delete(agendamento)
    db.session.commit()

    # ==============================
    # 🚀 ENVIO WHATSAPP (BACKGROUND)
    # ==============================
    try:
        numero = ''.join(filter(str.isdigit, telefone))

        if numero.startswith("0"):
            numero = numero[1:]

        if not numero.startswith("55"):
            numero = "55" + numero

        print("CANCELAMENTO → ENVIANDO PARA:", numero)

        # 👤 CLIENTE
        mensagem_cliente = f"""❌ *Agendamento Cancelado*

👤 Nome: {nome}
🛠️ Serviço: {servico_nome}
📆 Data: {data}
⏰ Hora: {hora}

Seu horário foi cancelado com sucesso.
"""

        # 👥 GRUPO
        grupo_id = "120363406795388890@g.us"

        mensagem_grupo = f"""❌ *Cancelamento*

👤 {nome}
📞 {telefone}
🛠️ {servico_nome}
📆 {data}
⏰ {hora}
"""

        # 🔥 THREAD ÚNICA (SEQUENCIAL DENTRO)
        threading.Thread(
            target=envio_cancelamento_background,
            args=(
                user_id,
                numero,
                mensagem_cliente,
                grupo_id,
                mensagem_grupo
            ),
            daemon=True
        ).start()

    except Exception as e:
        print("ERRO WHATS:", e)

    flash('Agendamento cancelado com sucesso!')
    return redirect(request.referrer or f"/agenda/{slug}")

def envio_cancelamento_background(user_id, numero, msg_cliente, grupo_id, msg_grupo):
    import time

    enviar_whatsapp(user_id, numero, msg_cliente)

    time.sleep(2)

    enviar_whatsapp(user_id, grupo_id, msg_grupo)

# =========================
# DISPONIBILIDADE / HORÁRIOS
# =========================
from datetime import datetime, date

@main.route('/horarios_disponiveis', methods=['POST'])
def horarios_disponiveis():
    data_str = request.json.get('data')
    usuario_id = request.json.get('usuario_id')
    profissional_id = request.json.get('profissional_id')

    if not data_str or not usuario_id:
        return jsonify([])

    data = datetime.strptime(
        data_str,
        '%Y-%m-%d'
    ).date()

    # bloqueio data passada
    if data < date.today():
        return jsonify([])

    dia_semana = data.weekday()

    usuario = db.session.get(Usuario, int(usuario_id))
    if not usuario:
        return jsonify([])
    garantir_agendas_profissionais(usuario)

    profissional = None
    if profissional_id:
        profissional = Profissional.query.filter_by(
            id=int(profissional_id),
            usuario_id=usuario.id,
            ativo=True
        ).first()
    if profissional is None:
        profissional = garantir_profissional_principal(usuario)

    config = garantir_configuracao_profissional(profissional)

    if not config:
        return jsonify([])

    dias_permitidos = carregar_json_campo(
        config.dias_semana,
        []
    )

    if dia_semana not in dias_permitidos:
        return jsonify([])

    horarios_cfg = carregar_json_campo(
        config.horarios_base,
        {}
    )

    # NOVO FORMATO
    if isinstance(horarios_cfg, dict):

        if dia_semana == 5:
            horarios = horarios_cfg.get(
                'sabado',
                []
            )
        else:
            horarios = horarios_cfg.get(
                'semana',
                []
            )

    else:
        # compatibilidade com registros antigos
        horarios = horarios_cfg

    excecao = ExcecaoProfissional.query.filter_by(
        profissional_id=profissional.id,
        data=data
    ).first()

    if excecao:

        if not excecao.dia_ativo:
            return jsonify([])

        bloqueados = (
            excecao.horarios_bloqueados
            or []
        )

        horarios = [
            h
            for h in horarios
            if h not in bloqueados
        ]

    return jsonify(horarios)



#====================================================================
def minutos_servico(servico):
    try:
        minutos = int(servico.duracao_minutos or 60)

        if minutos <= 0:
            return 60

        return minutos

    except Exception:
        return 60

import json

def carregar_json_campo(valor, padrao):
    if valor is None:
        return padrao

    if isinstance(valor, (list, dict)):
        return valor

    if isinstance(valor, str):
        try:
            return json.loads(valor)
        except Exception:
            return padrao

    return padrao


def horario_para_datetime(data, hora_str):
    hora_obj = datetime.strptime(hora_str, "%H:%M").time()
    return datetime.combine(data, hora_obj)

def calcular_limite_final(data, horarios_base):
    if not horarios_base:
        return None

    horarios_ordenados = sorted(
        horarios_base,
        key=lambda h: datetime.strptime(h, "%H:%M").time()
    )

    ultimo_horario_dt = horario_para_datetime(
        data,
        horarios_ordenados[-1]
    )

    return ultimo_horario_dt + timedelta(minutes=60)

def servico_cabe_no_expediente(data, horarios_base, inicio_novo, fim_novo):
    limite_final_dt = calcular_limite_final(data, horarios_base)

    if not limite_final_dt:
        return False

    return fim_novo <= limite_final_dt

def obter_horarios_base_usuario(usuario_id, data):
    config = ConfiguracaoAgenda.query.filter_by(
        usuario_id=usuario_id
    ).first()

    if not config:
        return []

    dia_semana = data.weekday()

    horarios_cfg = carregar_json_campo(
        config.horarios_base,
        {}
    )

    if isinstance(horarios_cfg, dict):

        if dia_semana == 5:
            return horarios_cfg.get('sabado', [])

        return horarios_cfg.get('semana', [])

    return horarios_cfg or []


def obter_horarios_base_profissional(profissional_id, data):
    profissional = db.session.get(Profissional, profissional_id)
    if not profissional:
        return []

    config = garantir_configuracao_profissional(profissional)
    dia_semana = data.weekday()
    dias_permitidos = carregar_json_campo(config.dias_semana, [])

    if dia_semana not in dias_permitidos:
        return []

    horarios_cfg = carregar_json_campo(config.horarios_base, {})
    if isinstance(horarios_cfg, dict):
        chave = 'sabado' if dia_semana == 5 else 'semana'
        return horarios_cfg.get(chave, [])

    return horarios_cfg or []

def existe_conflito_agendamento(
    usuario_id,
    data,
    inicio_novo,
    fim_novo,
    ignorar_agendamento_id=None,
    profissional_id=None
):
    query = Agendamento.query.filter_by(
        usuario_id=usuario_id,
        data=data
    )

    if profissional_id is not None:
        query = query.join(AgendamentoProfissional).filter(
            AgendamentoProfissional.profissional_id == profissional_id
        )

    if ignorar_agendamento_id:
        query = query.filter(Agendamento.id != ignorar_agendamento_id)

    agendamentos = query.all()

    for ag in agendamentos:
        if not ag.horario:
            continue

        inicio_existente = datetime.combine(data, ag.horario)

        duracao_existente = 60

        if ag.servico:
            duracao_existente = minutos_servico(ag.servico)

        fim_existente = inicio_existente + timedelta(minutes=duracao_existente)

        if inicio_novo < fim_existente and fim_novo > inicio_existente:
            return True

    return False

from datetime import datetime, date

#==================================================================================
@main.route('/verificar_horarios', methods=['POST'])
def verificar_horarios():
    try:
        data_json = request.get_json() or {}

        data_str = data_json.get('data')
        servico_id = data_json.get('servico_id')

        if not data_str or not servico_id:
            return jsonify([])

        data = datetime.strptime(data_str, '%Y-%m-%d').date()

        if data < date.today():
            return jsonify([])

        servico = Servico.query.get_or_404(int(servico_id))

        usuario_id = servico.usuario_id
        profissional = profissional_do_servico(servico)
        duracao_novo = minutos_servico(servico)

        dia_semana = data.weekday()

        config = garantir_configuracao_profissional(profissional)

        if not config:
            return jsonify([])

        dias_permitidos = carregar_json_campo(
            config.dias_semana,
            []
        )

        if dia_semana not in dias_permitidos:
            return jsonify([])

        horarios_cfg = carregar_json_campo(
            config.horarios_base,
            {}
        )

        if isinstance(horarios_cfg, dict):
            if dia_semana == 5:
                horarios_base = horarios_cfg.get('sabado', [])
            else:
                horarios_base = horarios_cfg.get('semana', [])
        else:
            horarios_base = horarios_cfg

        excecao = ExcecaoProfissional.query.filter_by(
            profissional_id=profissional.id,
            data=data
        ).first()

        if excecao:
            if not excecao.dia_ativo:
                return jsonify([])

            horarios_base = [
                h for h in horarios_base
                if h not in (excecao.horarios_bloqueados or [])
            ]

        if not horarios_base:
            return jsonify([])

        try:
            horarios_base = sorted(
                horarios_base,
                key=lambda h: datetime.strptime(h, "%H:%M").time()
            )
        except Exception:
            return jsonify([])

        ultimo_horario_dt = horario_para_datetime(
            data,
            horarios_base[-1]
        )

        limite_final_dt = ultimo_horario_dt + timedelta(minutes=60)

        agora = datetime.now()
        horarios_disponiveis = []

        for h in horarios_base:
            try:
                inicio_novo = horario_para_datetime(data, h)
            except Exception:
                continue

            fim_novo = inicio_novo + timedelta(minutes=duracao_novo)

            # Regra:
            # o último horário cadastrado ainda aceita serviços de até 60 minutos.
            # Exemplo: último horário 18:00 = limite final 19:00.
            if fim_novo > limite_final_dt:
                continue

            if inicio_novo <= agora:
                continue

            conflito = existe_conflito_agendamento(
                usuario_id=usuario_id,
                profissional_id=profissional.id,
                data=data,
                inicio_novo=inicio_novo,
                fim_novo=fim_novo
            )

            if conflito:
                continue

            horarios_disponiveis.append(h)

        return jsonify(horarios_disponiveis)

    except Exception as e:
        current_app.logger.exception("ERRO EM verificar_horarios")
        return jsonify({
            "erro": str(e),
            "tipo": type(e).__name__
        }), 500

@main.route('/relatorio')
@login_required
def relatorio():
    from datetime import date, timedelta
    from sqlalchemy import extract, func, or_

    user_id = session["user_id"]

    hoje = date.today()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    fim_semana = inicio_semana + timedelta(days=6)

    inicio_mes = hoje.replace(day=1)
    fim_7_dias = hoje + timedelta(days=7)
    ano_atual = hoje.year

    total_agendamentos = Agendamento.query.filter_by(
        usuario_id=user_id
    ).count()

    total_hoje = Agendamento.query.filter_by(
        usuario_id=user_id,
        data=hoje
    ).count()

    total_semana = Agendamento.query.filter(
        Agendamento.usuario_id == user_id,
        Agendamento.data >= inicio_semana,
        Agendamento.data <= fim_semana
    ).count()

    total_mes = Agendamento.query.filter(
        Agendamento.usuario_id == user_id,
        Agendamento.data >= inicio_mes
    ).count()

    proximos_7_dias = Agendamento.query.filter(
        Agendamento.usuario_id == user_id,
        Agendamento.data >= hoje,
        Agendamento.data <= fim_7_dias
    ).count()

    total_no_ano = Agendamento.query.filter(
        Agendamento.usuario_id == user_id,
        extract('year', Agendamento.data) == ano_atual
    ).count()

    total_cancelados = 0

    dados_por_mes = (
        db.session.query(
            extract('month', Agendamento.data).label('mes'),
            func.count(Agendamento.id).label('total')
        )
        .filter(
            Agendamento.usuario_id == user_id,
            extract('year', Agendamento.data) == ano_atual
        )
        .group_by('mes')
        .order_by(func.count(Agendamento.id).desc())
        .all()
    )

    meses_nomes = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]

    melhor_mes = None

    if dados_por_mes:
        melhor_mes = meses_nomes[int(dados_por_mes[0].mes) - 1]

    servicos_mais_vendidos = (
        db.session.query(
            Servico.titulo.label("titulo"),
            func.count(Agendamento.id).label("total")
        )
        .join(Servico, Servico.id == Agendamento.servico_id)
        .filter(Agendamento.usuario_id == user_id)
        .group_by(Servico.id, Servico.titulo)
        .order_by(func.count(Agendamento.id).desc())
        .limit(5)
        .all()
    )

    clientes_frequentes = (
        db.session.query(
            Agendamento.nome.label("nome"),
            Agendamento.telefone.label("telefone"),
            func.count(Agendamento.id).label("total")
        )
        .filter(Agendamento.usuario_id == user_id)
        .group_by(Agendamento.telefone, Agendamento.nome)
        .order_by(func.count(Agendamento.id).desc())
        .limit(5)
        .all()
    )

    desempenho_mensal = []

    for mes in range(1, 13):
        total_mes_item = Agendamento.query.filter(
            Agendamento.usuario_id == user_id,
            extract('year', Agendamento.data) == ano_atual,
            extract('month', Agendamento.data) == mes
        ).count()

        desempenho_mensal.append({
            "mes": meses_nomes[mes - 1][:3],
            "total": total_mes_item
        })

    maior_mes_total = max([m["total"] for m in desempenho_mensal] or [0])

    for item in desempenho_mensal:
        if maior_mes_total > 0:
            item["percentual"] = int((item["total"] / maior_mes_total) * 100)
        else:
            item["percentual"] = 0

    servico_mais_procurado = servicos_mais_vendidos[0].titulo if servicos_mais_vendidos else "Sem dados"
    cliente_do_mes = clientes_frequentes[0].nome if clientes_frequentes else "Sem dados"

    dia_pico_dado = (
        db.session.query(
            Agendamento.data.label("data"),
            func.count(Agendamento.id).label("total")
        )
        .filter(Agendamento.usuario_id == user_id)
        .group_by(Agendamento.data)
        .order_by(func.count(Agendamento.id).desc())
        .first()
    )

    dia_pico = dia_pico_dado.data.strftime('%d/%m/%Y') if dia_pico_dado else "Sem dados"

    return render_template(
        'relatorio.html',
        total_agendamentos=total_agendamentos,
        total_cancelados=total_cancelados,
        melhor_mes=melhor_mes,
        total_no_ano=total_no_ano,
        total_hoje=total_hoje,
        total_semana=total_semana,
        total_mes=total_mes,
        proximos_7_dias=proximos_7_dias,
        servicos_mais_vendidos=servicos_mais_vendidos,
        clientes_frequentes=clientes_frequentes,
        desempenho_mensal=desempenho_mensal,
        servico_mais_procurado=servico_mais_procurado,
        cliente_do_mes=cliente_do_mes,
        dia_pico=dia_pico
    )

@main.route("/lista")
@login_required
def lista():
    return render_template("lista.html")

@main.route("/suporte")
@login_required
def suporte():
    import os
    from urllib.parse import quote

    from .master_billing import calcular_status_assinatura, garantir_planos_padrao
    from .models import PagamentoAssinatura, PlanoSistema

    usuario = db.session.get(Usuario, session["user_id"])
    if not usuario:
        return redirect(url_for("auth.login"))

    if usuario.is_masteradm:
        return redirect(url_for("main.masteradm"))

    garantir_planos_padrao()

    assinatura = usuario.assinatura_cobranca
    status_financeiro = calcular_status_assinatura(assinatura)

    planos = (
        PlanoSistema.query
        .filter_by(ativo=True)
        .order_by(PlanoSistema.ordem, PlanoSistema.nome)
        .all()
    )

    solicitacao_pendente = (
        PagamentoAssinatura.query
        .filter(
            PagamentoAssinatura.usuario_id == usuario.id,
            PagamentoAssinatura.status == "pendente",
            PagamentoAssinatura.referencia_externa.like("troca-plano:%"),
        )
        .order_by(PagamentoAssinatura.criado_em.desc())
        .first()
    )

    plano_solicitado = None
    if solicitacao_pendente and solicitacao_pendente.referencia_externa:
        try:
            plano_id = int(solicitacao_pendente.referencia_externa.split(":")[1])
            plano_solicitado = db.session.get(PlanoSistema, plano_id)
        except (IndexError, TypeError, ValueError):
            plano_solicitado = None

    suporte_whatsapp = "".join(
        caractere
        for caractere in str(os.getenv("SUPPORT_WHATSAPP") or "")
        if caractere.isdigit()
    )
    suporte_email = str(os.getenv("SUPPORT_EMAIL") or "").strip()
    mensagem_suporte = quote(
        f"Olá, preciso de suporte no Agenda1. Usuário: {usuario.username}."
    )
    suporte_whatsapp_url = (
        f"https://wa.me/{suporte_whatsapp}?text={mensagem_suporte}"
        if suporte_whatsapp else None
    )

    return render_template(
        "suporte.html",
        usuario=usuario,
        assinatura=assinatura,
        status_financeiro=status_financeiro,
        planos=planos,
        solicitacao_pendente=solicitacao_pendente,
        plano_solicitado=plano_solicitado,
        suporte_whatsapp_url=suporte_whatsapp_url,
        suporte_email=suporte_email,
    )


@main.route("/suporte/solicitar-plano/<int:plano_id>", methods=["POST"])
@login_required
def solicitar_mudanca_plano(plano_id):
    from datetime import date
    from decimal import Decimal
    from uuid import uuid4

    from .models import AssinaturaUsuario, PagamentoAssinatura, PlanoSistema

    usuario = db.session.get(Usuario, session["user_id"])
    if not usuario or usuario.is_masteradm:
        return redirect(url_for("auth.login"))

    plano = PlanoSistema.query.filter_by(id=plano_id, ativo=True).first_or_404()
    assinatura = usuario.assinatura_cobranca

    if assinatura and assinatura.plano_id == plano.id:
        flash("Este já é o seu plano atual.")
        return redirect(url_for("main.suporte"))

    if not assinatura:
        assinatura = AssinaturaUsuario(
            usuario_id=usuario.id,
            status="ativa",
            valor_mensal=Decimal("0"),
            provedor="manual",
        )
        db.session.add(assinatura)
        db.session.flush()

    pendentes = (
        PagamentoAssinatura.query
        .filter(
            PagamentoAssinatura.usuario_id == usuario.id,
            PagamentoAssinatura.status == "pendente",
            PagamentoAssinatura.referencia_externa.like("troca-plano:%"),
        )
        .all()
    )
    for pendente in pendentes:
        pendente.status = "cancelado"
        pendente.observacao = (
            (pendente.observacao or "").strip()
            + " Solicitação substituída por uma escolha mais recente."
        ).strip()

    ciclo_meses = max(int(plano.ciclo_meses or 1), 1)
    valor_ciclo = Decimal(plano.valor_mensal or 0) * ciclo_meses

    solicitacao = PagamentoAssinatura(
        assinatura_id=assinatura.id,
        usuario_id=usuario.id,
        valor=valor_ciclo,
        vencimento=date.today(),
        status="pendente",
        forma_pagamento="aguardando_checkout",
        provedor="manual",
        referencia_externa=f"troca-plano:{plano.id}:{uuid4().hex}",
        observacao=(
            f"Solicitação de mudança para {plano.nome}. "
            "Aguardando confirmação do MASTER ADM ou geração de cobrança."
        ),
    )
    db.session.add(solicitacao)
    db.session.commit()

    flash(
        "Solicitação enviada. Seu plano atual permanece ativo até a confirmação "
        "do pagamento e da mudança."
    )
    return redirect(url_for("main.suporte"))

@main.route("/eventos")
@login_required
def eventos():
    return render_template("eventos.html")

# =========================
# CONSULTAS /
# =========================
@main.route('/consultar', methods=['GET', 'POST'])
def consultar():
    agendamentos = None
    telefone = None
    slug = None
    usuario = None

    if request.method == 'POST':
        telefone = request.form['telefone']
        agendamentos = Agendamento.query.filter_by(
            telefone=telefone
        ).order_by(
            Agendamento.data,
            Agendamento.horario
        ).all()

        if agendamentos:
            usuario = agendamentos[0].usuario
            garantir_agendas_profissionais(usuario)
            slug = usuario.slug

    return render_template(
        'consultar.html',
        agendamentos=agendamentos,
        telefone=telefone,
        slug=slug,
        usuario=usuario
    )


# =========================
# ROTAS PROTEGIDAS
# =========================
@main.route('/painel')
@login_required
def painel():
    from flask import session

    user_id = session["user_id"]

    # 🔥 atualiza status do WhatsApp
    atualizar_status(user_id)

    # 🔥 busca no banco
    whatsapp = WhatsappSession.query.filter_by(user_id=user_id).first()

    from .master_billing import obter_aviso_assinatura

    aviso_assinatura = obter_aviso_assinatura(user_id)

    return render_template(
        'painel.html',
        whatsapp=whatsapp,
        aviso_assinatura=aviso_assinatura
    )


@main.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    from datetime import datetime, date, timedelta

    user_id = session["user_id"]
    usuario = db.session.get(Usuario, user_id)
    garantir_agendas_profissionais(usuario)
    profissionais = Profissional.query.filter_by(
        usuario_id=user_id,
        ativo=True
    ).order_by(
        Profissional.principal.desc(),
        Profissional.nome
    ).all()
    profissional_id = request.args.get('profissional_id', type=int)
    if profissional_id and not any(p.id == profissional_id for p in profissionais):
        profissional_id = None

    hoje = date.today()
    amanha = hoje + timedelta(days=1)

    inicio_semana = hoje - timedelta(days=hoje.weekday())
    fim_semana = inicio_semana + timedelta(days=6)

    inicio_mes = hoje.replace(day=1)

    data_filtro = request.args.get("data") or request.form.get("data")
    periodo = request.args.get("periodo", "hoje")

    # ==========================================
    # FILTRO POR DATA ESPECÍFICA
    # ==========================================
    if data_filtro:

        try:

            data_obj = datetime.strptime(
                data_filtro,
                "%Y-%m-%d"
            ).date()

            agendamentos = (
                Agendamento.query
                .filter_by(
                    usuario_id=user_id,
                    data=data_obj
                )
                .order_by(
                    Agendamento.horario
                )
                .all()
            )

        except:

            agendamentos = []

    # ==========================================
    # FILTROS POR PERÍODO
    # ==========================================
    else:

        if periodo == "hoje":

            agendamentos = (
                Agendamento.query
                .filter_by(
                    usuario_id=user_id,
                    data=hoje
                )
                .order_by(
                    Agendamento.horario
                )
                .all()
            )

        elif periodo == "amanha":

            agendamentos = (
                Agendamento.query
                .filter_by(
                    usuario_id=user_id,
                    data=amanha
                )
                .order_by(
                    Agendamento.horario
                )
                .all()
            )

        elif periodo == "semana":

            agendamentos = (
                Agendamento.query
                .filter(
                    Agendamento.usuario_id == user_id,
                    Agendamento.data >= inicio_semana,
                    Agendamento.data <= fim_semana
                )
                .order_by(
                    Agendamento.data,
                    Agendamento.horario
                )
                .all()
            )

        elif periodo == "mes":

            agendamentos = (
                Agendamento.query
                .filter(
                    Agendamento.usuario_id == user_id,
                    Agendamento.data >= inicio_mes
                )
                .order_by(
                    Agendamento.data,
                    Agendamento.horario
                )
                .all()
            )

        elif periodo == "todos":

            agendamentos = (
                Agendamento.query
                .filter_by(
                    usuario_id=user_id
                )
                .order_by(
                    Agendamento.data,
                    Agendamento.horario
                )
                .all()
            )

        else:

            periodo = "hoje"

            agendamentos = (
                Agendamento.query
                .filter_by(
                    usuario_id=user_id,
                    data=hoje
                )
                .order_by(
                    Agendamento.horario
                )
                .all()
            )

    if profissional_id:
        agendamentos = [
            agendamento for agendamento in agendamentos
            if agendamento.vinculo_profissional
            and agendamento.vinculo_profissional.profissional_id == profissional_id
        ]

    # ==========================================
    # CARDS SUPERIORES
    # ==========================================

    def contar_agendamentos_profissional(*filtros):
        query = Agendamento.query.filter(*filtros)
        if profissional_id:
            query = query.join(AgendamentoProfissional).filter(
                AgendamentoProfissional.profissional_id == profissional_id
            )
        return query.count()

    total_hoje = contar_agendamentos_profissional(
        Agendamento.usuario_id == user_id,
        Agendamento.data == hoje
    )

    total_amanha = contar_agendamentos_profissional(
        Agendamento.usuario_id == user_id,
        Agendamento.data == amanha
    )

    total_semana = contar_agendamentos_profissional(
        Agendamento.usuario_id == user_id,
        Agendamento.data >= inicio_semana,
        Agendamento.data <= fim_semana
    )

    # ==========================================
    # PRÓXIMO AGENDAMENTO
    # ==========================================

    proximo_query = (
        Agendamento.query
        .filter(
            Agendamento.usuario_id == user_id,
            Agendamento.data >= hoje
        )
    )
    if profissional_id:
        proximo_query = proximo_query.join(AgendamentoProfissional).filter(
            AgendamentoProfissional.profissional_id == profissional_id
        )

    proximo_agendamento = (
        proximo_query.order_by(
            Agendamento.data,
            Agendamento.horario
        )
        .first()
    )

    return render_template(

        "admin.html",

        agendamentos=agendamentos,

        data_filtro=data_filtro,
        periodo=periodo,
        profissionais=profissionais,
        profissional_id=profissional_id,

        total_hoje=total_hoje,
        total_amanha=total_amanha,
        total_semana=total_semana,

        proximo_agendamento=proximo_agendamento

    )


@main.route('/servicos', methods=['GET', 'POST'])
@login_required
def servicos():
    user_id = session["user_id"]
    usuario = db.session.get(Usuario, user_id)
    principal = garantir_profissional_principal(usuario)
    garantir_servicos_profissional_principal(usuario, principal)

    profissionais_ativos = Profissional.query.filter_by(
        usuario_id=user_id,
        ativo=True
    ).order_by(
        Profissional.principal.desc(),
        Profissional.nome
    ).all()

    if request.method == 'POST':
        profissional_id = request.form.get('profissional_id', type=int)
        profissional = Profissional.query.filter_by(
            id=profissional_id,
            usuario_id=user_id,
            ativo=True
        ).first()

        if not profissional:
            flash('Selecione um profissional válido para o serviço.')
            return redirect(url_for('main.servicos'))

        novo_servico = Servico(
            usuario_id=user_id,
            titulo=request.form['titulo'],
            preco=request.form.get('valor'),
            duracao_minutos=int(request.form.get('tempo') or 60),
            cor=request.form.get('cor', '#2563eb'),
            ativo=True
        )
        db.session.add(novo_servico)
        db.session.flush()
        db.session.add(ProfissionalServico(
            profissional_id=profissional.id,
            servico_id=novo_servico.id
        ))
        db.session.commit()
        return redirect(url_for('main.servicos'))

    servicos = Servico.query.filter_by(
        usuario_id=user_id
    ).all()

    return render_template(
        'servicos.html',
        servicos=servicos,
        profissionais=profissionais_ativos
    )


@main.route('/profissionais', methods=['GET', 'POST'])
@login_required
def profissionais():
    usuario = db.session.get(Usuario, session['user_id'])
    garantir_profissional_principal(usuario)

    if request.method == 'POST':
        nome = str(request.form.get('nome') or '').strip()
        especialidade = str(request.form.get('especialidade') or '').strip()
        foto_url = str(request.form.get('foto_url') or '').strip()

        if len(nome) < 2:
            flash('Informe o nome do profissional.')
            return redirect(url_for('main.profissionais'))

        slug_base = slug_profissional(nome)
        slug = slug_base
        contador = 2

        while Profissional.query.filter_by(
            usuario_id=usuario.id,
            slug=slug
        ).first():
            slug = f'{slug_base}-{contador}'
            contador += 1

        profissional = Profissional(
            usuario_id=usuario.id,
            nome=nome,
            slug=slug,
            especialidade=especialidade or None,
            foto_url=foto_url or None,
            ativo=True,
            principal=False
        )
        db.session.add(profissional)
        db.session.commit()
        flash('Profissional cadastrado com sucesso.')
        return redirect(url_for('main.profissionais'))

    lista = Profissional.query.filter_by(
        usuario_id=usuario.id
    ).order_by(
        Profissional.principal.desc(),
        Profissional.nome
    ).all()

    return render_template(
        'profissionais.html',
        profissionais=lista,
        usuario=usuario
    )


@main.route('/profissionais/<int:profissional_id>/alternar', methods=['POST'])
@login_required
def alternar_profissional(profissional_id):
    profissional = Profissional.query.filter_by(
        id=profissional_id,
        usuario_id=session['user_id']
    ).first_or_404()

    if profissional.principal and profissional.ativo:
        flash('O profissional principal deve permanecer ativo.')
        return redirect(url_for('main.profissionais'))

    if profissional.ativo and profissional.servicos_vinculados:
        flash('Mova os serviços deste profissional antes de desativá-lo.')
        return redirect(url_for('main.profissionais'))

    profissional.ativo = not profissional.ativo
    db.session.commit()
    flash('Status do profissional atualizado.')
    return redirect(url_for('main.profissionais'))


@main.route('/editar_servico/<int:id>', methods=['POST'])
@login_required
def editar_servico(id):
    data = request.get_json()

    servico = Servico.query.filter_by(
        id=id,
        usuario_id=session["user_id"]
    ).first_or_404()

    servico.titulo = data.get('titulo')
    servico.preco = data.get('valor')
    servico.duracao_minutos = int(data.get('tempo') or 60)
    servico.cor = data.get('cor', servico.cor)

    profissional_id = data.get('profissional_id')
    try:
        profissional_id = int(profissional_id)
    except (TypeError, ValueError):
        return jsonify({'erro': 'Profissional inválido.'}), 400

    profissional = Profissional.query.filter_by(
        id=profissional_id,
        usuario_id=session['user_id'],
        ativo=True
    ).first()

    if not profissional:
        return jsonify({'erro': 'Profissional inválido.'}), 400

    if servico.vinculo_profissional:
        servico.vinculo_profissional.profissional_id = profissional.id
    else:
        db.session.add(ProfissionalServico(
            profissional_id=profissional.id,
            servico_id=servico.id
        ))

    db.session.commit()
    return jsonify({'mensagem': 'Serviço atualizado com sucesso!'})


# =========================
# ROTAS PÚBLICAS POR SLUG
# =========================
@main.route("/service")
@login_required
def service():
    usuario = Usuario.query.get_or_404(session["user_id"])
    return redirect(url_for("main.agenda_publica_slug", slug=usuario.slug))


@main.route("/agenda/<slug>")
def agenda_publica_slug(slug):
    usuario = Usuario.query.filter_by(slug=slug).first_or_404()

    principal = garantir_profissional_principal(usuario)
    garantir_servicos_profissional_principal(usuario, principal)
    profissionais_ativos = Profissional.query.filter_by(
        usuario_id=usuario.id,
        ativo=True
    ).order_by(
        Profissional.principal.desc(),
        Profissional.nome
    ).all()

    if len(profissionais_ativos) > 1:
        return render_template(
            'profissionais_publico.html',
            usuario=usuario,
            profissionais=profissionais_ativos
        )

    profissional = profissionais_ativos[0] if profissionais_ativos else principal
    servicos = (
        Servico.query
        .join(ProfissionalServico)
        .filter(
            Servico.usuario_id == usuario.id,
            ProfissionalServico.profissional_id == profissional.id
        )
        .order_by(Servico.titulo)
        .all()
    )

    return render_template(
        "service.html",
        servicos=servicos,
        usuario=usuario,
        profissional=profissional
    )


@main.route('/agenda/<slug>/profissional/<profissional_slug>')
def agenda_profissional_publica(slug, profissional_slug):
    usuario = Usuario.query.filter_by(slug=slug).first_or_404()
    garantir_servicos_profissional_principal(usuario)
    profissional = Profissional.query.filter_by(
        usuario_id=usuario.id,
        slug=profissional_slug,
        ativo=True
    ).first_or_404()

    servicos = (
        Servico.query
        .join(ProfissionalServico)
        .filter(
            Servico.usuario_id == usuario.id,
            ProfissionalServico.profissional_id == profissional.id
        )
        .order_by(Servico.titulo)
        .all()
    )

    return render_template(
        'service.html',
        servicos=servicos,
        usuario=usuario,
        profissional=profissional,
        possui_selecao_profissional=True
    )


@main.route('/agenda/<slug>/consultar', methods=['GET', 'POST'])
def consultar_publico(slug):
    usuario = Usuario.query.filter_by(slug=slug).first_or_404()
    garantir_agendas_profissionais(usuario)

    agendamentos = None
    telefone = None

    if request.method == 'POST':
        telefone = request.form['telefone']
        agendamentos = Agendamento.query.filter_by(
            telefone=telefone,
            usuario_id=usuario.id
        ).order_by(
            Agendamento.data,
            Agendamento.horario
        ).all()

    return render_template(
        'consultar.html',
        agendamentos=agendamentos,
        telefone=telefone,
        slug=slug,
        usuario=usuario
    )


@main.route('/salvar_configuracao_agenda', methods=['POST'])
@login_required
def salvar_configuracao_agenda():
    user_id = session['user_id']
    data = request.get_json()

    dias_semana = data.get('dias_semana')           # [0,1,2,3,4]
    horarios_base = data.get('horarios_base')       # ['08:00','09:00']
    excecoes = data.get('excecoes', [])              # opcional

    if not dias_semana or not horarios_base:
        return jsonify({'erro': 'Dados incompletos'}), 400

    # -----------------------------
    # CONFIGURAÇÃO BASE (UPSERT)
    # -----------------------------
    config = ConfiguracaoAgenda.query.filter_by(
        usuario_id=user_id
    ).first()

    dias_str = ','.join(str(d) for d in dias_semana)
    horarios_str = ','.join(horarios_base)

    if config:
        config.dias_semana = dias_str
        config.horarios_base = horarios_str
    else:
        config = ConfiguracaoAgenda(
            usuario_id=user_id,
            dias_semana=dias_str,
            horarios_base=horarios_str
        )
        db.session.add(config)

    # -----------------------------
    # EXCEÇÕES POR DATA
    # -----------------------------
    for ex in excecoes:
        data_ex = datetime.strptime(ex['data'], '%Y-%m-%d').date()
        dia_ativo = ex.get('dia_ativo', True)
        horarios_desativados = ex.get('horarios', [])

        excecao = ExcecaoAgenda.query.filter_by(
            usuario_id=user_id,
            data=data_ex
        ).first()

        horarios_str = ','.join(horarios_desativados) if horarios_desativados else None

        if excecao:
            excecao.dia_ativo = dia_ativo
            excecao.horarios_desativados = horarios_str
        else:
            nova = ExcecaoAgenda(
                usuario_id=user_id,
                data=data_ex,
                dia_ativo=dia_ativo,
                horarios_desativados=horarios_str
            )
            db.session.add(nova)

    db.session.commit()

    return jsonify({'status': 'ok'})

@main.route('/configuracoes')
@login_required
def configuracoes():
    usuario = db.session.get(Usuario, session['user_id'])
    garantir_agendas_profissionais(usuario)
    profissionais = Profissional.query.filter_by(
        usuario_id=usuario.id,
        ativo=True
    ).order_by(
        Profissional.principal.desc(),
        Profissional.nome
    ).all()
    tema_atual = normalizar_tema(usuario.tema)
    fonte_atual = normalizar_fonte_titulo(usuario.fonte_titulo)

    return render_template(
        'setup.html',
        profissionais=profissionais,
        usuario=usuario,
        tema_atual=tema_atual,
        fonte_atual=fonte_atual,
    )

@main.route('/configuracao_base', methods=['GET'])
@login_required
def configuracao_base():
    profissional_id = request.args.get('profissional_id', type=int)
    profissional = Profissional.query.filter_by(
        id=profissional_id,
        usuario_id=session['user_id'],
        ativo=True
    ).first()

    if not profissional:
        return jsonify({'erro': 'Profissional inválido.'}), 400

    config = garantir_configuracao_profissional(profissional)

    if not config:
        return jsonify({
            'dias_semana': [0, 1, 2, 3, 4, 5],
            'horarios_base': {
                'semana': [],
                'sabado': []
            }
        })

    return jsonify({
        'dias_semana': config.dias_semana or [],
        'horarios_base': config.horarios_base or {
            'semana': [],
            'sabado': []
        }
    })

@main.route('/salvar_configuracao_base', methods=['POST'])
@login_required
def salvar_configuracao_base():
    data = request.get_json() or {}
    profissional = Profissional.query.filter_by(
        id=data.get('profissional_id'),
        usuario_id=session['user_id'],
        ativo=True
    ).first()

    if not profissional:
        return jsonify({'erro': 'Profissional inválido.'}), 400

    config = garantir_configuracao_profissional(profissional)

    dias_semana = data.get('dias_semana', [])

    horarios_base = data.get(
        'horarios_base',
        {
            'semana': [],
            'sabado': []
        }
    )

    config.dias_semana = dias_semana
    config.horarios_base = horarios_base

    db.session.commit()

    return jsonify({
        'status': 'ok'
    })

@main.route('/salvar_excecao_agenda', methods=['POST'])
@login_required
def salvar_excecao_agenda():
    data = request.get_json() or {}

    profissional = Profissional.query.filter_by(
        id=data.get('profissional_id'),
        usuario_id=session['user_id'],
        ativo=True
    ).first()

    if not profissional:
        return jsonify({'erro': 'Profissional inválido.'}), 400

    data_obj = datetime.strptime(data['data'], '%Y-%m-%d').date()

    excecao = ExcecaoProfissional.query.filter_by(
        profissional_id=profissional.id,
        data=data_obj
    ).first()

    if not excecao:
        excecao = ExcecaoProfissional(
            profissional_id=profissional.id,
            data=data_obj
        )
        db.session.add(excecao)

    excecao.dia_ativo = data.get('dia_ativo', True)
    excecao.horarios_bloqueados = data.get('horarios_bloqueados', [])

    db.session.commit()

    # 🔥 LOG AQUI (após salvar)
    current_app.logger.info(
        f"ExcecaoProfissional | profissional_id={profissional.id} | data={data_obj} | ativo={excecao.dia_ativo} | bloqueados={excecao.horarios_bloqueados}"
    )

    return jsonify({'status':'ok'})

@main.route('/salvar_identidade', methods=['POST'])
@login_required
def salvar_identidade():
    data = request.get_json(silent=True) or {}

    usuario = db.session.get(Usuario, session['user_id'])
    if not usuario:
        return jsonify({'status': 'erro', 'mensagem': 'Usuário não encontrado.'}), 404

    if 'nome_fantasia' in data:
        usuario.nome_fantasia = str(data.get('nome_fantasia') or '').strip() or None

    if 'fonte_titulo' in data:
        usuario.fonte_titulo = normalizar_fonte_titulo(
            data.get('fonte_titulo')
        )

    if 'tema' in data:
        tema_recebido = str(data.get('tema') or '').strip().lower()
        if tema_recebido not in TEMAS_VALIDOS:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Paleta de cores inválida.'
            }), 400

        usuario.tema = tema_recebido
        session['tema'] = tema_recebido

    usuario.tema = normalizar_tema(usuario.tema)
    session['tema'] = usuario.tema
    db.session.commit()

    tema_atual = normalizar_tema(usuario.tema)
    return jsonify({
        'status': 'ok',
        'tema': tema_atual
    })

@main.route('/masteradm')
@master_required
def masteradm():
    return redirect(url_for('master_financeiro.dashboard'))

@main.route('/usuarios')
@master_required
def usuarios():
    return redirect(url_for('master_financeiro.usuarios'))

@main.route('/logs')
@master_required
def logs():
    with open('app.log', 'r') as f:
        conteudo = f.readlines()

    return render_template('logs.html', logs=conteudo[::-1])

@main.route('/logs_json')
def logs_json():
    try:
        with open('app.log', 'r') as f:
            conteudo = f.readlines()
    except:
        conteudo = []

    return {"logs": conteudo[-50:]}  # últimos 50

@main.route("/whatsapp")
@login_required
def whatsapp():
    from flask import session, redirect, render_template

    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    # 🔥 session única por usuário
    session_id = f"user_{user_id}"

    return render_template("conectar.html", session_id=session_id)


import requests
from app.models import WhatsappSession


def atualizar_status(user_id):
    import requests

    session_id = f"user_{user_id}"

    try:
        res = requests.get(
            f"http://localhost:3000/status/{session_id}",
            timeout=10  # 🔥 aumentei
        )

        if res.status_code == 200:
            status = res.json().get("status", "none")
        else:
            status = "offline"

    except Exception as e:
        print("Erro ao consultar Node:", e)
        status = "offline"

    print("STATUS ATUAL DO NODE:", status)  # 🔥 debug importante

    session_db = WhatsappSession.query.filter_by(user_id=user_id).first()

    if not session_db:
        session_db = WhatsappSession(
            user_id=user_id,
            session_id=session_id,
            status=status
        )
        db.session.add(session_db)
    else:
        session_db.status = status

    db.session.commit()

    return status  # 🔥 AGORA RETORNA

def enviar_whatsapp(user_id, numero, mensagem):
    import requests
    import time

    session_id = f"user_{user_id}"
    url_status = f"http://localhost:3000/status/{session_id}"
    url_send = "http://localhost:3000/send"

    numero = str(numero)
    if not numero.startswith("55") and "@g.us" not in numero:
        numero = "55" + numero

    print("SESSION_ID:", session_id)
    print("ENVIANDO PARA:", numero)

    # 🔁 tenta até 3 vezes
    for tentativa in range(3):
        print(f"TENTATIVA {tentativa+1}")

        # 🔥 espera ficar ready
        status_ok = False
        for i in range(10):
            try:
                status = requests.get(url_status, timeout=5).json()
                print("STATUS ATUAL:", status)

                if status.get("status") == "ready":
                    status_ok = True
                    break

            except Exception as e:
                print("Erro ao consultar status:", e)

            time.sleep(0.5)

        if not status_ok:
            print("Ainda não pronto, tentando novamente...")
            time.sleep(2)
            continue

        # 🔥 pequeno delay anti flood
        time.sleep(1)

        try:
            res = requests.post(
                url_send,
                json={
                    "sessionId": session_id,
                    "number": numero,
                    "message": mensagem
                },
                timeout=7
            )

            print("RESPOSTA NODE:", res.text)
            return True

        except requests.exceptions.ReadTimeout:
            print("Timeout (normal)")
            return True

        except Exception as e:
            print("Erro ao enviar, tentando novamente:", e)
            time.sleep(2)

    print("❌ Falha após várias tentativas")
    return False
from flask import current_app

def enviar_whatsapp_thread(app, user_id, numero, mensagem):
    with app.app_context():
        enviar_whatsapp(user_id, numero, mensagem)

def envio_whatsapp_background(user_id, numero, mensagem_cliente, grupo_id, mensagem_grupo):
    import time

    enviar_whatsapp(user_id, numero, mensagem_cliente)

    time.sleep(2)

    enviar_whatsapp(user_id, grupo_id, mensagem_grupo)


import requests

@main.route('/api/status/<session>')
def api_status(session):
    return requests.get(f"http://localhost:3000/status/{session}").json()


@main.route('/api/qr/<session>')
def api_qr(session):
    return requests.get(f"http://localhost:3000/qr/{session}").json()


@main.route('/api/session/<session>')
def api_session(session):
    return requests.get(f"http://localhost:3000/session/{session}").json()


@main.route('/api/logout/<session>')
def api_logout(session):
    return requests.get(f"http://localhost:3000/logout/{session}").json()

@main.route('/disponibilidade')
@login_required
def disponibilidade():
    usuario = db.session.get(Usuario, session['user_id'])
    garantir_agendas_profissionais(usuario)
    profissionais = Profissional.query.filter_by(
        usuario_id=usuario.id,
        ativo=True
    ).order_by(
        Profissional.principal.desc(),
        Profissional.nome
    ).all()
    return render_template(
        'disponibilidade.html',
        profissionais=profissionais
    )

@main.route('/carregar_disponibilidade', methods=['POST'])
@login_required
def carregar_disponibilidade():

    data_str = request.json.get('data')
    profissional_id = request.json.get('profissional_id')

    if not data_str:
        return jsonify({
            'horarios': [],
            'bloqueados': []
        })

    data = datetime.strptime(
        data_str,
        '%Y-%m-%d'
    ).date()

    profissional = Profissional.query.filter_by(
        id=profissional_id,
        usuario_id=session['user_id'],
        ativo=True
    ).first()

    if not profissional:
        return jsonify({'erro': 'Profissional inválido.'}), 400

    config = garantir_configuracao_profissional(profissional)

    if not config:
        return jsonify({
            'horarios': [],
            'bloqueados': []
        })

    dia_semana = data.weekday()

    horarios_cfg = config.horarios_base or {}

    if isinstance(horarios_cfg, dict):

        if dia_semana == 5:
            horarios = horarios_cfg.get(
                'sabado',
                []
            )
        else:
            horarios = horarios_cfg.get(
                'semana',
                []
            )

    else:
        horarios = horarios_cfg

    excecao = ExcecaoProfissional.query.filter_by(
        profissional_id=profissional.id,
        data=data
    ).first()

    bloqueados = []
    dia_ativo = True

    if excecao:
        bloqueados = (
            excecao.horarios_bloqueados
            or []
        )
        dia_ativo = excecao.dia_ativo

    return jsonify({
        'horarios': horarios,
        'bloqueados': bloqueados,
        'dia_ativo': dia_ativo,
    })

@main.route('/salvar_disponibilidade', methods=['POST'])
@login_required
def salvar_disponibilidade():

    data_str = request.json.get('data')
    profissional_id = request.json.get('profissional_id')
    bloqueados = request.json.get(
        'horarios_bloqueados',
        []
    )

    if not data_str:
        return jsonify({
            'status': 'erro'
        }), 400

    data = datetime.strptime(
        data_str,
        '%Y-%m-%d'
    ).date()

    profissional = Profissional.query.filter_by(
        id=profissional_id,
        usuario_id=session['user_id'],
        ativo=True
    ).first()

    if not profissional:
        return jsonify({'status': 'erro', 'mensagem': 'Profissional inválido.'}), 400

    excecao = ExcecaoProfissional.query.filter_by(
        profissional_id=profissional.id,
        data=data
    ).first()

    if not excecao:

        excecao = ExcecaoProfissional(
            profissional_id=profissional.id,
            data=data,
            dia_ativo=True
        )

        db.session.add(excecao)

    excecao.horarios_bloqueados = bloqueados

    db.session.commit()

    return jsonify({
        'status': 'ok'
    })

# =========================
# API CRM / CLIENTES
# =========================
@main.route('/api/crm/dados')
@login_required
def api_crm_dados():
    user_id = session['user_id']

    filtro = request.args.get('filtro', 'todos')
    semana = request.args.get('semana')
    mes = request.args.get('mes')

    agora = datetime.now()
    hoje = agora.date()
    limite_inativo = hoje - timedelta(days=60)

    # =========================
    # PERÍODO DA SEMANA
    # =========================
    if semana:
        try:
            ano_str, semana_str = semana.split('-W')
            inicio_semana = datetime.strptime(
                f'{ano_str}-W{semana_str}-1',
                '%G-W%V-%u'
            ).date()
            fim_semana = inicio_semana + timedelta(days=6)
        except Exception:
            inicio_semana = hoje - timedelta(days=hoje.weekday())
            fim_semana = inicio_semana + timedelta(days=6)
    else:
        inicio_semana = hoje - timedelta(days=hoje.weekday())
        fim_semana = inicio_semana + timedelta(days=6)

    # =========================
    # PERÍODO DO MÊS
    # =========================
    ano_mes = hoje.year
    mes_num = hoje.month

    if mes:
        try:
            ano_mes, mes_num = map(int, mes.split('-'))
        except Exception:
            ano_mes = hoje.year
            mes_num = hoje.month

    # =========================
    # CONTADORES GERAIS
    # =========================
    total_agendamentos = Agendamento.query.filter_by(
        usuario_id=user_id
    ).count()

    agendamentos_semana = Agendamento.query.filter(
        Agendamento.usuario_id == user_id,
        Agendamento.data >= inicio_semana,
        Agendamento.data <= fim_semana
    ).count()

    agendamentos_mes = Agendamento.query.filter(
        Agendamento.usuario_id == user_id,
        extract('year', Agendamento.data) == ano_mes,
        extract('month', Agendamento.data) == mes_num
    ).count()

    # Carrega clientes e agendamentos uma única vez. A associação por telefone
    # mantém compatibilidade com agendamentos antigos sem cliente_id.
    clientes_ativos = Cliente.query.filter_by(
        usuario_id=user_id,
        ativo_crm=True
    ).all()

    clientes_por_id = {cliente.id: cliente for cliente in clientes_ativos}
    clientes_por_telefone = {
        ''.join(filter(str.isdigit, cliente.telefone or '')): cliente
        for cliente in clientes_ativos
    }

    resumo_por_cliente = {
        cliente.id: {
            'realizados': [],
            'futuros': [],
            'todos': []
        }
        for cliente in clientes_ativos
    }

    agendamentos_usuario = Agendamento.query.filter_by(
        usuario_id=user_id
    ).all()

    for agendamento in agendamentos_usuario:
        cliente = clientes_por_id.get(agendamento.cliente_id)

        if not cliente:
            telefone = ''.join(filter(str.isdigit, agendamento.telefone or ''))
            cliente = clientes_por_telefone.get(telefone)

        if not cliente:
            continue

        agendamento_dt = datetime.combine(
            agendamento.data,
            agendamento.horario
        )

        resumo = resumo_por_cliente[cliente.id]
        resumo['todos'].append((agendamento_dt, agendamento))

        if agendamento_dt <= agora:
            resumo['realizados'].append((agendamento_dt, agendamento))
        else:
            resumo['futuros'].append((agendamento_dt, agendamento))

    clientes_lista = []
    total_inativos = 0

    for cliente in clientes_ativos:
        resumo = resumo_por_cliente[cliente.id]
        realizados = sorted(resumo['realizados'], key=lambda item: item[0])
        futuros = sorted(resumo['futuros'], key=lambda item: item[0])

        ultima_visita_dt = realizados[-1][0] if realizados else None
        proximo_dt = futuros[0][0] if futuros else None

        if ultima_visita_dt:
            status = (
                'inativo'
                if ultima_visita_dt.date() < limite_inativo
                else 'ativo'
            )
        elif proximo_dt:
            status = 'ativo'
        else:
            status = 'inativo'

        if status == 'inativo':
            total_inativos += 1

        if filtro == 'ativos' and status != 'ativo':
            continue

        if filtro == 'inativos' and status != 'inativo':
            continue

        if filtro == 'recorrentes' and cliente.recorrente != 'sim':
            continue

        clientes_lista.append({
            'id': cliente.id,
            'nome': cliente.nome,
            'telefone': cliente.telefone,
            'recorrente': cliente.recorrente or 'nao',
            'visitas': len(realizados),
            'total_agendamentos': len(resumo['todos']),
            'ultima_visita': (
                ultima_visita_dt.strftime('%Y-%m-%d')
                if ultima_visita_dt else None
            ),
            'ultimo_horario': (
                ultima_visita_dt.strftime('%H:%M')
                if ultima_visita_dt else None
            ),
            'proximo_agendamento': (
                proximo_dt.strftime('%Y-%m-%d')
                if proximo_dt else None
            ),
            'proximo_horario': (
                proximo_dt.strftime('%H:%M')
                if proximo_dt else None
            ),
            'status': status,
            '_ordenacao': ultima_visita_dt or proximo_dt or datetime.min
        })

    clientes_lista.sort(
        key=lambda cliente: cliente['_ordenacao'],
        reverse=True
    )

    for cliente in clientes_lista:
        cliente.pop('_ordenacao', None)

    return jsonify({
        'success': True,
        'total_agendamentos': total_agendamentos,
        'agendamentos_semana': agendamentos_semana,
        'agendamentos_mes': agendamentos_mes,
        'total_inativos': total_inativos,
        'clientes': clientes_lista
    })


@main.route('/api/crm/editar/<int:id>', methods=['POST'])
@login_required
def api_crm_editar(id):
    user_id = session['user_id']
    data_json = request.get_json() or {}

    cliente = Cliente.query.filter_by(
        id=id,
        usuario_id=user_id,
        ativo_crm=True
    ).first_or_404()

    nome = (data_json.get('nome') or '').strip()
    telefone = ''.join(filter(str.isdigit, data_json.get('telefone') or ''))
    recorrente = data_json.get('recorrente') or 'nao'

    if not nome:
        return jsonify({
            'success': False,
            'erro': 'Nome é obrigatório.'
        }), 400

    if len(telefone) < 10 or len(telefone) > 11:
        return jsonify({
            'success': False,
            'erro': 'Telefone inválido. Use DDD + número.'
        }), 400

    if recorrente not in ['sim', 'nao']:
        recorrente = 'nao'

    cliente.nome = nome
    cliente.telefone = telefone
    cliente.recorrente = recorrente

    # Mantém os agendamentos vinculados sincronizados visualmente
    Agendamento.query.filter_by(
        usuario_id=user_id,
        cliente_id=cliente.id
    ).update({
        'nome': nome,
        'telefone': telefone
    })

    db.session.commit()

    return jsonify({
        'success': True,
        'mensagem': 'Cliente atualizado com sucesso.'
    })


@main.route('/api/crm/excluir/<int:id>', methods=['DELETE'])
@login_required
def api_crm_excluir(id):
    user_id = session['user_id']

    cliente = Cliente.query.filter_by(
        id=id,
        usuario_id=user_id,
        ativo_crm=True
    ).first_or_404()

    # Não apaga histórico de agendamentos.
    # Apenas remove/inativa o cliente do CRM.
    cliente.ativo_crm = False

    db.session.commit()

    return jsonify({
        'success': True,
        'mensagem': 'Cliente removido do CRM.'
    })

@main.route('/api/crm/historico/<int:id>')
@login_required
def api_crm_historico(id):
    user_id = session['user_id']

    cliente = Cliente.query.filter_by(
        id=id,
        usuario_id=user_id,
        ativo_crm=True
    ).first_or_404()

    agora = datetime.now()
    hoje = agora.date()

    # O telefone entra como compatibilidade para registros antigos que ainda
    # não possuam cliente_id preenchido. Nenhum dado é alterado no banco.
    agendamentos = (
        Agendamento.query
        .filter(
            Agendamento.usuario_id == user_id,
            or_(
                Agendamento.cliente_id == cliente.id,
                Agendamento.telefone == cliente.telefone
            )
        )
        .order_by(
            Agendamento.data.asc(),
            Agendamento.horario.asc()
        )
        .all()
    )

    dias_semana = [
        'Segunda-feira',
        'Terça-feira',
        'Quarta-feira',
        'Quinta-feira',
        'Sexta-feira',
        'Sábado',
        'Domingo'
    ]

    meses_nomes = [
        'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
        'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
    ]

    detalhes = []
    historicos = []
    futuros = []
    contagem_dias = Counter()
    contagem_horarios = Counter()
    contagem_semanas = Counter()
    contagem_servicos = Counter()
    contagem_meses = Counter()
    valor_total = 0.0

    for agendamento in agendamentos:
        agendamento_dt = datetime.combine(
            agendamento.data,
            agendamento.horario
        )

        semana_mes = ((agendamento.data.day - 1) // 7) + 1
        dia_semana = dias_semana[agendamento.data.weekday()]
        horario = agendamento.horario.strftime('%H:%M')

        servico_nome = (
            agendamento.servico.titulo
            if agendamento.servico else 'Serviço não informado'
        )
        duracao = (
            minutos_servico(agendamento.servico)
            if agendamento.servico else None
        )
        preco = (
            float(agendamento.servico.preco)
            if agendamento.servico and agendamento.servico.preco is not None
            else None
        )
        profissional = (
            agendamento.vinculo_profissional.profissional.nome
            if agendamento.vinculo_profissional
            and agendamento.vinculo_profissional.profissional
            else None
        )

        if agendamento.data == hoje:
            periodo = 'hoje'
            periodo_label = 'Hoje'
        elif agendamento_dt < agora:
            periodo = 'passado'
            periodo_label = 'Realizado'
        else:
            periodo = 'futuro'
            periodo_label = 'Agendado'

        detalhes.append({
            'id': agendamento.id,
            'data_iso': agendamento.data.isoformat(),
            'data_formatada': agendamento.data.strftime('%d/%m/%Y'),
            'dia_semana': dia_semana,
            'horario': horario,
            'semana_mes': semana_mes,
            'semana_mes_label': f'{semana_mes}ª semana do mês',
            'servico': servico_nome,
            'duracao_minutos': duracao,
            'preco': preco,
            'profissional': profissional,
            'periodo': periodo,
            'periodo_label': periodo_label
        })

        if agendamento_dt <= agora:
            historicos.append((agendamento_dt, agendamento))
        else:
            futuros.append((agendamento_dt, agendamento))

        contagem_dias[dia_semana] += 1
        contagem_horarios[horario] += 1
        contagem_semanas[semana_mes] += 1
        contagem_servicos[servico_nome] += 1
        contagem_meses[(agendamento.data.year, agendamento.data.month)] += 1

        if preco is not None:
            valor_total += preco

    historicos.sort(key=lambda item: item[0])
    futuros.sort(key=lambda item: item[0])

    primeira_visita_dt = historicos[0][0] if historicos else None
    ultima_visita_dt = historicos[-1][0] if historicos else None
    proximo_agendamento_dt = futuros[0][0] if futuros else None

    intervalos = []
    for anterior, atual in zip(historicos, historicos[1:]):
        diferenca = (atual[0].date() - anterior[0].date()).days
        if diferenca >= 0:
            intervalos.append(diferenca)

    media_intervalo_dias = (
        round(sum(intervalos) / len(intervalos), 1)
        if intervalos else None
    )

    def mais_frequente(contador):
        return contador.most_common(1)[0][0] if contador else None

    semana_preferida = mais_frequente(contagem_semanas)

    agendamentos_por_mes = []
    for (ano, mes_num), total in sorted(
        contagem_meses.items(),
        key=lambda item: item[0],
        reverse=True
    ):
        agendamentos_por_mes.append({
            'ano': ano,
            'mes': mes_num,
            'label': meses_nomes[mes_num - 1],
            'total': total
        })

    # Mantém futuros primeiro (mais próximo), depois hoje e o histórico recente.
    ordem_periodo = {'futuro': 0, 'hoje': 1, 'passado': 2}
    detalhes.sort(
        key=lambda item: (
            ordem_periodo[item['periodo']],
            item['data_iso'] if item['periodo'] != 'passado' else '',
            item['horario']
        )
    )
    futuros_detalhes = [item for item in detalhes if item['periodo'] == 'futuro']
    hoje_detalhes = [item for item in detalhes if item['periodo'] == 'hoje']
    passados_detalhes = sorted(
        [item for item in detalhes if item['periodo'] == 'passado'],
        key=lambda item: (item['data_iso'], item['horario']),
        reverse=True
    )
    detalhes = futuros_detalhes + hoje_detalhes + passados_detalhes

    total_mes_atual = sum(
        1 for agendamento in agendamentos
        if agendamento.data.year == hoje.year
        and agendamento.data.month == hoje.month
    )

    return jsonify({
        'success': True,
        'cliente': {
            'id': cliente.id,
            'nome': cliente.nome,
            'telefone': cliente.telefone,
            'recorrente': cliente.recorrente or 'nao',
            'total_agendamentos': len(agendamentos),
            'total_realizados': len(historicos),
            'total_futuros': len(futuros),
            'total_mes_atual': total_mes_atual,
            'limite_mensal_referencia': 4,
            'passou_limite_mes': total_mes_atual > 4,
            'primeira_visita': (
                primeira_visita_dt.strftime('%d/%m/%Y às %H:%M')
                if primeira_visita_dt else None
            ),
            'ultima_visita': (
                ultima_visita_dt.strftime('%d/%m/%Y às %H:%M')
                if ultima_visita_dt else None
            ),
            'proximo_agendamento': (
                proximo_agendamento_dt.strftime('%d/%m/%Y às %H:%M')
                if proximo_agendamento_dt else None
            ),
            'dia_preferido': mais_frequente(contagem_dias),
            'horario_preferido': mais_frequente(contagem_horarios),
            'semana_mes_preferida': (
                f'{semana_preferida}ª semana do mês'
                if semana_preferida else None
            ),
            'servico_preferido': mais_frequente(contagem_servicos),
            'media_intervalo_dias': media_intervalo_dias,
            'valor_total_agendado': round(valor_total, 2),
            'agendamentos_por_mes': agendamentos_por_mes,
            'agendamentos': detalhes
        }
    })


from collections import defaultdict
from datetime import date

@main.route('/clientes')
@login_required
def clientes():

    user_id = session['user_id']

    agendamentos = (
        Agendamento.query
        .filter_by(usuario_id=user_id)
        .order_by(Agendamento.data.desc())
        .all()
    )

    clientes_dict = {}

    hoje = date.today()

    for ag in agendamentos:

        telefone = ag.telefone

        if telefone not in clientes_dict:

            dias_sem_visita = (
                hoje - ag.data
            ).days

            if dias_sem_visita <= 30:
                status = 'ativo'
            elif dias_sem_visita <= 60:
                status = 'atencao'
            else:
                status = 'inativo'

            clientes_dict[telefone] = {
                'nome': ag.nome,
                'telefone': telefone,
                'visitas': 1,
                'ultima_visita': ag.data,
                'status': status
            }

        else:

            clientes_dict[telefone]['visitas'] += 1

    clientes = sorted(
        clientes_dict.values(),
        key=lambda x: x['ultima_visita'],
        reverse=True
    )

    return render_template(
        'clientes.html',
        clientes=clientes
    )

@main.route('/excluir_servico/<int:id>', methods=['POST'])
@login_required
def excluir_servico(id):

    try:
        servico = Servico.query.filter_by(
            id=id,
            usuario_id=session["user_id"]
        ).first_or_404()

        db.session.delete(servico)
        db.session.commit()

        return jsonify({
            'mensagem': 'Serviço excluído com sucesso!'
        })

    except Exception as e:
        db.session.rollback()

        current_app.logger.exception(
            f"Erro ao excluir serviço {id}"
        )

        return jsonify({
            'erro': str(e)
        }), 500

@main.route('/financeiro')
@login_required
def financeiro():
    user_id = session["user_id"]

    hoje = date.today()

    inicio_semana = hoje - timedelta(days=hoje.weekday())
    fim_semana = inicio_semana + timedelta(days=6)

    inicio_mes = hoje.replace(day=1)

    faturamento_hoje = 0
    faturamento_semana = 0
    faturamento_mes = 0
    qtd_agendamentos_mes = 0

    agendamentos = (
        Agendamento.query
        .filter_by(usuario_id=user_id)
        .order_by(Agendamento.data.desc(), Agendamento.horario.desc())
        .all()
    )

    movimentacoes = []

    for ag in agendamentos:
        valor = 0

        if ag.servico and ag.servico.preco:
            valor = float(ag.servico.preco)

        if ag.data == hoje:
            faturamento_hoje += valor

        if inicio_semana <= ag.data <= fim_semana:
            faturamento_semana += valor

        if ag.data >= inicio_mes:
            faturamento_mes += valor
            qtd_agendamentos_mes += 1

        movimentacoes.append({
            "data": ag.data.strftime("%d/%m/%Y"),
            "horario": ag.horario.strftime("%H:%M") if ag.horario else "",
            "cliente": ag.nome,
            "servico": ag.servico.titulo if ag.servico else "Serviço removido",
            "valor": valor,
            "status": "Agendado"
        })

    ticket_medio = (
        faturamento_mes / qtd_agendamentos_mes
        if qtd_agendamentos_mes > 0
        else 0
    )

    return render_template(
        "financeiro.html",
        total_hoje=faturamento_hoje,
        total_semana=faturamento_semana,
        total_mes=faturamento_mes,
        ticket_medio=ticket_medio,
        total_agendamentos_mes=qtd_agendamentos_mes,
        movimentacoes=movimentacoes
    )

@main.route("/estoque", methods=["GET", "POST"])
@login_required
def estoque():
    user_id = session["user_id"]

    if request.method == "POST":

        nome = (request.form.get("nome") or "").strip()
        quantidade = request.form.get("quantidade") or 0
        valor_compra = request.form.get("valor_compra") or 0
        valor_venda = request.form.get("valor_venda") or 0

        if not nome:
            flash("Informe o nome do produto.")
            return redirect(url_for("main.estoque"))

        try:
            quantidade = int(quantidade)
            valor_compra = float(valor_compra)
            valor_venda = float(valor_venda)
        except Exception:
            flash("Dados inválidos para quantidade ou valores.")
            return redirect(url_for("main.estoque"))

        if quantidade < 0:
            flash("A quantidade não pode ser negativa.")
            return redirect(url_for("main.estoque"))

        novo_produto = Produto(
            usuario_id=user_id,
            nome=nome,
            quantidade_atual=quantidade,
            valor_compra=valor_compra,
            valor_venda=valor_venda,
            estoque_minimo=5,
            ativo=True
        )

        db.session.add(novo_produto)
        db.session.commit()

        movimentacao = MovimentacaoProduto(
            produto_id=novo_produto.id,
            usuario_id=user_id,
            tipo="ENTRADA",
            quantidade=quantidade,
            valor_unitario=valor_compra,
            observacao="Cadastro inicial"
        )

        db.session.add(movimentacao)
        db.session.commit()

        flash("Produto cadastrado com sucesso.")
        return redirect(url_for("main.estoque"))

    produtos_db = (
        Produto.query
        .filter_by(
            usuario_id=user_id,
            ativo=True
        )
        .order_by(Produto.nome)
        .all()
    )

    produtos = []

    for p in produtos_db:
        quantidade = int(p.quantidade_atual or 0)
        valor_compra = float(p.valor_compra or 0)
        valor_venda = float(p.valor_venda or 0)

        total_estoque = quantidade * valor_compra
        lucro = (valor_venda - valor_compra) * quantidade

        produtos.append({
            "id": p.id,
            "nome": p.nome,
            "quantidade": quantidade,
            "valor_compra": valor_compra,
            "valor_venda": valor_venda,
            "total_estoque": total_estoque,
            "lucro": lucro,
            "status": (
                "Esgotado"
                if quantidade <= 0
                else "Baixo Estoque"
                if quantidade <= p.estoque_minimo
                else "Disponível"
            )
        })

    total_produtos = len(produtos)

    total_itens = sum(
        p["quantidade"]
        for p in produtos
    )

    valor_investido = sum(
        p["quantidade"] * p["valor_compra"]
        for p in produtos
    )

    valor_potencial = sum(
        p["quantidade"] * p["valor_venda"]
        for p in produtos
    )

    lucro_estimado = valor_potencial - valor_investido

    return render_template(
        "estoque.html",
        produtos=produtos,
        total_produtos=total_produtos,
        total_itens=total_itens,
        valor_investido=valor_investido,
        valor_potencial=valor_potencial,
        lucro_estimado=lucro_estimado
    )

@main.route("/estoque/produto/<int:id>/editar", methods=["POST"])
@login_required
def editar_produto_estoque(id):
    user_id = session["user_id"]

    produto = Produto.query.filter_by(
        id=id,
        usuario_id=user_id,
        ativo=True
    ).first_or_404()

    nome = (request.form.get("nome") or "").strip()
    quantidade = request.form.get("quantidade") or 0
    valor_compra = request.form.get("valor_compra") or 0
    valor_venda = request.form.get("valor_venda") or 0

    if not nome:
        flash("Informe o nome do produto.")
        return redirect(url_for("main.estoque"))

    try:
        quantidade = int(quantidade)
        valor_compra = float(valor_compra)
        valor_venda = float(valor_venda)
    except Exception:
        flash("Dados inválidos para quantidade ou valores.")
        return redirect(url_for("main.estoque"))

    if quantidade < 0:
        flash("A quantidade não pode ser negativa.")
        return redirect(url_for("main.estoque"))

    produto.nome = nome
    produto.quantidade_atual = quantidade
    produto.valor_compra = valor_compra
    produto.valor_venda = valor_venda

    db.session.commit()

    flash("Produto atualizado com sucesso.")
    return redirect(url_for("main.estoque"))


@main.route("/estoque/produto/<int:id>/excluir", methods=["POST"])
@login_required
def excluir_produto_estoque(id):
    user_id = session["user_id"]

    produto = Produto.query.filter_by(
        id=id,
        usuario_id=user_id,
        ativo=True
    ).first_or_404()

    produto.ativo = False

    db.session.commit()

    flash("Produto removido do estoque.")
    return redirect(url_for("main.estoque"))


@main.route("/estoque/produto/vender", methods=["POST"])
@login_required
def vender_produto_estoque():
    user_id = session["user_id"]

    produto_id = request.form.get("produto_id")
    quantidade_vendida = request.form.get("quantidade_vendida") or 0
    valor_venda_real = request.form.get("valor_venda_real") or 0
    observacao = (request.form.get("observacao") or "").strip()

    try:
        produto_id = int(produto_id)
        quantidade_vendida = int(quantidade_vendida)
    except Exception:
        flash("Dados inválidos para venda.")
        return redirect(url_for("main.estoque"))

    if quantidade_vendida <= 0:
        flash("A quantidade vendida deve ser maior que zero.")
        return redirect(url_for("main.estoque"))

    produto = Produto.query.filter_by(
        id=produto_id,
        usuario_id=user_id,
        ativo=True
    ).first_or_404()

    if quantidade_vendida > int(produto.quantidade_atual or 0):
        flash("Quantidade vendida maior que o estoque disponível.")
        return redirect(url_for("main.estoque"))

    try:
        if valor_venda_real:
            valor_venda_real = float(valor_venda_real)
        else:
            valor_venda_real = float(produto.valor_venda or 0)
    except Exception:
        flash("Valor de venda inválido.")
        return redirect(url_for("main.estoque"))

    produto.quantidade_atual = int(produto.quantidade_atual or 0) - quantidade_vendida

    movimentacao = MovimentacaoProduto(
        produto_id=produto.id,
        usuario_id=user_id,
        tipo="SAIDA",
        quantidade=quantidade_vendida,
        valor_unitario=valor_venda_real,
        observacao=observacao or "Venda / saída de produto"
    )

    db.session.add(movimentacao)
    db.session.commit()

    flash("Saída registrada com sucesso.")
    return redirect(url_for("main.estoque"))

@main.route("/estoque/movimentacoes")
@login_required
def movimentacoes_estoque():
    user_id = session["user_id"]

    movimentacoes = (
        MovimentacaoProduto.query
        .filter_by(usuario_id=user_id)
        .order_by(MovimentacaoProduto.criado_em.desc())
        .all()
    )

    total_entradas = sum(
        m.quantidade for m in movimentacoes if m.tipo == "ENTRADA"
    )

    total_saidas = sum(
        m.quantidade for m in movimentacoes if m.tipo == "SAIDA"
    )

    valor_entradas = sum(
        m.quantidade * float(m.valor_unitario or 0)
        for m in movimentacoes
        if m.tipo == "ENTRADA"
    )

    valor_saidas = sum(
        m.quantidade * float(m.valor_unitario or 0)
        for m in movimentacoes
        if m.tipo == "SAIDA"
    )

    return render_template(
        "movimentacoes_estoque.html",
        movimentacoes=movimentacoes,
        total_entradas=total_entradas,
        total_saidas=total_saidas,
        valor_entradas=valor_entradas,
        valor_saidas=valor_saidas
    )

@main.route("/clientes-vip")
@login_required
def clientes_vip():
    user_id = session["user_id"]

    clientes = (
        Cliente.query
        .filter_by(usuario_id=user_id)
        .order_by(Cliente.nome)
        .all()
    )

    return render_template(
        "clientes_vip.html",
        clientes=clientes,
        clientes_vip=[],
        total_clientes=len(clientes),
        total_vip=0,
        total_premium=0,
        total_super_premium=0
    )

@main.route("/clientes-vip/atualizar", methods=["POST"])
@login_required
def atualizar_cliente_vip():
    flash("Função em desenvolvimento.")
    return redirect(url_for("main.clientes_vip"))
