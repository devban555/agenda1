from collections import defaultdict
from datetime import date, datetime, timedelta
from functools import wraps
import secrets
import threading
import json
import time

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from . import db
from .models import Agendamento, Cliente, Produto, Servico

marketing = Blueprint('marketing', __name__)


_envios_lock = threading.Lock()
_envios = {}


def _criar_envio(usuario_id, total):
    envio_id = secrets.token_urlsafe(12)
    agora = datetime.now().isoformat(timespec='seconds')
    with _envios_lock:
        _envios[envio_id] = {
            'id': envio_id,
            'usuario_id': usuario_id,
            'status': 'processando',
            'total': int(total),
            'processados': 0,
            'enviados': 0,
            'falhas': 0,
            'criado_em': agora,
            'finalizado_em': None,
            'erro': None,
        }
    return envio_id


def _atualizar_envio(envio_id, **campos):
    with _envios_lock:
        envio = _envios.get(envio_id)
        if envio:
            envio.update(campos)


def _obter_envio(envio_id):
    with _envios_lock:
        envio = _envios.get(envio_id)
        return dict(envio) if envio else None


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return wrapper


def _metricas_clientes(usuario_id):
    hoje = date.today()
    limite_inativo = hoje - timedelta(days=60)

    clientes = Cliente.query.filter_by(usuario_id=usuario_id).all()
    agendamentos = (
        Agendamento.query
        .filter_by(usuario_id=usuario_id)
        .order_by(Agendamento.data.asc(), Agendamento.horario.asc())
        .all()
    )

    por_cliente = defaultdict(list)
    por_telefone = defaultdict(list)
    for ag in agendamentos:
        if ag.cliente_id:
            por_cliente[ag.cliente_id].append(ag)
        por_telefone[str(ag.telefone or '')].append(ag)

    resultado = []
    for cliente in clientes:
        historico = por_cliente.get(cliente.id) or por_telefone.get(str(cliente.telefone or ''), [])
        realizados = [ag for ag in historico if ag.data and ag.data <= hoje]
        futuros = [ag for ag in historico if ag.data and ag.data > hoje]

        ultima = max((ag.data for ag in realizados), default=None)
        proxima = min((ag.data for ag in futuros), default=None)
        visitas = len(realizados)

        if proxima:
            status = 'ativo'
        elif ultima and ultima >= limite_inativo:
            status = 'ativo'
        else:
            status = 'inativo'

        resultado.append({
            'id': cliente.id,
            'nome': cliente.nome,
            'telefone': cliente.telefone,
            'recorrente': cliente.recorrente,
            'status': status,
            'visitas': visitas,
            'ultima_visita': ultima.isoformat() if ultima else None,
            'proximo_agendamento': proxima.isoformat() if proxima else None,
        })

    resultado.sort(key=lambda item: (item['nome'] or '').lower())
    return resultado


def _filtrar_publico(clientes, publico):
    publico = (publico or 'todos').strip().lower()
    if publico == 'ativos':
        return [c for c in clientes if c['status'] == 'ativo']
    if publico == 'inativos':
        return [c for c in clientes if c['status'] == 'inativo']
    if publico == 'recorrentes':
        return [c for c in clientes if c['recorrente'] == 'sim']
    if publico == 'fidelizados':
        return [c for c in clientes if c['visitas'] >= 3]
    return clientes


def _clientes_selecionados(usuario_id, ids):
    ids_validos = []
    for valor in ids or []:
        try:
            ids_validos.append(int(valor))
        except (TypeError, ValueError):
            continue

    if not ids_validos:
        return []

    return (
        Cliente.query
        .filter(
            Cliente.usuario_id == usuario_id,
            Cliente.id.in_(ids_validos),
            Cliente.ativo_crm.is_(True),
        )
        .all()
    )


def _normalizar_numero(numero):
    digitos = ''.join(ch for ch in str(numero or '') if ch.isdigit())
    if digitos.startswith('0'):
        digitos = digitos[1:]
    if digitos and not digitos.startswith('55'):
        digitos = '55' + digitos
    return digitos


def _worker_envio(app, usuario_id, clientes_ids, mensagem, envio_id):
    with app.app_context():
        from .routes import enviar_whatsapp

        enviados = 0
        falhas = 0
        processados = 0

        try:
            clientes = _clientes_selecionados(usuario_id, clientes_ids)

            for indice, cliente in enumerate(clientes):
                numero = _normalizar_numero(cliente.telefone)
                sucesso = False

                if numero:
                    texto = str(mensagem or '').replace('{nome}', cliente.nome or 'cliente')
                    try:
                        sucesso = bool(enviar_whatsapp(usuario_id, numero, texto))
                    except Exception as exc:
                        app.logger.error(
                            'Marketing WhatsApp FAIL | usuario_id=%s | cliente_id=%s | erro=%s',
                            usuario_id,
                            cliente.id,
                            exc,
                        )

                if sucesso:
                    enviados += 1
                else:
                    falhas += 1

                processados += 1
                _atualizar_envio(
                    envio_id,
                    processados=processados,
                    enviados=enviados,
                    falhas=falhas,
                )

                if indice < len(clientes) - 1:
                    time.sleep(1.2)

            _atualizar_envio(
                envio_id,
                status='concluido',
                processados=processados,
                enviados=enviados,
                falhas=falhas,
                finalizado_em=datetime.now().isoformat(timespec='seconds'),
            )

        except Exception as exc:
            app.logger.exception(
                'Marketing campanha FAIL | usuario_id=%s | envio_id=%s',
                usuario_id,
                envio_id,
            )
            _atualizar_envio(
                envio_id,
                status='erro',
                erro=str(exc),
                finalizado_em=datetime.now().isoformat(timespec='seconds'),
            )


