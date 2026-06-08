from flask import Blueprint, render_template, request, redirect, flash, url_for, jsonify, session
from functools import wraps
from datetime import datetime
from sqlalchemy import extract, func
from flask import current_app
from . import db
from .models import Agendamento
from app.models import Servico, Usuario, ConfiguracaoAgenda, ExcecaoAgenda

main = Blueprint('main', __name__)

from flask import session, redirect
from app.models import Usuario  # ajusta conforme seu projeto
from functools import wraps

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

    return render_template(
        'agendar_servico.html',
        servico=servico,
        usuario=usuario
    )


@main.route('/confirmar_agendamento', methods=['POST'])
def confirmar_agendamento():
    servico_id = request.form.get('servico_id')
    data_str = request.form.get('data')
    hora_str = request.form.get('hora')

    if not servico_id or not data_str or not hora_str:
        return "Dados insuficientes.", 400

    servico = Servico.query.get_or_404(int(servico_id))
    data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
    hora_obj = datetime.strptime(hora_str, '%H:%M').time()

    existe = Agendamento.query.filter_by(
        data=data_obj,
        horario=hora_obj,
        usuario_id=servico.usuario_id
    ).first()

    if existe:
        return "Horário já agendado. Volte e escolha outro.", 409

    return render_template(
        'confirmar_dados.html',
        servico=servico.titulo,
        data=data_str,
        hora=hora_str,
        servico_id=servico.id
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

    novo = Agendamento(
        usuario_id=servico.usuario_id,
        nome=nome,
        telefone=telefone,
        data=data,
        horario=hora,
        servico_id=servico.id
    )

    db.session.add(novo)
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
🛠️ Serviço: {servico.titulo}
📆 Data: {data.strftime('%d/%m/%Y')}
⏰ Hora: {hora.strftime('%H:%M')}

✅ Seu horário está reservado!
"""

        grupo_id = "120363406795388890@g.us"

        mensagem_grupo = f"""📢 *Novo Agendamento*

👤 {nome}
📞 {telefone}
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

    return render_template(
        'confirmacao.html',
        nome=nome,
        servico=servico.titulo,
        data_str=data.strftime('%d/%m'),
        hora_str=hora.strftime('%H:%M'),
        slug=slug
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

    config = ConfiguracaoAgenda.query.filter_by(
        usuario_id=usuario_id
    ).first()

    if not config:
        return jsonify([])

    dias_permitidos = config.dias_semana or []

    if dia_semana not in dias_permitidos:
        return jsonify([])

    horarios_cfg = config.horarios_base or {}

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

    excecao = ExcecaoAgenda.query.filter_by(
        usuario_id=usuario_id,
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


from datetime import datetime, date

@main.route('/verificar_horarios', methods=['POST'])
def verificar_horarios():
    data_json = request.get_json()

    data_str = data_json.get('data')
    servico_id = data_json.get('servico_id')

    if not data_str or not servico_id:
        return jsonify([])

    data = datetime.strptime(
        data_str,
        '%Y-%m-%d'
    ).date()

    # bloqueio data passada
    if data < date.today():
        return jsonify([])

    dia_semana = data.weekday()

    # serviço
    servico = Servico.query.get_or_404(servico_id)
    usuario_id = servico.usuario_id

    # configuração
    config = ConfiguracaoAgenda.query.filter_by(
        usuario_id=usuario_id
    ).first()

    if not config:
        return jsonify([])

    dias_permitidos = config.dias_semana or []

    # dia não permitido
    if dia_semana not in dias_permitidos:
        return jsonify([])

    # ==========================
    # NOVO FORMATO DE HORÁRIOS
    # ==========================
    horarios_cfg = config.horarios_base or {}

    if isinstance(horarios_cfg, dict):

        if dia_semana == 5:
            horarios_base = horarios_cfg.get(
                'sabado',
                []
            )
        else:
            horarios_base = horarios_cfg.get(
                'semana',
                []
            )

    else:
        # compatibilidade com formato antigo
        horarios_base = horarios_cfg

    # exceção
    excecao = ExcecaoAgenda.query.filter_by(
        usuario_id=usuario_id,
        data=data
    ).first()

    if excecao:

        if not excecao.dia_ativo:
            return jsonify([])

        horarios_base = [
            h
            for h in horarios_base
            if h not in (
                excecao.horarios_bloqueados or []
            )
        ]

    # agendados
    agendados = Agendamento.query.filter_by(
        usuario_id=usuario_id,
        data=data
    ).all()

    horarios_ocupados = {
        a.horario.strftime('%H:%M')
        for a in agendados
    }

    agora = datetime.now()

    horarios_disponiveis = []

    for h in horarios_base:

        try:
            hora_obj = datetime.strptime(
                h,
                "%H:%M"
            ).time()

        except Exception:
            continue

        data_hora = datetime.combine(
            data,
            hora_obj
        )

        # remove passados
        if data_hora <= agora:
            continue

        # remove ocupados
        if h in horarios_ocupados:
            continue

        horarios_disponiveis.append(h)

    return jsonify(horarios_disponiveis)

@main.route('/relatorio')
@login_required
def relatorio():
    # Total de agendamentos
    total_agendamentos = Agendamento.query.count()

    # Melhor mês do ano (mês com mais agendamentos)
    dados_por_mes = (
        db.session.query(
            extract('month', Agendamento.data).label('mes'),
            func.count(Agendamento.id).label('total')
        )
        .group_by('mes')
        .order_by(func.count(Agendamento.id).desc())
        .all()
    )
    melhor_mes = None
    if dados_por_mes:
        meses_nomes = [
            "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
        ]
        melhor_mes = meses_nomes[int(dados_por_mes[0].mes) - 1]

    # Total de cancelados (considerando que há um campo status='cancelado')
    total_cancelados = Agendamento.query.filter_by(status='cancelado').count() if hasattr(Agendamento, 'status') else 0

    # Total de agendamentos no ano atual
    ano_atual = datetime.now().year
    total_no_ano = Agendamento.query.filter(extract('year', Agendamento.data) == ano_atual).count()

    return render_template(
        'relatorio.html',
        total_agendamentos=total_agendamentos,
        melhor_mes=melhor_mes,
        total_cancelados=total_cancelados,
        total_no_ano=total_no_ano
    )

@main.route("/lista")
@login_required
def lista():
    return render_template("lista.html")

@main.route("/suporte")
@login_required
def suporte():
    return render_template("suporte.html")

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

    if request.method == 'POST':
        telefone = request.form['telefone']
        agendamentos = Agendamento.query.filter_by(
            telefone=telefone
        ).order_by(
            Agendamento.data,
            Agendamento.horario
        ).all()

        if agendamentos:
            slug = agendamentos[0].usuario.slug

    return render_template(
        'consultar.html',
        agendamentos=agendamentos,
        telefone=telefone,
        slug=slug
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

    return render_template('painel.html', whatsapp=whatsapp)


@main.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    from datetime import datetime, date, timedelta

    data_filtro = request.form.get('data')
    user_id = session["user_id"]

    if data_filtro:
        try:
            data_obj = datetime.strptime(data_filtro, '%Y-%m-%d').date()

            agendamentos = Agendamento.query.filter_by(
                usuario_id=user_id,
                data=data_obj
            ).order_by(
                Agendamento.horario
            ).all()

        except:
            agendamentos = []

    else:
        agendamentos = Agendamento.query.filter_by(
            usuario_id=user_id
        ).order_by(
            Agendamento.data,
            Agendamento.horario
        ).all()

    hoje = date.today()
    amanha = hoje + timedelta(days=1)
    fim_semana = hoje + timedelta(days=7)

    total_hoje = Agendamento.query.filter_by(
        usuario_id=user_id,
        data=hoje
    ).count()

    total_amanha = Agendamento.query.filter_by(
        usuario_id=user_id,
        data=amanha
    ).count()

    total_semana = Agendamento.query.filter(
        Agendamento.usuario_id == user_id,
        Agendamento.data >= hoje,
        Agendamento.data <= fim_semana
    ).count()

    proximo_agendamento = Agendamento.query.filter(
        Agendamento.usuario_id == user_id,
        Agendamento.data >= hoje
    ).order_by(
        Agendamento.data,
        Agendamento.horario
    ).first()

    return render_template(
        'admin.html',
        agendamentos=agendamentos,
        data_filtro=data_filtro,
        total_hoje=total_hoje,
        total_amanha=total_amanha,
        total_semana=total_semana,
        proximo_agendamento=proximo_agendamento
    )


@main.route('/servicos', methods=['GET', 'POST'])
@login_required
def servicos():
    user_id = session["user_id"]

    if request.method == 'POST':
        novo_servico = Servico(
            usuario_id=user_id,
            titulo=request.form['titulo'],
            valor=request.form['valor'],
            tempo=request.form['tempo']
        )
        db.session.add(novo_servico)
        db.session.commit()
        return redirect(url_for('main.servicos'))

    servicos = Servico.query.filter_by(
        usuario_id=user_id
    ).all()

    return render_template('servicos.html', servicos=servicos)


@main.route('/editar_servico/<int:id>', methods=['POST'])
@login_required
def editar_servico(id):
    data = request.get_json()

    servico = Servico.query.filter_by(
        id=id,
        usuario_id=session["user_id"]
    ).first_or_404()

    servico.titulo = data.get('titulo')
    servico.valor = data.get('valor')
    servico.tempo = data.get('tempo')

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

    servicos = Servico.query.filter_by(
        usuario_id=usuario.id
    ).order_by(Servico.titulo).all()

    return render_template(
        "service.html",
        servicos=servicos,
        usuario=usuario
    )


@main.route('/agenda/<slug>/consultar', methods=['GET', 'POST'])
def consultar_publico(slug):
    usuario = Usuario.query.filter_by(slug=slug).first_or_404()

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
        slug=slug
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
    return render_template('setup.html')

@main.route('/configuracao_base', methods=['GET'])
@login_required
def configuracao_base():
    config = ConfiguracaoAgenda.query.filter_by(
        usuario_id=session['user_id']
    ).first()

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
    data = request.get_json()

    config = ConfiguracaoAgenda.query.filter_by(
        usuario_id=session['user_id']
    ).first()

    if not config:
        config = ConfiguracaoAgenda(
            usuario_id=session['user_id']
        )
        db.session.add(config)

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
    data = request.get_json()

    data_obj = datetime.strptime(data['data'], '%Y-%m-%d').date()

    excecao = ExcecaoAgenda.query.filter_by(
        usuario_id=session['user_id'],
        data=data_obj
    ).first()

    if not excecao:
        excecao = ExcecaoAgenda(
            usuario_id=session['user_id'],
            data=data_obj
        )
        db.session.add(excecao)

    excecao.dia_ativo = data.get('dia_ativo', True)
    excecao.horarios_bloqueados = data.get('horarios_bloqueados', [])

    db.session.commit()

    # 🔥 LOG AQUI (após salvar)
    current_app.logger.info(
        f"ExcecaoAgenda | usuario_id={session['user_id']} | data={data_obj} | ativo={excecao.dia_ativo} | bloqueados={excecao.horarios_bloqueados}"
    )

    return jsonify({'status':'ok'})

@main.route('/salvar_identidade', methods=['POST'])
@login_required
def salvar_identidade():
    data = request.get_json()

    usuario = Usuario.query.get(session['user_id'])

    usuario.nome_fantasia = data.get('nome_fantasia')
    usuario.fonte_titulo = data.get('fonte_titulo', 'padrao')
    usuario.tema = data.get('tema', 'principal')

    db.session.commit()
    return jsonify({'status': 'ok'})

@main.route('/masteradm')
@master_required
def masteradm():
    return render_template('masteradm.html')

@main.route('/usuarios')
@master_required
def usuarios():
    lista_usuarios = Usuario.query.all()
    print(lista_usuarios)  # 🔥 DEBUG
    return render_template('usuarios.html', usuarios=lista_usuarios)

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
    return render_template('disponibilidade.html')

@main.route('/carregar_disponibilidade', methods=['POST'])
@login_required
def carregar_disponibilidade():

    data_str = request.json.get('data')

    if not data_str:
        return jsonify({
            'horarios': [],
            'bloqueados': []
        })

    data = datetime.strptime(
        data_str,
        '%Y-%m-%d'
    ).date()

    config = ConfiguracaoAgenda.query.filter_by(
        usuario_id=session['user_id']
    ).first()

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

    excecao = ExcecaoAgenda.query.filter_by(
        usuario_id=session['user_id'],
        data=data
    ).first()

    bloqueados = []

    if excecao:
        bloqueados = (
            excecao.horarios_bloqueados
            or []
        )

    return jsonify({
        'horarios': horarios,
        'bloqueados': bloqueados
    })

@main.route('/salvar_disponibilidade', methods=['POST'])
@login_required
def salvar_disponibilidade():

    data_str = request.json.get('data')
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

    excecao = ExcecaoAgenda.query.filter_by(
        usuario_id=session['user_id'],
        data=data
    ).first()

    if not excecao:

        excecao = ExcecaoAgenda(
            usuario_id=session['user_id'],
            data=data,
            dia_ativo=True
        )

        db.session.add(excecao)

    excecao.horarios_bloqueados = bloqueados

    db.session.commit()

    return jsonify({
        'status': 'ok'
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