from flask import Blueprint, render_template, request, redirect, flash, url_for, jsonify, session
from functools import wraps
from datetime import datetime
from sqlalchemy import extract, func

from . import db
from .models import Agendamento
from app.models import Servico, Usuario, ConfiguracaoAgenda, ExcecaoAgenda

main = Blueprint('main', __name__)

# =========================
# AUTH DECORATOR
# =========================
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


@main.route('/salvar_agendamento', methods=['POST'])
def salvar_agendamento():
    nome = request.form['nome']
    telefone = request.form['telefone']
    data = datetime.strptime(request.form['data'], '%Y-%m-%d').date()
    hora = datetime.strptime(request.form['hora'], '%H:%M').time()

    sid = request.form.get('servico_id')
    servico = Servico.query.get_or_404(int(sid))

    novo = Agendamento(
        usuario_id=servico.usuario_id,
        nome=nome,
        telefone=telefone,
        data=data,
        horario=hora
    )

    db.session.add(novo)
    db.session.commit()

    slug = servico.usuario.slug

    return render_template(
        'confirmacao.html',
        nome=nome,
        servico=servico.titulo,
        data_str=data.strftime('%d/%m'),
        hora_str=hora.strftime('%H:%M'),
        slug=slug
    )


# =========================
# DISPONIBILIDADE / HORÁRIOS
# =========================
@main.route('/horarios_disponiveis', methods=['POST'])
def horarios_disponiveis():
    data_str = request.json.get('data')
    usuario_id = request.json.get('usuario_id')

    if not data_str or not usuario_id:
        return jsonify([])

    data = datetime.strptime(data_str, '%Y-%m-%d').date()
    dia_semana = data.weekday()  # 0 = segunda

    config = ConfiguracaoAgenda.query.filter_by(
        usuario_id=usuario_id
    ).first()

    if not config:
        return jsonify([])

    dias_permitidos = [int(d) for d in config.dias_semana.split(',')]
    if dia_semana not in dias_permitidos:
        return jsonify([])

    horarios = config.horarios_base.split(',')

    excecao = ExcecaoAgenda.query.filter_by(
        usuario_id=usuario_id,
        data=data
    ).first()

    if excecao:
        if not excecao.dia_ativo:
            return jsonify([])

        if excecao.horarios_desativados:
            bloqueados = excecao.horarios_desativados.split(',')
            horarios = [h for h in horarios if h not in bloqueados]

    return jsonify(horarios)


@main.route('/verificar_horarios', methods=['POST'])
def verificar_horarios():
    data_json = request.get_json()
    data_str = data_json.get('data')
    servico_id = data_json.get('servico_id')

    if not data_str or not servico_id:
        return jsonify([])

    data = datetime.strptime(data_str, '%Y-%m-%d').date()
    dia_semana = data.weekday()  # 0 = segunda, 6 = domingo

    # serviço e usuário
    servico = Servico.query.get_or_404(servico_id)
    usuario_id = servico.usuario_id

    # configuração base
    config = ConfiguracaoAgenda.query.filter_by(
        usuario_id=usuario_id
    ).first()

    if not config:
        return jsonify([])

    # ✅ AGORA É LISTA, NÃO STRING
    dias_permitidos = config.dias_semana
    horarios_base = config.horarios_base

    # dia não permitido
    if dia_semana not in dias_permitidos:
        return jsonify([])

    # exceção por data
    excecao = ExcecaoAgenda.query.filter_by(
        usuario_id=usuario_id,
        data=data
    ).first()

    if excecao:
        if not excecao.dia_ativo:
            return jsonify([])

        horarios_base = [
            h for h in horarios_base
            if h not in (excecao.horarios_bloqueados or [])
        ]

    # horários já agendados
    agendados = Agendamento.query.filter_by(
        usuario_id=usuario_id,
        data=data
    ).all()

    horarios_ocupados = {a.horario.strftime('%H:%M') for a in agendados}

    # horários finais disponíveis
    horarios_disponiveis = [
        h for h in horarios_base
        if h not in horarios_ocupados
    ]

    return jsonify(horarios_disponiveis)

@main.route('/relatorio')
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
def lista():
    return render_template("lista.html")

@main.route("/suporte")
def suporte():
    return render_template("suporte.html")

@main.route("/eventos")
def eventos():
    return render_template("eventos.html")

# =========================
# CONSULTAS / CANCELAMENTO
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


@main.route('/cancelar/<int:id>', methods=['POST'])
def cancelar(id):
    agendamento = Agendamento.query.get_or_404(id)
    telefone = agendamento.telefone

    db.session.delete(agendamento)
    db.session.commit()

    flash('Agendamento cancelado com sucesso!')
    return redirect(url_for('main.consultar'))


# =========================
# ROTAS PROTEGIDAS
# =========================
@main.route('/painel')
@login_required
def painel():
    return render_template('painel.html')


@main.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    data_filtro = request.form.get('data')
    user_id = session["user_id"]

    if data_filtro:
        try:
            data_obj = datetime.strptime(data_filtro, '%Y-%m-%d').date()
            agendamentos = Agendamento.query.filter_by(
                usuario_id=user_id,
                data=data_obj
            ).order_by(Agendamento.horario).all()
        except:
            agendamentos = []
    else:
        agendamentos = Agendamento.query.filter_by(
            usuario_id=user_id
        ).order_by(Agendamento.data, Agendamento.horario).all()

    return render_template(
        'admin.html',
        agendamentos=agendamentos,
        data_filtro=data_filtro
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

@main.route('/salvar_configuracao_base', methods=['POST'])
@login_required
def salvar_configuracao_base():
    data = request.get_json()

    config = ConfiguracaoAgenda.query.filter_by(
        usuario_id=session['user_id']
    ).first()

    if not config:
        config = ConfiguracaoAgenda(usuario_id=session['user_id'])
        db.session.add(config)

    config.dias_semana = data.get('dias_semana', [])
    config.horarios_base = data.get('horarios_base', [])

    db.session.commit()
    return jsonify({'status':'ok'})

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
