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
            colaborador.id_colaborador AS id,
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
        collab_info = sqlexecute(
            "SELECT id_login, id_dados_profissionais FROM colaborador WHERE id_colaborador = ?;", 
            employee_id
        )
        
        if collab_info:
            
            id_login = collab_info[0]['id_login']
            id_dados_profissionais = collab_info[0]['id_dados_profissionais']  

            # Login data
            register_code = request.form.get('register_code')
            password = request.form.get('password')
            if password in ["", " "]:
                return httperror("A senha não pode ser vazia.", 400)
            access_level = int(request.form.get('access_level'))
            if access_level not in [0, 1, 2]:
                return httperror("Nível de acesso inválido.", 400)
            
            # Professional data
            role = request.form.get('role')
            contract_type = request.form.get('contract_type')
            corporative_email = request.form.get('corporative_email')
            work_shift = request.form.get('work_shift')
            weekly_workload = int(request.form.get('weekly_workload'))
            department = request.form.get('department')
            admission_date = request.form.get('admission_date')
            
            # Personal data
            cpf = request.form.get('cpf')
            full_name = request.form.get('full_name')
            gender = request.form.get('gender')
            birth_date = request.form.get('birth_date')
            
            # Contact data
            phone_number = request.form.get('phone_number')
            
            # Address data
            cep = request.form.get('cep')
            state = request.form.get('state')
            city = request.form.get('city')
            neighborhood = request.form.get('neighborhood')
            street = request.form.get('street')
            number = request.form.get('number')
            complement = request.form.get('complement')        
            
            # Salary data
            salary_value = float(request.form.get('salary_value'))
            
            try:
                sqlexecute(
                    "UPDATE login SET registro = ?, nivel_acesso = ? WHERE id_login = ?;",
                    register_code, access_level, id_login
                )
                
                sqlexecute(
                    """
                    UPDATE dados_profissionais SET 
                        cargo = ?, contrato = ?, email_corporativo = ?, 
                        turno = ?, carga_horaria_semanal_contrato = ?, 
                        departamento = ?, data_admissao = ?
                    WHERE id_dados_profissionais = ?;
                    """,
                    role, contract_type, corporative_email, work_shift, weekly_workload, department, admission_date, id_dados_profissionais
                )
                
                sqlexecute(
                    """
                    UPDATE colaborador SET 
                        cpf = ?, nome_completo = ?, genero = ?, data_nascimento = ?
                    WHERE id_colaborador = ?;
                    """,
                    cpf, full_name, gender, birth_date, employee_id
                )
                
                if salary_value:
                    sqlexecute(
                        "UPDATE historico_salarial SET valor = ? WHERE colaborador_id_colaborador = ? AND data_fim IS NULL;",
                        salary_value, employee_id
                    )
                
                sqlexecute(
                    """
                    UPDATE endereco SET 
                        cep = ?, estado = ?, cidade = ?, bairro = ?, rua = ?, numero = ?, complemento = ?
                    WHERE id_colaborador = ?;
                    """,
                    cep, state, city, neighborhood, street, number, complement, employee_id
                )
                
                sqlexecute(
                    "UPDATE contato SET numero_celular = ? WHERE id_colaborador = ?;",
                    phone_number, employee_id
                )
                
                # 4. Atualizar Escala (Estratégia: remove as escalas anteriores e insere as novas marcadas)
                sqlexecute("DELETE FROM escala WHERE id_colaborador = ?;", employee_id)
                
                dias_semana = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
                for dia in dias_semana:
                    if request.form.get(f'escala[{dia}][ativo]'):
                        sqlexecute(
                            """
                            INSERT INTO escala (
                                dia_semana, hora_entrada, inicio_intervalo, 
                                fim_intervalo, hora_saida, id_colaborador
                            ) VALUES (?, ?, ?, ?, ?, ?);
                            """,
                            dia,
                            request.form.get(f'escala[{dia}][hora_entrada]'),
                            request.form.get(f'escala[{dia}][inicio_intervalo]'),
                            request.form.get(f'escala[{dia}][fim_intervalo]'),
                            request.form.get(f'escala[{dia}][hora_saida]'),
                            employee_id
                        )
                        
            except Exception as e:
                return httperror(f"Ocorreu um erro ao atualizar os dados do colaborador", 500)
            
        return redirect(f'/employee/{employee_id}')

    employee_exists = sqlexecute("SELECT 1 FROM colaborador WHERE id_colaborador = ?", employee_id)
    if not employee_exists:
        return httperror("Colaborador não encontrado.", 404)
    
    employee_data = [
        sqlexecute(
            """
            SELECT 
                c.id_colaborador, c.cpf, c.nome_completo, c.genero, c.data_nascimento,
                l.registro, l.nivel_acesso,
                d.cargo, d.contrato, d.email_corporativo, 
                d.turno, d.carga_horaria_semanal_contrato, d.departamento, d.data_admissao,
                e.cep, e.estado, e.cidade, e.bairro, e.rua, e.numero, e.complemento,
                ct.numero_celular,
                hs.valor
            FROM colaborador c
            JOIN login l ON c.id_login = l.id_login
            JOIN dados_profissionais d ON c.id_dados_profissionais = d.id_dados_profissionais
            LEFT JOIN endereco e ON c.id_colaborador = e.id_colaborador
            LEFT JOIN contato ct ON c.id_colaborador = ct.id_colaborador
            LEFT JOIN historico_salarial hs ON c.id_colaborador = hs.colaborador_id_colaborador AND hs.data_fim IS NULL
            WHERE c.id_colaborador = ?;
            """,
            employee_id
        ),
        
        sqlexecute(
            """
            SELECT dia_semana, hora_entrada, inicio_intervalo, fim_intervalo, hora_saida 
            FROM escala 
            WHERE id_colaborador = ?;
            """,
            employee_id
        )
        ]
    
    return render_template('employee_details.html', employee_info=employee_data[0][0], employee_schedule=employee_data[1])


