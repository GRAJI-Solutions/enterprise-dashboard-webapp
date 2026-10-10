import os
import sqlite3
from flask import Flask, render_template, request, redirect, session, send_from_directory, jsonify
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import sqlexecute, login_required, level_1_required, level_2_required, httperror


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
        # Pega a ação do botão que foi clicado
        acao = request.form.get('ponto_clicado')
        
        return redirect('/bater_ponto')

    return render_template('work.html')


@app.route('/dashboard_enterprise')
@login_required
@level_2_required
def dashboard_enterprise():
    return render_template('dashboard_enterprise.html')


@app.route('/employees')
@login_required
@level_1_required
def employees():
    # SELECT geral no banco para montar a tabela da equipe
    return render_template('employees.html')


@app.route('/employee/<employee_register>', methods=['GET', 'POST'])
@login_required
@level_1_required
def employee_details(employee_register):
    if request.method == 'POST':
        # Aqui você puxa os dados do formulário quando o chefe alterar algo e clicar em salvar
        novo_cargo = request.form.get('cargo')
        nova_escala = request.form.get('escala')
        novo_salario = request.form.get('salario')
        
        # Comando SQL para atualizar as informacoes daquela pessoa especifica no banco
        # db.execute("UPDATE colaboradores SET cargo = ?, escala = ?, salario = ? WHERE registro = ?", novo_cargo, nova_escala, novo_salario, employee_register)
                
        # Recarrega a pagina para mostrar os dados novos
        return redirect('/employee/employee_register', employee_register=employee_register)
        
    # Se a requisicao for GET, o sistema busca todos os dados no banco para preencher a tela
    # informacoes = db.execute("SELECT * FROM colaboradores WHERE registro = ?", employee_register)
    
    # Aqui voce manda as informacoes do banco de dados direto para o seu template HTML
    return render_template('detalhes_colaborador.html', id_funcionario=employee_register)


@app.route('/onboard_employee', methods=['GET', 'POST'])
@login_required
@level_1_required
def cadastrar_colaborador():
    if request.method == 'POST':
        nome = request.form.get('nome_completo')
        cpf = request.form.get('cpf')
        cargo = request.form.get('cargo')
                
        return redirect('/employees')

    return render_template('onboard_employee.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect("/")


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
    )
