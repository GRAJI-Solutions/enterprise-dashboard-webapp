import math
import os
import re
import secrets
import sqlite3
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from threading import Lock, Thread
from time import sleep
from zoneinfo import ZoneInfo

from helpers.dashboard_charts import (
    absences_last_five_months,
    current_average_salary,
    employees_by_department,
    hours_last_eight_weeks,
    monthly_hours_change,
)
from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from flask_session import Session
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



def current_viewer():
    """Colaborador logado e o nível de acesso atual (lido do banco, não da sessão)."""
    rows = sqlexecute(
        '''
        SELECT c.id_colaborador AS id, l.nivel_acesso AS level
        FROM colaborador c
        JOIN login l ON l.id_login = c.id_login
        WHERE l.id_login = ?
        ''',
        session["user_id"],
    )
    return rows[0] if rows else None


def dashboard_profile_options(viewer):
    """Colaboradores que o usuário logado pode abrir no dashboard.
    Nível 2 (chefe): todos. Nível 1 (RH): só nível 0. Nível 0: ninguém."""
    if viewer["level"] < 1:
        return []

    query = '''
        SELECT c.id_colaborador AS id, c.nome_completo AS name, l.nivel_acesso AS level
        FROM colaborador c
        JOIN login l ON l.id_login = c.id_login
        WHERE c.id_colaborador <> ?
    '''
    if viewer["level"] < 2:
        query += " AND l.nivel_acesso = 0"
    return sqlexecute(query + " ORDER BY c.nome_completo", viewer["id"])


def render_employee_dashboard(employee_id, viewer, *, reviewed_employee_name=None):
    now = attendance_now()
    today = now.date().isoformat()
    salary_rows = sqlexecute(
        '''
        SELECT valor FROM historico_salarial
        WHERE colaborador_id_colaborador = ? AND data_inicio <= ?
            AND (data_fim IS NULL OR data_fim >= ?)
        ORDER BY data_inicio DESC, id_historico_salarial DESC LIMIT 1
        ''',
        employee_id, today, today,
    )
    salary = None
    if salary_rows:
        salary = f"{salary_rows[0]['valor']:,.2f}".translate(str.maketrans(',.', '.,'))

    return render_template(
        'dashboard.html',
        hours_chart=hours_last_eight_weeks(employee_id),
        reviewed_employee_name=reviewed_employee_name,
        profile_options=dashboard_profile_options(viewer),
        selected_employee_id=employee_id,
        salary=salary,
        **employee_dashboard_metrics(employee_id, now),
    )


@app.route('/dashboard')
@login_required
def dashboard():
    viewer = current_viewer()
    if not viewer:
        return httperror("Colaborador não encontrado.", 404), 404

    return render_employee_dashboard(viewer["id"], viewer)


@app.route('/dashboard/employee/<int:employee_id>')
@login_required
@level_required(1)
def employee_dashboard(employee_id):
    viewer = current_viewer()
    if not viewer:
        return httperror("Colaborador não encontrado.", 404), 404

    if employee_id == viewer["id"]:
        return redirect(url_for('dashboard'))

    target_rows = sqlexecute(
        '''
        SELECT c.nome_completo, l.nivel_acesso
        FROM colaborador c
        JOIN login l ON l.id_login = c.id_login
        WHERE c.id_colaborador = ?
        ''',
        employee_id,
    )
    if not target_rows:
        return httperror("Colaborador não encontrado.", 404), 404
    target = target_rows[0]

    if viewer["level"] < 2 and target["nivel_acesso"] != 0:
        return httperror("Você não tem permissão para ver este dashboard.", 403), 403

    return render_employee_dashboard(
        employee_id,
        viewer,
        reviewed_employee_name=target["nome_completo"],
    )


