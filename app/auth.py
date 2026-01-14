from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from .models import db, Usuario

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
            return redirect(url_for("main.painel"))

        flash("Usuário ou senha inválidos")

    return render_template("login.html")


@auth.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]

        if Usuario.query.filter_by(username=username).first():
            flash("Usuário já existe")
            return redirect(url_for("auth.register"))

        # 🔹 slug automático
        slug = username.lower().strip().replace(" ", "-")

        user = Usuario(
            username=username,
            slug=slug
        )
        user.set_password(request.form["password"])

        db.session.add(user)
        db.session.commit()

        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
