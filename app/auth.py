from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from .models import db, Usuario
from .themes import normalizar_tema

auth = Blueprint("auth", __name__)

@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = Usuario.query.filter_by(
            username=request.form["username"]
        ).first()

        if user and user.check_password(request.form["password"]):
            session["user_id"] = user.id
            session["username"] = user.username
            session["tema"] = normalizar_tema(user.tema)

            current_app.logger.info(f"Login realizado: {user.username}")

            # 🔥 DEBUG (TEMPORÁRIO)
            print("IS MASTER:", user.is_masteradm)

            # 🔥 REDIRECIONAMENTO CORRETO
            if user.is_masteradm:
                return redirect(url_for("main.masteradm"))

            return redirect(url_for("main.painel"))

        flash("Usuário ou senha inválidos")
        current_app.logger.warning(f"Falha de login para: {request.form['username']}")

    return render_template("login.html")


@auth.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]

        if Usuario.query.filter_by(username=username).first():
            flash("Usuário já existe")

            # 🔥 LOG USUÁRIO DUPLICADO
            current_app.logger.warning(f"Tentativa de cadastro duplicado: {username}")

            return redirect(url_for("auth.register"))

        # 🔹 slug automático
        slug = username.lower().strip().replace(" ", "-")

        user = Usuario(
            username=username,
            slug=slug,

            # 🔥 NOVOS CAMPOS
            nome=request.form.get("nome"),
            email=request.form.get("email"),
            telefone=request.form.get("telefone"),
            cpf=request.form.get("cpf"),
            empresa=request.form.get("empresa"),
            plano=request.form.get("plano"),
            status=request.form.get("status"),
            obs=request.form.get("obs"),
        )

        user.set_password(request.form["password"])

        db.session.add(user)
        db.session.commit()

        # 🔥 LOG CRIAÇÃO
        current_app.logger.info(
            f"Novo usuário criado: {username} | Plano: {request.form.get('plano')}"
        )

        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth.route("/logout")
def logout():
    username = session.get("username")

    session.clear()

    # 🔥 LOG LOGOUT
    if username:
        current_app.logger.info(f"Logout realizado: {username}")

    return redirect(url_for("auth.login"))

@auth.route('/criar-masteradm', methods=['GET', 'POST'])
def criar_masteradm():
    from flask import request, render_template, redirect, flash
    from app import db
    from app.models import Usuario
    from config import MASTERADM_KEY

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        chave = request.form.get('chave')

        if not all([username, password, chave]):
            flash("Preencha todos os campos")
            return redirect(request.url)

        # 🔒 valida chave
        if chave != MASTERADM_KEY:
            flash("Chave inválida")
            return redirect(request.url)

        # 🔒 evita duplicado
        if Usuario.query.filter_by(username=username).first():
            flash("Usuário já existe")
            return redirect(request.url)

        slug = username.lower().replace(" ", "-")

        novo = Usuario(
            username=username,
            slug=slug,
            is_masteradm=True
        )

        novo.set_password(password)

        db.session.add(novo)
        db.session.commit()

        flash("MasterADM criado com sucesso!")
        return redirect('/login')

    return render_template('criar_masteradm.html')