ATTENDANCE_TIMEZONE = ZoneInfo('America/Sao_Paulo')
ATTENDANCE_WEEKDAYS = ('Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo')
ATTENDANCE_STEPS = (
    ('clock_in', 'hora_entrada', 'Entrada'),
    ('break_start', 'inicio_intervalo', 'Início do intervalo'),
    ('break_end', 'fim_intervalo', 'Fim do intervalo'),
    ('clock_out', 'hora_saida', 'Saída'),
)
attendance_closer_lock = Lock()
attendance_closer_thread = None


def attendance_now():
    return datetime.now(ATTENDANCE_TIMEZONE)


def clock_minutes(value):
    return int(value[:2]) * 60 + int(value[3:5])


def minutes_since_clock_in(value, clock_in):
    # A smaller clock value belongs to the following day of the same shift.
    return (clock_minutes(value) - clock_minutes(clock_in)) % (24 * 60)


def close_expired_attendance(now, *, employee_id=None):
    """Close unfinished shifts at their scheduled end without creating rows."""
    # Use the schedule for the date of the original clock-in, not today's schedule.
    open_entries = sqlexecute(
        '''
        SELECT p.id_ponto, p.data, p.hora_entrada, p.inicio_intervalo, p.fim_intervalo,
               e.hora_entrada AS scheduled_start, e.hora_saida AS scheduled_end
        FROM ponto p
        JOIN escala e ON e.id_colaborador = p.id_colaborador
            AND e.dia_semana = CASE strftime('%w', p.data)
                WHEN '0' THEN 'Domingo' WHEN '1' THEN 'Segunda'
                WHEN '2' THEN 'Terça' WHEN '3' THEN 'Quarta'
                WHEN '4' THEN 'Quinta' WHEN '5' THEN 'Sexta' WHEN '6' THEN 'Sábado'
            END
        WHERE p.data < ? AND p.hora_entrada IS NOT NULL AND p.hora_saida IS NULL
            AND e.hora_entrada IS NOT NULL AND e.hora_saida IS NOT NULL
            AND (? IS NULL OR p.id_colaborador = ?)
        ''',
        now.date().isoformat(), employee_id, employee_id,
    )

    for entry in open_entries:
        work_date = date.fromisoformat(entry['data'])
        midnight = datetime.combine(work_date + timedelta(days=1), time.min, ATTENDANCE_TIMEZONE)
        scheduled_end = datetime.combine(
            work_date, time.fromisoformat(entry['scheduled_end']), ATTENDANCE_TIMEZONE,
        )
        if entry['scheduled_end'] < entry['scheduled_start']:
            scheduled_end += timedelta(days=1)

        # A night shift may still be in progress at midnight.
        if now < max(midnight, scheduled_end):
            continue

        clock_in = entry['hora_entrada']
        clock_in_at = datetime.combine(work_date, time.fromisoformat(clock_in), ATTENDANCE_TIMEZONE)
        scheduled_minutes = (scheduled_end - clock_in_at).total_seconds() / 60
        # Never backdate a clock-out before a punch or close a shift the schema cannot represent.
        if not 0 <= scheduled_minutes < 1440 or any(
            entry[column] and minutes_since_clock_in(entry[column], clock_in) > scheduled_minutes
            for column in ('inicio_intervalo', 'fim_intervalo')
        ):
            continue

        # Check the original punches so concurrent workers cannot overwrite a manual clock-out.
        sqlexecute(
            '''
            UPDATE ponto SET hora_saida = ? WHERE id_ponto = ? AND hora_saida IS NULL
                AND hora_entrada IS ? AND inicio_intervalo IS ? AND fim_intervalo IS ?
            ''',
            entry['scheduled_end'], entry['id_ponto'], clock_in,
            entry['inicio_intervalo'], entry['fim_intervalo'],
        )


def run_attendance_closer():
    while True:
        try:
            close_expired_attendance(attendance_now())
        except sqlite3.DatabaseError:
            app.logger.exception('Failed to close expired attendance entries')

        # Run again at the next minute boundary, including local midnight.
        now = attendance_now()
        sleep(60 - now.second - now.microsecond / 1_000_000)


