from flask import Blueprint, render_template, request, redirect, flash, url_for, jsonify, session
from functools import wraps
from datetime import datetime
from sqlalchemy import extract, func
from flask import session
from . import db
from .models import Agendamento
from app.models import Servico
from app.models import Usuario

main = Blueprint('main', __name__)

# =========================
# AUTH DECORATOR (necessário)
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
    return render_template('index.html')


@main.route('/agendar/<int:servico_id>')
def agendar_por_id(servico_id):
    servico = Servico.query.get_or_404(servico_id)
    return render_template('agendar_servico.html', servico=servico)


@main.route('/agendar/<servico>')
def agendar_servico(servico):
    servicos = {
        'corte': {'nome': 'Corte', 'valor': 'R$ 45,00', 'tempo': '01:00'},
        'corte_barba': {'nome': 'Corte + Barba', 'valor': 'R$ 65,00', 'tempo': '01:30'},
        'corte_sobrancelha': {'nome': 'Corte + Sobrancelha', 'valor': 'R$ 59,00', 'tempo': '01:00'},
        'corte_barba_sobrancelha': {'nome': 'Corte + Barba + Sobrancelha', 'valor': 'R$ 70,00', 'tempo': '01:40'},
    }

    if servico not in servicos:
        return "Serviço inválido", 404

    dados = servicos[servico]
    return render_template('agendar_servico.html', servico=dados, id_servico=servico)


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

    existe = Agendamento.query.filter_by(data=data_obj, hora=hora_obj).first()
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

    # serviço selecionado pelo cliente
    sid = request.form.get('servico_id')
    servico = Servico.query.get_or_404(int(sid))

    novo = Agendamento(
        usuario_id=servico.usuario_id,   # 🔐 vínculo correto com o admin
        nome=nome,
        telefone=telefone,
        servico=servico.titulo,
        data=data,
        hora=hora
    )

    db.session.add(novo)
    db.session.commit()

    # 🔑 slug público correto
    slug = servico.usuario.slug

    return render_template(
        'confirmacao.html',
        nome=nome,
        servico=servico.titulo,
        data_str=data.strftime('%d/%m'),
        hora_str=hora.strftime('%H:%M'),
        slug=slug
    )

@main.route('/verificar_horarios', methods=['POST'])
def verificar_horarios():
    data = request.json.get('data')
    if not data:
        return jsonify([])

    data_obj = datetime.strptime(data, '%Y-%m-%d').date()
    agendamentos = Agendamento.query.filter_by(data=data_obj).all()
    horarios_ocupados = [ag.hora.strftime('%H:%M') for ag in agendamentos]
    return jsonify(horarios_ocupados)


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
            Agendamento.hora
        ).all()

        if agendamentos:
            # 🔑 envia o SLUG público para o template
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
            ).order_by(Agendamento.hora).all()
        except:
            agendamentos = []
    else:
        agendamentos = Agendamento.query.filter_by(
            usuario_id=user_id
        ).order_by(Agendamento.data, Agendamento.hora).all()

    return render_template(
        'admin.html',
        agendamentos=agendamentos,
        data_filtro=data_filtro
    )

@main.route('/excluir_servico/<int:id>', methods=['POST'])
@login_required
def excluir_servico(id):
    servico = Servico.query.filter_by(
        id=id,
        usuario_id=session["user_id"]
    ).first_or_404()

    db.session.delete(servico)
    db.session.commit()
    return ('', 204)



@main.route('/servicos', methods=['GET', 'POST'])
@login_required
def servicos():
    user_id = session["user_id"]

    if request.method == 'POST':
        novo_servico = Servico(
            usuario_id=user_id,              # 🔐 vínculo
            titulo=request.form['titulo'],
            valor=request.form['valor'],
            tempo=request.form['tempo']
        )
        db.session.add(novo_servico)
        db.session.commit()
        return redirect(url_for('main.servicos'))

    # 🔐 lista apenas do usuário logado
    servicos = Servico.query.filter_by(usuario_id=user_id).all()
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
# OUTRAS ROTAS
# =========================
@main.route("/service")
@login_required
def service():
    usuario = Usuario.query.get_or_404(session["user_id"])

    return redirect(
        url_for(
            "main.agenda_publica_slug",
            slug=usuario.slug
        )
    )


@main.route('/relatorio')
@login_required
def relatorio():
    total_agendamentos = Agendamento.query.count()

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

    ano_atual = datetime.now().year
    total_no_ano = Agendamento.query.filter(
        extract('year', Agendamento.data) == ano_atual
    ).count()

    return render_template(
        'relatorio.html',
        total_agendamentos=total_agendamentos,
        melhor_mes=melhor_mes,
        total_cancelados=0,
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

@main.route("/u/<username>")
def agenda_publica(username):
    # identifica o admin pelo username
    usuario = Usuario.query.filter_by(username=username).first_or_404()

    # busca somente os serviços desse admin
    servicos = Servico.query.filter_by(
        usuario_id=usuario.id
    ).order_by(Servico.titulo).all()

    return render_template(
        "service.html",
        servicos=servicos,
        usuario=usuario
    )

from app.models import Usuario, Servico

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
            Agendamento.hora
        ).all()

    return render_template(
        'consultar.html',
        agendamentos=agendamentos,
        telefone=telefone,
        slug=slug
    )
