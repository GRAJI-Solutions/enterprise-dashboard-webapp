import os
import sqlite3
from flask import Flask, render_template, request, redirect, session, send_from_directory, jsonify
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import sqlexecute, login_required, level_required, httperror


app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

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
    
    if request.method == 'POST':
        registro = request.form.get('employee_register')
        senha = request.form.get('senha')

        # Aqui entra sua query SQL para buscar o usuário e a senha no banco
        # Exemplo: usuario = db.execute("SELECT * FROM usuarios WHERE registro = ?", registro)
        
        # Simulando uma validação aprovada para o exemplo
        usuario_valido = True
        nivel_chefe = True # Mudar para False se for funcionário comum
        
        if usuario_valido:
            session['usuario_id'] = registro
            session['is_chefe'] = nivel_chefe

            # Redireciona para o dashboard correto com base no cargo
            if nivel_chefe:
                return redirect('/dashboard_enterprise')
            return redirect('/dashboard')

    return render_template('login.html')


@app.route('/dashboard')
@login_required
def dashboard():
    # Rota GET padrão, aqui você faz o SELECT das horas trabalhadas, salário, etc
    return render_template('dashboard.html')


@app.route('/attendence', methods=['GET', 'POST'])
@login_required
def attendence():
    if request.method == 'POST':
        action = request.form.get('ponto_clicado')
        
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
