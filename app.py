from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "troque-esta-chave-depois"  # necessário para usar session


# ---------------------------------------------------------------------------
# USUÁRIOS DE TESTE (temporário, depois vem do banco / login)
# Para alternar a visão, acesse:
#   /?cargo=chefe        -> vê as abas Colaboradores e Corporação
#   /?cargo=funcionario  -> vê só Dashboard e Bater ponto
# O cargo escolhido fica salvo na sessão, então vale para o resto do menu.
# ---------------------------------------------------------------------------
USUARIOS_TESTE = {
    "funcionario": {"nome": "Heitor", "sobrenome": "Tomazella", "cargo": "funcionario"},
    "chefe": {"nome": "Gustavo", "sobrenome": "Rossi", "cargo": "chefe"},
}


def usuario_atual():
    cargo = request.args.get("cargo")
    if cargo in USUARIOS_TESTE:
        session["cargo"] = cargo
    return USUARIOS_TESTE[session.get("cargo", "funcionario")]


# ---------------------------------------------------------------------------
# ROTAS
# ---------------------------------------------------------------------------
@app.route("/")
@app.route("/dashboard")
def dashboard():
    return render_template("layout.html", usuario=usuario_atual(), pagina="dashboard")


@app.route("/bater-ponto")
def bater_ponto():
    return render_template("layout.html", usuario=usuario_atual(), pagina="bater_ponto")


@app.route("/colaboradores")
def colaboradores():
    usuario = usuario_atual()
    if usuario["cargo"] not in ("chefe", "rh"):
        return redirect(url_for("dashboard"))
    return render_template("layout.html", usuario=usuario, pagina="colaboradores")


@app.route("/corporacao")
def corporacao():
    usuario = usuario_atual()
    if usuario["cargo"] not in ("chefe", "rh"):
        return redirect(url_for("dashboard"))
    return render_template("layout.html", usuario=usuario, pagina="corporacao")


@app.route("/logout")
def logout():
    # Depois: redirecionar para a tela de login (url_for("login"))
    session.clear()
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)