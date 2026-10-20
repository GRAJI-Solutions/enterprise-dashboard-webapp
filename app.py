import os
import sqlite3
from flask import Flask, render_template, request, redirect, session, send_from_directory, jsonify, g
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers.helpers import sqlexecute, login_required, level_required, httperror


app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

@app.before_request
def load_employee_name():
    user_id = session.get('user_id')
    
    if user_id is None:
        g.employee_in_session_fullname = None
    else:
        full_name = sqlexecute('SELECT nome_completo FROM colaborador WHERE id_login = ?', user_id)[0]["nome_completo"].split(" ", 1)
        g.employee_in_session_fullname = {
            "name": full_name[0],
            "surname": full_name[1]
        }


@app.context_processor
def inject_employee_name():
    if request.endpoint == 'login':
        return {}
    return {'employee_in_session_fullname': g.employee_in_session_fullname }


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    session.clear()

    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("register_code"):
            return httperror("Precisa informar o número de registro", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return httperror("Precisa informar a senha", 403)

        # Query database for username
        rows = sqlexecute(
            "SELECT * FROM login WHERE registro = ?", request.form.get("register_code")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["senha"], request.form.get("password")):
            return httperror("Número de registro e/ou senha inválidos", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id_login"]
        session["access_level"] = rows[0]["nivel_acesso"]

        # Redirect user to home page
        return redirect("/dashboard")

    else:       
        return render_template("login.html")



@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')


@app.route('/attendence', methods=['GET', 'POST'])
@login_required
def attendence():
    if request.method == 'POST':
        action = request.form.get('attendence_action')
        
        return redirect('/attendence')

    return render_template('attendence.html')


@app.route('/dashboard_enterprise')
@login_required
@level_required(2)
def dashboard_enterprise():
    return render_template('dashboard_enterprise.html')


@app.route('/employees')
@login_required
@level_required(1)
def employees():
    employees_rows = sqlexecute(
        """
        SELECT 
            colaborador.nome_completo AS nome,
            (
                SELECT contato.numero_celular 
                FROM contato 
                WHERE contato.id_colaborador = colaborador.id_colaborador 
                ORDER BY contato.id_contato ASC 
                LIMIT 1
            ) AS telefone,
            dados_profissionais.email_corporativo AS email,
            dados_profissionais.turno
        FROM colaborador
        JOIN dados_profissionais ON colaborador.id_dados_profissionais = dados_profissionais.id_dados_profissionais
        """
    )
    return render_template('employees.html', employees=employees_rows)


@app.route('/employee/<employee_id>', methods=['GET', 'POST'])
@login_required
@level_required(1)
def employee_details(employee_id):
    if request.method == 'POST':
        employee_data = sqlexecute("""placeholder for SQL query to fetch employee data based on employee_id""")
        return redirect(f'/employee/{employee_id}', employee_data=employee_data)

    return render_template('employee_details.html')


@app.route('/onboard_employee', methods=['GET', 'POST'])
@login_required
@level_required(1)
def onboard_employee():
    if request.method == 'POST':
        return redirect('/employees')
    
    return render_template('onboard_employee.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect("/login")


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
    )
