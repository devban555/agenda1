from flask import Blueprint, render_template, request, redirect, flash, url_for
from . import db
from .models import Agendamento
from datetime import datetime
from flask import jsonify
from app.models import Servico
from flask import Blueprint


main = Blueprint('main', __name__)

@main.route('/', methods=['GET', 'POST'])
def home():
    return render_template('index.html')

@main.route('/admin', methods=['GET', 'POST'])
def admin():
    from datetime import datetime
    data_filtro = request.form.get('data')

    if data_filtro:
        try:
            data_obj = datetime.strptime(data_filtro, '%Y-%m-%d').date()
            agendamentos = Agendamento.query.filter_by(data=data_obj).order_by(Agendamento.hora).all()
        except:
            agendamentos = []
    else:
        agendamentos = Agendamento.query.order_by(Agendamento.data, Agendamento.hora).all()

    return render_template('admin.html', agendamentos=agendamentos, data_filtro=data_filtro)

@main.route('/agendar/<int:servico_id>')
def agendar_por_id(servico_id):
    servico = Servico.query.get_or_404(servico_id)
    # página com título/valor/tempo + escolha de data/hora (com horários ocupados desabilitados)
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
    data_str   = request.form.get('data')
    hora_str   = request.form.get('hora')

    if not servico_id or not data_str or not hora_str:
        return "Dados insuficientes.", 400

    servico = Servico.query.get_or_404(int(servico_id))

    data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
    hora_obj = datetime.strptime(hora_str, '%H:%M').time()

    # bloqueia horário globalmente (independente do serviço)
    existe = Agendamento.query.filter_by(data=data_obj, hora=hora_obj).first()
    if existe:
        return "Horário já agendado. Volte e escolha outro.", 409

    # Vai para tela de confirmação de dados do cliente
    return render_template(
        'confirmar_dados.html',
        servico=servico.titulo,  # mantendo seu modelo atual com texto do serviço
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

    servico_texto = request.form.get('servico')  # vindo do form
    if not servico_texto:
        sid = request.form.get('servico_id')
        if sid:
            s = Servico.query.get(int(sid))
            servico_texto = s.titulo if s else 'Serviço'

    novo = Agendamento(
        nome=nome,
        telefone=telefone,
        servico=servico_texto,
        data=data,
        hora=hora
    )
    db.session.add(novo)
    db.session.commit()

    # Renderiza o template com os dados
    return render_template(
        'confirmacao.html',
        nome=nome,
        servico=servico_texto,
        data_str=data.strftime('%d/%m'),
        hora_str=hora.strftime('%H:%M')
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

    if request.method == 'POST':
        telefone = request.form['telefone']
        agendamentos = Agendamento.query.filter_by(telefone=telefone).order_by(Agendamento.data, Agendamento.hora).all()

    return render_template('consultar.html', agendamentos=agendamentos, telefone=telefone)

@main.route('/cancelar/<int:id>', methods=['POST'])
def cancelar(id):
    agendamento = Agendamento.query.get_or_404(id)

    # Salva o telefone antes de excluir para redirecionar
    telefone = agendamento.telefone

    db.session.delete(agendamento)
    db.session.commit()

    flash('Agendamento cancelado com sucesso!')
    return redirect(url_for('main.consultar'))

@main.route("/painel")
def painel():
    return render_template("painel.html")

@main.route('/excluir_servico/<int:id>', methods=['POST'])
def excluir_servico(id):
    servico = Servico.query.get_or_404(id)
    db.session.delete(servico)
    db.session.commit()
    # pode retornar 204 sem corpo; o fetch trata como OK
    return ('', 204)

@main.route('/servicos', methods=['GET', 'POST'])
def servicos():
    if request.method == 'POST':
        titulo = request.form['titulo']
        valor = request.form['valor']
        tempo = request.form['tempo']
        novo_servico = Servico(titulo=titulo, valor=valor, tempo=tempo)
        db.session.add(novo_servico)
        db.session.commit()
        return redirect(url_for('main.servicos'))

    servicos = Servico.query.all()
    return render_template('servicos.html', servicos=servicos)

@main.route('/editar_servico/<int:id>', methods=['POST'])
def editar_servico(id):
    data = request.get_json()
    servico = Servico.query.get_or_404(id)

    servico.titulo = data.get('titulo')
    servico.valor = data.get('valor')
    servico.tempo = data.get('tempo')

    db.session.commit()
    return jsonify({'mensagem': 'Serviço atualizado com sucesso!'})

@main.route("/service")
def service():
    servicos = Servico.query.order_by(Servico.titulo).all()
    return render_template("service.html", servicos=servicos)

from sqlalchemy import extract, func

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