@app.before_request
def start_attendance_closer():
    global attendance_closer_thread
    if app.testing or attendance_closer_thread is not None:
        return

    # Start once per serving process, not at import time or in the Flask reloader parent.
    with attendance_closer_lock:
        if attendance_closer_thread is None:
            attendance_closer_thread = Thread(target=run_attendance_closer, daemon=True)
            attendance_closer_thread.start()


def attendance_worked_minutes(entry, elapsed=None):
    clock_in = entry.get('hora_entrada')
    if not clock_in:
        return None

    clock_out = entry.get('hora_saida')
    end = minutes_since_clock_in(clock_out, clock_in) if clock_out else elapsed
    if end is None:
        return None

    break_start = entry.get('inicio_intervalo')
    break_end = entry.get('fim_intervalo')
    if not break_start:
        return end if not break_end else None

    start = minutes_since_clock_in(break_start, clock_in)
    if not break_end:
        # The worked total stops increasing while the employee is on a break.
        return start if not clock_out and start <= end else None

    finish = minutes_since_clock_in(break_end, clock_in)
    return end - (finish - start) if start <= finish <= end else None


def format_attendance_duration(minutes, *, signed=False):
    prefix = '-' if minutes < 0 else ('+' if signed and minutes > 0 else '')
    hours, remaining_minutes = divmod(abs(minutes), 60)
    return f'{prefix}{hours:02d}:{remaining_minutes:02d}'


def next_attendance_step(entry, schedule):
    if entry.get('hora_saida'):
        return None

    has_break = (
        (schedule.get('inicio_intervalo') and schedule.get('fim_intervalo'))
        or entry.get('inicio_intervalo') or entry.get('fim_intervalo')
    )
    for action, column, label in ATTENDANCE_STEPS:
        if action in ('break_start', 'break_end') and not has_break:
            continue
        if not entry.get(column):
            return action, column, label
    return None


def attendance_work_date(now, entries_by_date, schedules):
    today = now.date()
    if today in entries_by_date:
        return today

    yesterday = today - timedelta(days=1)
    previous_entry = entries_by_date.get(yesterday, {})
    previous_schedule = schedules.get(ATTENDANCE_WEEKDAYS[yesterday.weekday()], {})
    planned_start = previous_schedule.get('hora_entrada')
    planned_end = previous_schedule.get('hora_saida')
    clock_in = previous_entry.get('hora_entrada')
    if not (planned_start and planned_end and planned_end < planned_start and clock_in):
        return today

    clock_out = previous_entry.get('hora_saida')
    today_start = schedules.get(ATTENDANCE_WEEKDAYS[today.weekday()], {}).get('hora_entrada')
    cutoff = clock_minutes(clock_in)
    if today_start and today_start >= planned_end:
        cutoff = min(cutoff, clock_minutes(today_start))
    if (not clock_out or clock_out < clock_in) and clock_minutes(now.strftime('%H:%M')) < cutoff:
        return yesterday
    return today


def latest_employee_punch(employee_id, now):
    # Check both recent work dates because a night shift can end the next morning.
    rows = sqlexecute(
        '''
        SELECT data, hora_entrada, inicio_intervalo, fim_intervalo, hora_saida
        FROM ponto WHERE id_colaborador = ? AND data <= ?
            AND coalesce(hora_entrada, inicio_intervalo, fim_intervalo, hora_saida) IS NOT NULL
        ORDER BY data DESC LIMIT 2
        ''',
        employee_id, now.date().isoformat(),
    )
    latest = None
    for row in rows:
        work_date = date.fromisoformat(row['data'])
        clock_in = row['hora_entrada']
        for _, column, _ in ATTENDANCE_STEPS:
            value = row[column]
            if not value:
                continue
            punch_date = work_date + timedelta(days=1) if clock_in and value < clock_in else work_date
            punch = datetime.combine(punch_date, time.fromisoformat(value), now.tzinfo)
            if punch <= now and (latest is None or punch > latest):
                latest = punch

    if latest is None:
        return None
    day_offset = (now.date() - latest.date()).days
    day_label = {0: 'Hoje', 1: 'Ontem'}.get(day_offset, f'{latest:%d/%m/%Y}')
    return f'{day_label} às {latest:%H:%M}'