@marketing.get('/eventos/descontaco')
@login_required
def descontaco():
    return render_template('marketing_descontaco.html')


@marketing.get('/eventos/sorteio')
@login_required
def sorteio():
    return render_template('marketing_sorteio.html')


@marketing.get('/eventos/fidelidade')
@login_required
def fidelidade():
    clientes = _metricas_clientes(session['user_id'])
    ranking = sorted(
        [c for c in clientes if c['visitas'] > 0],
        key=lambda c: (-c['visitas'], c['nome'].lower()),
    )
    return render_template('marketing_fidelidade.html', ranking=ranking)


@marketing.get('/eventos/oferta-flash')
@login_required
def oferta_flash():
    usuario_id = session['user_id']
    servicos = (
        Servico.query
        .filter_by(usuario_id=usuario_id, ativo=True)
        .order_by(Servico.titulo.asc())
        .all()
    )
    produtos = (
        Produto.query
        .filter(
            Produto.usuario_id == usuario_id,
            Produto.ativo.is_(True),
            Produto.quantidade_atual > 0,
        )
        .order_by(Produto.nome.asc())
        .all()
    )
    servicos_json = json.dumps([
        {
            'id': s.id,
            'nome': s.titulo,
            'valor': float(s.preco or 0),
        }
        for s in servicos
    ], ensure_ascii=False)
    produtos_json = json.dumps([
        {
            'id': p.id,
            'nome': p.nome,
            'valor': float(p.valor_venda or 0),
            'estoque': int(p.quantidade_atual or 0),
        }
        for p in produtos
    ], ensure_ascii=False)
    return render_template(
        'marketing_oferta_flash.html',
        servicos=servicos,
        produtos=produtos,
        servicos_json=servicos_json,
        produtos_json=produtos_json,
    )


@marketing.get('/api/marketing/publico')
@login_required
def api_publico():
    publico = request.args.get('publico', 'todos')
    clientes = _filtrar_publico(_metricas_clientes(session['user_id']), publico)
    return jsonify({'clientes': clientes, 'total': len(clientes)})


@marketing.post('/api/marketing/sorteio')
@login_required
def api_sorteio():
    payload = request.get_json(silent=True) or {}
    publico = payload.get('publico', 'todos')
    ids = payload.get('clientes_ids') or []

    clientes = _filtrar_publico(_metricas_clientes(session['user_id']), publico)
    if ids:
        ids_set = {int(v) for v in ids if str(v).isdigit()}
        clientes = [c for c in clientes if c['id'] in ids_set]

    if not clientes:
        return jsonify({'success': False, 'error': 'Nenhum cliente disponível para este sorteio.'}), 400

    vencedor = secrets.choice(clientes)
    return jsonify({'success': True, 'vencedor': vencedor, 'participantes': len(clientes)})


@marketing.post('/api/marketing/enviar')
@login_required
def api_enviar():
    payload = request.get_json(silent=True) or {}
    mensagem = str(payload.get('mensagem') or '').strip()
    ids = payload.get('clientes_ids') or []

    if not mensagem:
        return jsonify({'success': False, 'error': 'Escreva a mensagem antes do envio.'}), 400

    if len(mensagem) > 2000:
        return jsonify({'success': False, 'error': 'Mensagem muito longa.'}), 400

    clientes = _clientes_selecionados(session['user_id'], ids)
    if not clientes:
        return jsonify({'success': False, 'error': 'Selecione ao menos um cliente.'}), 400

    app = current_app._get_current_object()
    usuario_id = session['user_id']
    clientes_ids = [c.id for c in clientes]
    envio_id = _criar_envio(usuario_id, len(clientes_ids))

    threading.Thread(
        target=_worker_envio,
        args=(app, usuario_id, clientes_ids, mensagem, envio_id),
        daemon=True,
    ).start()

    return jsonify({
        'success': True,
        'total': len(clientes_ids),
        'envio_id': envio_id,
        'message': 'Envio iniciado em segundo plano.'
    }), 202


@marketing.get('/api/marketing/envio/<envio_id>')
@login_required
def api_status_envio(envio_id):
    envio = _obter_envio(envio_id)

    if not envio or envio.get('usuario_id') != session['user_id']:
        return jsonify({
            'success': False,
            'error': 'Envio não encontrado.'
        }), 404

    envio.pop('usuario_id', None)
    return jsonify({
        'success': True,
        'envio': envio,
    })