@app.route('/onboard_employee', methods=['GET', 'POST'])
@login_required
@level_required(1)
def onboard_employee():
    if request.method == 'POST':
        
        # From the form:
        
        # Login data
        register_code = request.form.get('register_code')
        password = generate_password_hash(request.form.get('password'))
        access_level = int(request.form.get('access_level'))
        if access_level not in [0, 1, 2]:
            return httperror("Nível de acesso inválido.", 400)
        
        # Professional data
        role = request.form.get('role')
        contract_type = request.form.get('contract_type')
        corporative_email = request.form.get('corporative_email')
        work_shift = request.form.get('work_shift')
        weekly_workload = int(request.form.get('weekly_workload'))
        department = request.form.get('department')
        admission_date = request.form.get('admission_date')
        
        # Personal data
        cpf = request.form.get('cpf')
        full_name = request.form.get('full_name')
        gender = request.form.get('gender')
        birth_date = request.form.get('birth_date')
        
        # Contact data
        phone_number = request.form.get('phone_number')
        
        # Address data
        cep = request.form.get('cep')
        state = request.form.get('state')
        city = request.form.get('city')
        neighborhood = request.form.get('neighborhood')
        street = request.form.get('street')
        number = request.form.get('number')
        complement = request.form.get('complement')        
        
        # Salary data
        salary_value = float(request.form.get('salary_value'))
        
        # Check each field for empty values and return an error if any are found
        required_fields = [
            register_code, password, access_level, role, contract_type, corporative_email,
            work_shift, weekly_workload, department, admission_date, cpf, full_name,
            gender, birth_date, phone_number, cep, state, city, neighborhood,
            street, number, salary_value
        ]
        
        if any(field is None or field == '' for field in required_fields):
            return httperror("Todos os campos obrigatórios devem ser preenchidos.", 400)
        
        # Check if at least one workday is selected
        workdays = ['segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo']
        has_selected_day = any(request.form.get(f'escala[{day}][ativo]') for day in workdays)

        if not has_selected_day:
            return httperror("Você deve selecionar pelo menos um dia de escala de trabalho.", 400)
        try:
            #Insert data into the database
            id_login = sqlexecute(
                "INSERT INTO login (registro, senha, nivel_acesso) VALUES (?, ?, ?);",
                register_code, password, access_level
            )

            id_dados_profissionais = sqlexecute(
                """
                INSERT INTO dados_profissionais (
                    cargo, contrato, email_corporativo, turno, 
                    carga_horaria_semanal_contrato, departamento, data_admissao
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                role, contract_type, corporative_email, work_shift, weekly_workload, department, admission_date
            )

            id_colaborador = sqlexecute(
                """
                INSERT INTO colaborador (
                    cpf, nome_completo, genero, data_nascimento, 
                    id_dados_profissionais, id_login
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                cpf, full_name, gender, birth_date, id_dados_profissionais, id_login
            )

            sqlexecute(
                "INSERT INTO contato (numero_celular, id_colaborador) VALUES (?, ?);",
                phone_number, id_colaborador
            )
            
            sqlexecute(
                """
                INSERT INTO endereco (
                    cep, estado, cidade, bairro, rua, numero, complemento, id_colaborador
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                cep, state, city, neighborhood, street, number, complement, id_colaborador
            )

            sqlexecute(
                """
                INSERT INTO historico_salarial (valor, data_inicio, colaborador_id_colaborador) 
                VALUES (?, date('now'), ?);
                """,
                salary_value, id_colaborador
            )

            for day in workdays:
                ativo = request.form.get(f'escala[{day}][ativo]')
                
                if ativo:
                    clock_in = request.form.get(f'escala[{day}][hora_entrada]') or None
                    break_start = request.form.get(f'escala[{day}][inicio_intervalo]') or None
                    break_end = request.form.get(f'escala[{day}][fim_intervalo]') or None
                    clock_out = request.form.get(f'escala[{day}][hora_saida]') or None
                
                # Insere a escala utilizando a sua função sqlexecute com parâmetros seguros (?)
                sqlexecute(
                    """
                    INSERT INTO escala (
                        dia_semana, hora_entrada, inicio_intervalo, 
                        fim_intervalo, hora_saida, id_colaborador
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    day, clock_in, break_start, break_end, clock_out, id_colaborador
                )
        except Exception as e:
            return httperror(f"Ocorreu um erro ao cadastrar o colaborador", 500)
                    
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