def completed_service_months(hired_on, reference_date):
    completed_months = (reference_date.year - hired_on.year) * 12 + reference_date.month - hired_on.month
    # Use the last day of the month if the original hire day does not exist.
    anniversary_day = min(hired_on.day, monthrange(reference_date.year, reference_date.month)[1])
    if reference_date.day < anniversary_day:
        completed_months -= 1
    return completed_months


def calculate_vacation_days(employee_id, admission_date, today):
    if not admission_date:
        return 0

    try:
        hired_on = date.fromisoformat(admission_date)
    except ValueError:
        return 0
    if hired_on > today:
        return 0

    approved_vacations = sqlexecute(
        '''
        SELECT data_inicio, dias_solicitados FROM ferias
        WHERE id_colaborador = ? AND status = 'Aprovada'
            AND data_inicio >= ? AND data_solicitacao <= ? AND dias_solicitados IS NOT NULL
        ORDER BY data_inicio
        ''',
        employee_id, admission_date, today.isoformat(),
    )

    # Keep half-days so an unused fraction carries into the next month.
    monthly_credit = 5
    balance_limit = 30 * 2
    balance = credited_months = 0
    for vacation in approved_vacations:
        # Debit past vacations on their start date and reserve future approved days today.
        debit_date = min(date.fromisoformat(vacation['data_inicio']), today)
        service_months = completed_service_months(hired_on, debit_date)
        balance = min(balance_limit, balance + (service_months - credited_months) * monthly_credit)
        balance -= vacation['dias_solicitados'] * 2
        credited_months = service_months

    service_months = completed_service_months(hired_on, today)
    balance = min(balance_limit, balance + (service_months - credited_months) * monthly_credit)
    return int(max(0, balance) // 2)


def employee_dashboard_metrics(employee_id, now):
    today = now.date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    profile_rows = sqlexecute(
        '''
        SELECT d.cargo, d.carga_horaria_semanal_contrato, d.data_admissao
        FROM colaborador c
        JOIN dados_profissionais d ON d.id_dados_profissionais = c.id_dados_profissionais
        WHERE c.id_colaborador = ?
        ''',
        employee_id,
    )
    profile = profile_rows[0] if profile_rows else {}
    schedules = {row['dia_semana']: row for row in sqlexecute(
        '''
        SELECT dia_semana, hora_entrada, inicio_intervalo, fim_intervalo, hora_saida
        FROM escala WHERE id_colaborador = ? AND hora_entrada IS NOT NULL AND hora_saida IS NOT NULL
        ''',
        employee_id,
    )}
    rows = sqlexecute(
        '''
        SELECT data, hora_entrada, inicio_intervalo, fim_intervalo, hora_saida
        FROM ponto WHERE id_colaborador = ? AND data BETWEEN ? AND ? AND hora_entrada IS NOT NULL
        ''',
        employee_id, min(week_start, month_start).isoformat(), today.isoformat(),
    )
    entries_by_date = {date.fromisoformat(row['data']): row for row in rows}
    active_date = attendance_work_date(now, entries_by_date, schedules)

    worked_minutes = late_arrivals = 0
    for work_date, row in entries_by_date.items():
        schedule = schedules.get(ATTENDANCE_WEEKDAYS[work_date.weekday()])
        clock_in = row['hora_entrada']
        # Count one late arrival per scheduled date, using the first punch.
        if work_date >= month_start and schedule and clock_in > schedule['hora_entrada']:
            late_arrivals += 1
        if work_date < week_start:
            continue

        elapsed = None
        if work_date == active_date and not row['hora_saida']:
            minutes = (today - work_date).days * 1440 + now.hour * 60 + now.minute - clock_minutes(clock_in)
            if 0 <= minutes < 1440:
                elapsed = minutes
        worked_minutes += attendance_worked_minutes(row, elapsed) or 0

    # Use planned hours as a fallback when older profiles have no contract hours.
    contract_hours = profile.get('carga_horaria_semanal_contrato')
    weekly_minutes = int(contract_hours * 60) if contract_hours is not None else sum(
        attendance_worked_minutes(schedule) or 0 for schedule in schedules.values()
    )
    work_schedule = []
    for index, weekday in enumerate(ATTENDANCE_WEEKDAYS):
        schedule = schedules.get(weekday)
        work_schedule.append({
            'label': weekday[:3],
            'is_today': index == today.weekday(),
            'color': 'green' if schedule else 'gray',
            'time_range': f"{schedule['hora_entrada']} – {schedule['hora_saida']}" if schedule else '—',
            'status': 'Escalado' if schedule else 'Folga',
        })

    return {
        'total_hours': format_attendance_duration(weekly_minutes),
        'remaining_hours': format_attendance_duration(max(0, weekly_minutes - worked_minutes)),
        'last_clock_entry': latest_employee_punch(employee_id, now),
        'work_schedule': work_schedule,
        'late_arrivals': late_arrivals,
        'occupation': profile.get('cargo') or 'Não informada',
        'vacation_days': calculate_vacation_days(employee_id, profile.get('data_admissao'), today),
    }


@app.route('/attendence', methods=['GET', 'POST'])
@login_required
def attendance():
    employee_rows = sqlexecute(
        'SELECT id_colaborador FROM colaborador WHERE id_login = ?', session['user_id'],
    )
    if not employee_rows:
        return httperror('Colaborador não encontrado.', 404), 404

    employee_id = employee_rows[0]['id_colaborador']
    now = attendance_now()

    if request.method == 'POST':
        token = session.get('attendance_token')
        submitted_token = request.form.get('attendance_token', '')
        if not token or not secrets.compare_digest(token.encode(), submitted_token.encode()):
            return httperror('Formulário inválido. Atualize a página e tente novamente.', 403), 403

    # Catch up before reading the form state if the server was offline at closing time.
    try:
        close_expired_attendance(now, employee_id=employee_id)
    except sqlite3.DatabaseError:
        app.logger.exception('Failed to close expired attendance entries')
        return httperror('Não foi possível atualizar o ponto. Tente novamente.', 500), 500

    schedules = {
        row['dia_semana']: row for row in sqlexecute('SELECT * FROM escala WHERE id_colaborador = ?', employee_id)
    }
    entries = sqlexecute(
        'SELECT * FROM ponto WHERE id_colaborador = ? AND data <= ? ORDER BY data DESC LIMIT 10',
        employee_id, now.date().isoformat(),
    )
    entries_by_date = {date.fromisoformat(row['data']): row for row in entries}
    work_date = attendance_work_date(now, entries_by_date, schedules)
    entry = entries_by_date.get(work_date, {})
    schedule = schedules.get(ATTENDANCE_WEEKDAYS[work_date.weekday()], {})
    next_step = next_attendance_step(entry, schedule)

    current_time = now.strftime('%H:%M')
    clock_in = entry.get('hora_entrada')
    elapsed = None if not clock_in else (
        (now.date() - work_date).days * 1440 + clock_minutes(current_time) - clock_minutes(clock_in)
    )

    if request.method == 'POST':
        if (not next_step or request.form.get('attendance_action') != next_step[0]
                or request.form.get('work_date') != work_date.isoformat()):
            return httperror('O ponto já mudou. Volte à tela de ponto antes de registrar novamente.', 409), 409

        _, column, label = next_step
        if elapsed is not None and any(
            minutes_since_clock_in(entry[key], clock_in) > elapsed
            for _, key, _ in ATTENDANCE_STEPS if entry.get(key)
        ):
            return httperror('O horário atual é anterior ao último ponto registrado.', 409), 409

        try:
            if not entry:
                # Keep one row per employee and work date, even if two requests arrive together.
                written = sqlexecute(
                    '''
                    INSERT INTO ponto (id_colaborador, data, hora_entrada) VALUES (?, ?, ?)
                    ON CONFLICT (id_colaborador, data) DO NOTHING RETURNING id_ponto
                    ''',
                    employee_id, work_date.isoformat(), current_time,
                )
            else:
                # The column is selected by the server, and the snapshot prevents duplicate submissions.
                written = sqlexecute(
                    f'''
                    UPDATE ponto SET {column} = ? WHERE id_ponto = ? AND id_colaborador = ?
                        AND hora_entrada IS ? AND inicio_intervalo IS ?
                        AND fim_intervalo IS ? AND hora_saida IS ?
                    ''',
                    current_time, entry['id_ponto'], employee_id,
                    *(entry[key] for _, key, _ in ATTENDANCE_STEPS),
                )
        except sqlite3.DatabaseError:
            app.logger.exception('Failed to save attendance')
            return httperror('Não foi possível registrar o ponto. Tente novamente.', 500), 500

        if not written:
            return httperror('O ponto já mudou. Volte à tela de ponto antes de registrar novamente.', 409), 409

        flash(f'Ponto registrado às {current_time}: {label.lower()}.', 'attendance-success')
        return redirect(url_for('attendance'), code=303)

    if 'attendance_token' not in session:
        session['attendance_token'] = secrets.token_urlsafe(32)

    worked_total = attendance_worked_minutes(entry, max(0, elapsed) if elapsed is not None else None)
    worked = worked_total or 0
    expected = attendance_worked_minutes(schedule) or 0
    balance = worked - expected
    history = []
    for row in entries:
        row_date = date.fromisoformat(row['data'])
        row_schedule = schedules.get(ATTENDANCE_WEEKDAYS[row_date.weekday()], {})
        row_worked = worked_total if row_date == work_date else attendance_worked_minutes(row)
        row_balance = None if row_worked is None else row_worked - (attendance_worked_minutes(row_schedule) or 0)
        break_start, break_end = row['inicio_intervalo'], row['fim_intervalo']
        history.append({
            'date': f'{row_date:%d/%m/%Y} ({ATTENDANCE_WEEKDAYS[row_date.weekday()][:3]})',
            'clock_in': row['hora_entrada'] or '—',
            'break_period': f'{break_start} – {break_end or "—"}' if break_start else '—',
            'clock_out': row['hora_saida'] or '—',
            'balance': format_attendance_duration(row_balance, signed=True) if row_balance is not None else '—',
            'is_negative': row_balance is not None and row_balance < 0,
            'has_no_balance': row_balance is None,
        })

    return render_template(
        'attendence.html',
        server_now=now,
        work_date=work_date,
        is_previous_day=work_date != now.date(),
        next_entry=next_step[2] if next_step else None,
        next_action=next_step[0] if next_step else None,
        clock_in=entry.get('hora_entrada') or '—:—',
        break_start=entry.get('inicio_intervalo') or '—:—',
        break_end=entry.get('fim_intervalo') or '—:—',
        clock_out=entry.get('hora_saida') or '—:—',
        worked_hours=format_attendance_duration(worked),
        expected_hours=format_attendance_duration(expected),
        daily_balance=format_attendance_duration(balance, signed=True),
        is_balance_negative=balance < 0,
        attendance_history=history,
        live_summary={
            'worked': worked,
            'expected': expected,
            'running': worked_total is not None and elapsed is not None and elapsed >= 0
                and not entry.get('hora_saida')
                and (not entry.get('inicio_intervalo') or bool(entry.get('fim_intervalo'))),
        },
    )


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
