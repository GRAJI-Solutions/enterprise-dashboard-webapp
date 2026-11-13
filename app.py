import math
import os
import re
import sqlite3
from datetime import date

from flask import (
    Flask,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers.dashboard_charts import (
    absences_last_five_months,
    current_average_salary,
    employees_by_department,
    hours_last_eight_weeks,
    monthly_hours_change,
)
from helpers.helpers import httperror, level_required, login_required, sqlexecute

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = os.path.join(app.root_path, "flask_session")
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



def render_employee_dashboard(employee_id, *, reviewed_employee_name=None):
    return render_template(
        'dashboard.html',
        hours_chart=hours_last_eight_weeks(employee_id),
        reviewed_employee_name=reviewed_employee_name,
    )


@app.route('/dashboard')
@login_required
def dashboard():
    employee_rows = sqlexecute(
        "SELECT id_colaborador FROM colaborador WHERE id_login = ?",
        session["user_id"],
    )

    if not employee_rows:
        return httperror("Colaborador não encontrado.", 404), 404

    return render_employee_dashboard(employee_rows[0]["id_colaborador"])


@app.route('/dashboard/employee/<int:employee_id>')
@login_required
@level_required(1)
def employee_dashboard(employee_id):
    employee_rows = sqlexecute(
        "SELECT nome_completo FROM colaborador WHERE id_colaborador = ?",
        employee_id,
    )
    if not employee_rows:
        return httperror("Colaborador não encontrado.", 404), 404

    return render_employee_dashboard(
        employee_id,
        reviewed_employee_name=employee_rows[0]["nome_completo"],
    )


@app.route('/attendence', methods=['GET', 'POST'])
@login_required
def attendance():
    if request.method == 'POST':
        action = request.form.get('attendence_action')
        
        return redirect('/attendence')

    return render_template('attendence.html')


@app.route('/dashboard_enterprise')
@login_required
@level_required(2)
def dashboard_enterprise():
    absences_chart = absences_last_five_months()
    departments = employees_by_department()
    performance = monthly_hours_change()
    average_salary = current_average_salary()
    total_employees = sum(department["total"] for department in departments)

    return render_template(
        'dashboard_enterprise.html',
        absences_chart=absences_chart,
        departments=departments,
        performance=performance,
        average_salary=average_salary,
        total_employees=total_employees,
    )


@app.route('/employees')
@login_required
@level_required(1)
def employees():
    employees_rows = sqlexecute(
        """
        SELECT 
            colaborador.id_colaborador AS id,
            colaborador.nome_completo AS name,
            (
                SELECT contato.numero_celular 
                FROM contato 
                WHERE contato.id_colaborador = colaborador.id_colaborador 
                ORDER BY contato.id_contato ASC 
                LIMIT 1
            ) AS phone_number,
            dados_profissionais.email_corporativo AS email,
            dados_profissionais.turno AS work_shift
        FROM colaborador
        JOIN dados_profissionais ON colaborador.id_dados_profissionais = dados_profissionais.id_dados_profissionais
        """
    )
    
    return render_template('employees.html', employees=employees_rows)


EMPLOYEE_QUERY = """
    SELECT
        c.id_colaborador, c.cpf, c.nome_completo, c.genero, c.data_nascimento,
        c.id_login, c.id_dados_profissionais, l.registro, l.nivel_acesso,
        d.cargo, d.contrato, d.email_corporativo, d.turno,
        d.carga_horaria_semanal_contrato, d.departamento, d.data_admissao,
        e.id_endereco, e.cep, e.estado, e.cidade, e.bairro, e.rua,
        e.numero, e.complemento, ct.id_contato, ct.numero_celular,
        hs.id_historico_salarial, hs.valor
    FROM colaborador c
    JOIN login l ON c.id_login = l.id_login
    JOIN dados_profissionais d ON c.id_dados_profissionais = d.id_dados_profissionais
    LEFT JOIN endereco e ON e.id_endereco = (
        SELECT id_endereco FROM endereco WHERE id_colaborador = c.id_colaborador
        ORDER BY id_endereco LIMIT 1
    )
    LEFT JOIN contato ct ON ct.id_contato = (
        SELECT id_contato FROM contato WHERE id_colaborador = c.id_colaborador
        ORDER BY id_contato LIMIT 1
    )
    LEFT JOIN historico_salarial hs ON hs.id_historico_salarial = (
        SELECT id_historico_salarial FROM historico_salarial
        WHERE colaborador_id_colaborador = c.id_colaborador AND data_fim IS NULL
        ORDER BY data_inicio DESC, id_historico_salarial DESC LIMIT 1
    )
    WHERE c.id_colaborador = ?
"""


@app.route('/employee/<employee_id>', methods=['GET', 'POST'])
@login_required
@level_required(1)
def employee_details(employee_id):
    employee_rows = sqlexecute(EMPLOYEE_QUERY, employee_id)
    if not employee_rows:
        return httperror("Colaborador não encontrado.", 404), 404
    employee = employee_rows[0]

    if request.method == 'GET':
        employee_schedule = sqlexecute(
            """
            SELECT dia_semana, hora_entrada, inicio_intervalo, fim_intervalo, hora_saida
            FROM escala WHERE id_colaborador = ? ORDER BY id_escala;
            """,
            employee_id
        )
        return render_template('employee_details.html', employee_info=employee, employee_schedule=employee_schedule)

    login_id = employee['id_login']
    professional_details_id = employee['id_dados_profissionais']

    register_code = (request.form.get('register_code') or '').strip()
    if not register_code:
        return httperror("A matrícula é obrigatória.", 400), 400
    if sqlexecute("SELECT 1 FROM login WHERE registro = ? AND id_login <> ?;", register_code, login_id):
        return httperror("Matrícula já cadastrada.", 409), 409

    access_level = (request.form.get('access_level') or '').strip()
    try:
        access_level = int(access_level)
    except ValueError:
        return httperror("O nível de acesso deve ser um número inteiro.", 400), 400
    if access_level not in (0, 1, 2):
        return httperror("Nível de acesso inválido. Informe 0, 1 ou 2.", 400), 400

    role = (request.form.get('role') or '').strip()
    if not role:
        return httperror("O cargo é obrigatório.", 400), 400

    contract_type = (request.form.get('contract_type') or '').strip()
    if not contract_type:
        return httperror("O tipo de contrato é obrigatório.", 400), 400

    corporative_email = (request.form.get('corporative_email') or '').strip()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', corporative_email):
        return httperror("Informe um e-mail corporativo válido.", 400), 400
    if sqlexecute(
        "SELECT 1 FROM dados_profissionais WHERE email_corporativo = ? AND id_dados_profissionais <> ?;",
        corporative_email, professional_details_id
    ):
        return httperror("E-mail corporativo já cadastrado.", 409), 409

    work_shift = (request.form.get('work_shift') or '').strip()
    if work_shift not in ('Manhã', 'Tarde', 'Noite', 'Integral'):
        return httperror("Turno inválido.", 400), 400

    weekly_workload = (request.form.get('weekly_workload') or '').strip()
    try:
        weekly_workload = int(weekly_workload)
    except ValueError:
        return httperror("A carga horária semanal deve ser um número inteiro.", 400), 400
    if not 1 <= weekly_workload <= 44:
        return httperror("A carga horária semanal deve estar entre 1 e 44 horas.", 400), 400

    department = (request.form.get('department') or '').strip()
    if not department:
        return httperror("O departamento é obrigatório.", 400), 400

    admission_date = (request.form.get('admission_date') or '').strip()
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', admission_date):
        return httperror("Informe a data de admissão no formato AAAA-MM-DD.", 400), 400
    try:
        date.fromisoformat(admission_date)
    except ValueError:
        return httperror("A data de admissão é inválida.", 400), 400

    taxpayer_id = (request.form.get('cpf') or '').strip()
    if not re.fullmatch(r'[0-9]{11}', taxpayer_id):
        return httperror("O CPF deve conter 11 dígitos, sem pontuação.", 400), 400
    if sqlexecute("SELECT 1 FROM colaborador WHERE cpf = ? AND id_colaborador <> ?;", taxpayer_id, employee_id):
        return httperror("CPF já cadastrado.", 409), 409

    full_name = (request.form.get('full_name') or '').strip()
    if not full_name:
        return httperror("O nome completo é obrigatório.", 400), 400

    gender = (request.form.get('gender') or '').strip()
    if gender not in ('M', 'F', 'Outro'):
        return httperror("Gênero inválido. Informe M, F ou Outro.", 400), 400

    birth_date = (request.form.get('birth_date') or '').strip()
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', birth_date):
        return httperror("Informe a data de nascimento no formato AAAA-MM-DD.", 400), 400
    try:
        date.fromisoformat(birth_date)
    except ValueError:
        return httperror("A data de nascimento é inválida.", 400), 400

    phone_number = (request.form.get('phone_number') or '').strip()
    if not re.fullmatch(r'[0-9]{11}', phone_number):
        return httperror("O telefone deve conter 11 dígitos, incluindo o DDD e sem pontuação.", 400), 400
    if sqlexecute(
        """
        SELECT 1 FROM contato WHERE id_colaborador = ? AND numero_celular = ?
            AND (? IS NULL OR id_contato <> ?);
        """,
        employee_id, phone_number, employee['id_contato'], employee['id_contato']
    ):
        return httperror("Este telefone já existe em outro contato do colaborador.", 409), 409

    postal_code = (request.form.get('cep') or '').strip()
    if not re.fullmatch(r'[0-9]{8}', postal_code):
        return httperror("O CEP deve conter 8 dígitos, sem pontuação.", 400), 400

    state = (request.form.get('state') or '').strip().upper()
    if state not in (
        'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG',
        'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
    ):
        return httperror("Informe uma UF brasileira válida com duas letras.", 400), 400

    city = (request.form.get('city') or '').strip()
    if not city:
        return httperror("A cidade é obrigatória.", 400), 400

    neighborhood = (request.form.get('neighborhood') or '').strip()
    if not neighborhood:
        return httperror("O bairro é obrigatório.", 400), 400

    street = (request.form.get('street') or '').strip()
    if not street:
        return httperror("O endereço é obrigatório.", 400), 400

    number = (request.form.get('number') or '').strip()
    if not number:
        return httperror("O número do imóvel é obrigatório.", 400), 400

    complement = (request.form.get('complement') or '').strip() or None

    salary_value = (request.form.get('salary_value') or '').strip()
    try:
        salary_value = float(salary_value)
    except ValueError:
        return httperror("O salário deve ser um número válido. Use ponto para os centavos.", 400), 400
    if not math.isfinite(salary_value) or salary_value <= 0:
        return httperror("O salário deve ser um número finito maior que zero.", 400), 400

    # Validate the full schedule before writing any records.
    # Form keys are in English; weekday values are stored in Portuguese.
    workdays = (
        ('monday', 'Segunda'), ('tuesday', 'Terça'), ('wednesday', 'Quarta'),
        ('thursday', 'Quinta'), ('friday', 'Sexta'), ('saturday', 'Sábado'), ('sunday', 'Domingo')
    )
    schedule = []
    for day, database_day in workdays:
        active = request.form.get(f'schedule[{day}][active]')
        if active not in (None, '', 'on'):
            return httperror(f"Seleção de dia inválida: {database_day}.", 400), 400

        if active != 'on':
            continue

        clock_in = (request.form.get(f'schedule[{day}][clock_in]') or '').strip()
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', clock_in):
            return httperror(f"Informe a entrada de {database_day} no formato HH:MM, de 00:00 a 23:59.", 400), 400

        break_start = (request.form.get(f'schedule[{day}][break_start]') or '').strip() or None
        if break_start and not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', break_start):
            return httperror(f"Início do intervalo inválido para {database_day}. Use HH:MM.", 400), 400

        break_end = (request.form.get(f'schedule[{day}][break_end]') or '').strip() or None
        if break_end and not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', break_end):
            return httperror(f"Fim do intervalo inválido para {database_day}. Use HH:MM.", 400), 400
        if (break_start is None) != (break_end is None):
            return httperror(f"Informe o início e o fim do intervalo para {database_day}, ou deixe os dois vazios.", 400), 400

        clock_out = (request.form.get(f'schedule[{day}][clock_out]') or '').strip()
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', clock_out):
            return httperror(f"Informe a saída de {database_day} no formato HH:MM, de 00:00 a 23:59.", 400), 400

        schedule.append((database_day, clock_in, break_start, break_end, clock_out))

    try:
        sqlexecute(
            "UPDATE login SET registro = ?, nivel_acesso = ? WHERE id_login = ?;",
            register_code, access_level, login_id
        )
        sqlexecute(
            """
            UPDATE dados_profissionais SET cargo = ?, contrato = ?, email_corporativo = ?,
                turno = ?, carga_horaria_semanal_contrato = ?, departamento = ?, data_admissao = ?
            WHERE id_dados_profissionais = ?;
            """,
            role, contract_type, corporative_email, work_shift, weekly_workload,
            department, admission_date, professional_details_id
        )
        sqlexecute(
            "UPDATE colaborador SET cpf = ?, nome_completo = ?, genero = ?, data_nascimento = ? WHERE id_colaborador = ?;",
            taxpayer_id, full_name, gender, birth_date, employee_id
        )
        if employee['id_endereco'] is not None:
            sqlexecute(
                """
                UPDATE endereco SET cep = ?, estado = ?, cidade = ?, bairro = ?,
                    rua = ?, numero = ?, complemento = ? WHERE id_endereco = ?;
                """,
                postal_code, state, city, neighborhood, street, number, complement, employee['id_endereco']
            )
        else:
            sqlexecute(
                """
                INSERT INTO endereco (cep, estado, cidade, bairro, rua, numero, complemento, id_colaborador)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                postal_code, state, city, neighborhood, street, number, complement, employee_id
            )
        if employee['id_contato'] is not None:
            sqlexecute(
                "UPDATE contato SET numero_celular = ? WHERE id_contato = ?;",
                phone_number, employee['id_contato']
            )
        else:
            sqlexecute(
                "INSERT INTO contato (numero_celular, id_colaborador) VALUES (?, ?);",
                phone_number, employee_id
            )
        if employee['id_historico_salarial'] is not None:
            sqlexecute(
                "UPDATE historico_salarial SET valor = ? WHERE id_historico_salarial = ?;",
                salary_value, employee['id_historico_salarial']
            )
        else:
            sqlexecute(
                "INSERT INTO historico_salarial (valor, data_inicio, colaborador_id_colaborador) VALUES (?, ?, ?);",
                salary_value, admission_date, employee_id
            )
        sqlexecute("DELETE FROM escala WHERE id_colaborador = ?;", employee_id)
        for database_day, clock_in, break_start, break_end, clock_out in schedule:
            sqlexecute(
                """
                INSERT INTO escala (dia_semana, hora_entrada, inicio_intervalo, fim_intervalo, hora_saida, id_colaborador)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                database_day, clock_in, break_start, break_end, clock_out, employee_id
            )
    except sqlite3.IntegrityError:
        return httperror("Os dados conflitam com um cadastro existente ou com as regras do banco.", 409), 409
    except sqlite3.DatabaseError:
        app.logger.exception("Erro ao atualizar colaborador")
        return httperror("Ocorreu um erro ao atualizar os dados do colaborador.", 500), 500

    return redirect(url_for('employee_details', employee_id=employee_id))


@app.route('/onboard_employee', methods=['GET', 'POST'])
@login_required
@level_required(1)
def onboard_employee():
    if request.method == 'GET':
        return render_template('onboard_employee.html')

    register_code = (request.form.get('register_code') or '').strip()
    if not register_code:
        return httperror("A matrícula é obrigatória.", 400), 400
    if sqlexecute("SELECT 1 FROM login WHERE registro = ?;", register_code):
        return httperror("Matrícula já cadastrada.", 409), 409

    password = request.form.get('password') or ''
    if not password.strip():
        return httperror("A senha provisória é obrigatória.", 400), 400
    if len(password) < 8:
        return httperror("A senha provisória deve ter pelo menos 8 caracteres.", 400), 400

    access_level = (request.form.get('access_level') or '').strip()
    try:
        access_level = int(access_level)
    except ValueError:
        return httperror("O nível de acesso deve ser um número inteiro.", 400), 400
    if access_level not in (0, 1, 2):
        return httperror("Nível de acesso inválido. Informe 0, 1 ou 2.", 400), 400

    role = (request.form.get('role') or '').strip()
    if not role:
        return httperror("O cargo é obrigatório.", 400), 400

    contract_type = (request.form.get('contract_type') or '').strip()
    if not contract_type:
        return httperror("O tipo de contrato é obrigatório.", 400), 400

    corporative_email = (request.form.get('corporative_email') or '').strip()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', corporative_email):
        return httperror("Informe um e-mail corporativo válido.", 400), 400
    if sqlexecute("SELECT 1 FROM dados_profissionais WHERE email_corporativo = ?;", corporative_email):
        return httperror("E-mail corporativo já cadastrado.", 409), 409

    work_shift = (request.form.get('work_shift') or '').strip()
    if work_shift not in ('Manhã', 'Tarde', 'Noite', 'Integral'):
        return httperror("Turno inválido.", 400), 400

    weekly_workload = (request.form.get('weekly_workload') or '').strip()
    try:
        weekly_workload = int(weekly_workload)
    except ValueError:
        return httperror("A carga horária semanal deve ser um número inteiro.", 400), 400
    if not 1 <= weekly_workload <= 44:
        return httperror("A carga horária semanal deve estar entre 1 e 44 horas.", 400), 400

    department = (request.form.get('department') or '').strip()
    if not department:
        return httperror("O departamento é obrigatório.", 400), 400

    admission_date = (request.form.get('admission_date') or '').strip()
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', admission_date):
        return httperror("Informe a data de admissão no formato AAAA-MM-DD.", 400), 400
    try:
        date.fromisoformat(admission_date)
    except ValueError:
        return httperror("A data de admissão é inválida.", 400), 400

    taxpayer_id = (request.form.get('cpf') or '').strip()
    if not re.fullmatch(r'[0-9]{11}', taxpayer_id):
        return httperror("O CPF deve conter 11 dígitos, sem pontuação.", 400), 400
    if sqlexecute("SELECT 1 FROM colaborador WHERE cpf = ?;", taxpayer_id):
        return httperror("CPF já cadastrado.", 409), 409

    full_name = (request.form.get('full_name') or '').strip()
    if not full_name:
        return httperror("O nome completo é obrigatório.", 400), 400

    gender = (request.form.get('gender') or '').strip()
    if gender not in ('M', 'F', 'Outro'):
        return httperror("Gênero inválido. Informe M, F ou Outro.", 400), 400

    birth_date = (request.form.get('birth_date') or '').strip()
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', birth_date):
        return httperror("Informe a data de nascimento no formato AAAA-MM-DD.", 400), 400
    try:
        date.fromisoformat(birth_date)
    except ValueError:
        return httperror("A data de nascimento é inválida.", 400), 400

    phone_number = (request.form.get('phone_number') or '').strip()
    if not re.fullmatch(r'[0-9]{11}', phone_number):
        return httperror("O telefone deve conter 11 dígitos, incluindo o DDD e sem pontuação.", 400), 400

    postal_code = (request.form.get('cep') or '').strip()
    if not re.fullmatch(r'[0-9]{8}', postal_code):
        return httperror("O CEP deve conter 8 dígitos, sem pontuação.", 400), 400

    state = (request.form.get('state') or '').strip().upper()
    if state not in (
        'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG',
        'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
    ):
        return httperror("Informe uma UF brasileira válida com duas letras.", 400), 400

    city = (request.form.get('city') or '').strip()
    if not city:
        return httperror("A cidade é obrigatória.", 400), 400

    neighborhood = (request.form.get('neighborhood') or '').strip()
    if not neighborhood:
        return httperror("O bairro é obrigatório.", 400), 400

    street = (request.form.get('street') or '').strip()
    if not street:
        return httperror("O endereço é obrigatório.", 400), 400

    number = (request.form.get('number') or '').strip()
    if not number:
        return httperror("O número do imóvel é obrigatório.", 400), 400

    complement = (request.form.get('complement') or '').strip() or None

    salary_value = (request.form.get('salary_value') or '').strip()
    try:
        salary_value = float(salary_value)
    except ValueError:
        return httperror("O salário deve ser um número válido. Use ponto para os centavos.", 400), 400
    if not math.isfinite(salary_value) or salary_value <= 0:
        return httperror("O salário deve ser um número finito maior que zero.", 400), 400

    # Validate the full schedule before writing any records.
    # Form keys are in English; weekday values are stored in Portuguese.
    workdays = (
        ('monday', 'Segunda'), ('tuesday', 'Terça'), ('wednesday', 'Quarta'),
        ('thursday', 'Quinta'), ('friday', 'Sexta'), ('saturday', 'Sábado'), ('sunday', 'Domingo')
    )
    schedule = []
    for day, database_day in workdays:
        active = request.form.get(f'schedule[{day}][active]')
        if active not in (None, '', 'on'):
            return httperror(f"Seleção de dia inválida: {database_day}.", 400), 400

        if active != 'on':
            continue

        clock_in = (request.form.get(f'schedule[{day}][clock_in]') or '').strip()
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', clock_in):
            return httperror(f"Informe a entrada de {database_day} no formato HH:MM, de 00:00 a 23:59.", 400), 400

        break_start = (request.form.get(f'schedule[{day}][break_start]') or '').strip() or None
        if break_start and not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', break_start):
            return httperror(f"Início do intervalo inválido para {database_day}. Use HH:MM.", 400), 400

        break_end = (request.form.get(f'schedule[{day}][break_end]') or '').strip() or None
        if break_end and not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', break_end):
            return httperror(f"Fim do intervalo inválido para {database_day}. Use HH:MM.", 400), 400
        if (break_start is None) != (break_end is None):
            return httperror(f"Informe o início e o fim do intervalo para {database_day}, ou deixe os dois vazios.", 400), 400

        clock_out = (request.form.get(f'schedule[{day}][clock_out]') or '').strip()
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', clock_out):
            return httperror(f"Informe a saída de {database_day} no formato HH:MM, de 00:00 a 23:59.", 400), 400

        schedule.append((database_day, clock_in, break_start, break_end, clock_out))

    if not schedule:
        return httperror("Você deve selecionar pelo menos um dia de escala de trabalho.", 400), 400

    # Keep using the existing sqlexecute calls for individual writes.
    # All fields have been validated before the first INSERT.
    password = generate_password_hash(password)
    try:
        login_id = sqlexecute(
            "INSERT INTO login (registro, senha, nivel_acesso) VALUES (?, ?, ?);",
            register_code, password, access_level
        )
        professional_details_id = sqlexecute(
            """
            INSERT INTO dados_profissionais (
                cargo, contrato, email_corporativo, turno,
                carga_horaria_semanal_contrato, departamento, data_admissao
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            role, contract_type, corporative_email, work_shift, weekly_workload, department, admission_date
        )
        employee_id = sqlexecute(
            """
            INSERT INTO colaborador (cpf, nome_completo, genero, data_nascimento, id_dados_profissionais, id_login)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            taxpayer_id, full_name, gender, birth_date, professional_details_id, login_id
        )
        sqlexecute(
            "INSERT INTO contato (numero_celular, id_colaborador) VALUES (?, ?);",
            phone_number, employee_id
        )
        sqlexecute(
            """
            INSERT INTO endereco (cep, estado, cidade, bairro, rua, numero, complemento, id_colaborador)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            postal_code, state, city, neighborhood, street, number, complement, employee_id
        )
        sqlexecute(
            "INSERT INTO historico_salarial (valor, data_inicio, colaborador_id_colaborador) VALUES (?, ?, ?);",
            salary_value, admission_date, employee_id
        )
        for database_day, clock_in, break_start, break_end, clock_out in schedule:
            sqlexecute(
                """
                INSERT INTO escala (dia_semana, hora_entrada, inicio_intervalo, fim_intervalo, hora_saida, id_colaborador)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                database_day, clock_in, break_start, break_end, clock_out, employee_id
            )
    except sqlite3.IntegrityError:
        return httperror("Os dados conflitam com um cadastro existente ou com as regras do banco.", 409), 409
    except sqlite3.DatabaseError:
        app.logger.exception("Erro ao cadastrar colaborador")
        return httperror("Ocorreu um erro ao cadastrar o colaborador.", 500), 500

    return redirect(url_for('employees'))


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
