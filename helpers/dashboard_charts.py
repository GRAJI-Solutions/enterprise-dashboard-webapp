from datetime import date, timedelta
from helpers.helpers import sqlexecute


CHART_COLORS = [
  '#7338d5', '#f5a623', '#13a9ce', '#2263d6',
  '#40ae55', '#ea4e55', '#ce62ac', '#8294a7'
]

# Calculate worked time and subtract the break, when present.
_WORKED_SECONDS_SQL = '''
  (
    strftime('%s', '2000-01-01 ' || p.hora_saida)
    - strftime('%s', '2000-01-01 ' || p.hora_entrada)
    - CASE
        WHEN p.inicio_intervalo IS NOT NULL AND p.fim_intervalo IS NOT NULL
        THEN strftime('%s', '2000-01-01 ' || p.fim_intervalo)
             - strftime('%s', '2000-01-01 ' || p.inicio_intervalo)
        ELSE 0
      END
  )
'''


def _today():
  return date.today()


def _previous_month(reference_date):
  return (reference_date.replace(day=1) - timedelta(days=1)).replace(day=1)


def hours_last_eight_weeks(employee_id):
  # Fetch the employee's hours for the last eight weeks, including this week.
  today = _today()
  current_monday = today - timedelta(days=today.weekday())
  start_date = current_monday - timedelta(weeks=7)

  rows = sqlexecute(f'''
    WITH daily_hours AS (
      SELECT
        p.data AS work_date,
        {_WORKED_SECONDS_SQL} AS worked_seconds
      FROM ponto p
      WHERE p.id_colaborador = ?
        AND p.data BETWEEN ? AND ?
        AND p.hora_entrada IS NOT NULL
        AND p.hora_saida IS NOT NULL
        AND (
          (p.inicio_intervalo IS NULL AND p.fim_intervalo IS NULL)
          OR (p.inicio_intervalo IS NOT NULL AND p.fim_intervalo IS NOT NULL)
        )
    )
    SELECT
      CAST((julianday(work_date) - julianday(?)) / 7 AS INTEGER) AS week_index,
      ROUND(SUM(worked_seconds) / 3600.0, 1) AS hours
    FROM daily_hours
    WHERE worked_seconds >= 0
    GROUP BY week_index
  ''', employee_id, start_date.isoformat(), today.isoformat(), start_date.isoformat())

  values = [0] * 8
  for row in rows:
    week_index = int(row['week_index'])
    if 0 <= week_index < 8:
      values[week_index] = float(row['hours'] or 0)

  labels = []
  for week_index in range(8):
    monday = start_date + timedelta(weeks=week_index)
    sunday = monday + timedelta(days=6)
    labels.append(f'{monday:%d/%m} - {sunday:%d/%m}')

  return {'labels': labels, 'values': values}


def absences_last_five_months():
  # Count scheduled days without a clock-in, excluding approved vacation.
  today = _today()
  start_date = today.replace(day=1)
  for _ in range(4):
    start_date = _previous_month(start_date)

  yesterday = today - timedelta(days=1)
  months = []
  month = start_date
  for _ in range(5):
    months.append(month.strftime('%Y-%m'))
    month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)

  rows = sqlexecute('''
    WITH RECURSIVE calendar_days(work_date) AS (
      SELECT date(?)
      UNION ALL
      SELECT date(work_date, '+1 day')
      FROM calendar_days
      WHERE work_date < date(?)
    )
    SELECT strftime('%Y-%m', calendar_days.work_date) AS month, COUNT(*) AS total
    FROM calendar_days
    JOIN escala e ON e.dia_semana = CASE strftime('%w', calendar_days.work_date)
      WHEN '0' THEN 'Domingo'
      WHEN '1' THEN 'Segunda'
      WHEN '2' THEN 'Terça'
      WHEN '3' THEN 'Quarta'
      WHEN '4' THEN 'Quinta'
      WHEN '5' THEN 'Sexta'
      WHEN '6' THEN 'Sábado'
    END
    JOIN colaborador c ON c.id_colaborador = e.id_colaborador
    JOIN dados_profissionais d
      ON d.id_dados_profissionais = c.id_dados_profissionais
    WHERE d.data_admissao <= calendar_days.work_date
      AND e.hora_entrada IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM ponto p
        WHERE p.id_colaborador = c.id_colaborador
          AND p.data = calendar_days.work_date
          AND p.hora_entrada IS NOT NULL
      )
      AND NOT EXISTS (
        SELECT 1 FROM ferias f
        WHERE f.id_colaborador = c.id_colaborador
          AND f.status = 'Aprovada'
          AND calendar_days.work_date BETWEEN f.data_inicio AND f.data_fim
      )
    GROUP BY strftime('%Y-%m', calendar_days.work_date)
    ORDER BY month
  ''', start_date.isoformat(), yesterday.isoformat())

  totals_by_month = {row['month']: int(row['total']) for row in rows}
  return {
    'labels': [f'{month[5:7]}/{month[:4]}' for month in months],
    'values': [totals_by_month.get(month, 0) for month in months]
  }


def employees_by_department():
  # Count the employees in each department.
  rows = sqlexecute('''
    SELECT d.departamento AS name, COUNT(*) AS total
    FROM colaborador c
    JOIN dados_profissionais d
      ON d.id_dados_profissionais = c.id_dados_profissionais
    GROUP BY d.departamento
    ORDER BY total DESC, d.departamento
  ''')

  return [
    {'name': row['name'], 'total': int(row['total']), 'color': CHART_COLORS[index % len(CHART_COLORS)]}
    for index, row in enumerate(rows)
  ]


def current_average_salary():
  # Average the current salaries of all employees.
  today = _today().isoformat()
  rows = sqlexecute('''
    SELECT ROUND(AVG(h.valor), 2) AS average_salary
    FROM historico_salarial h
    WHERE h.id_historico_salarial = (
      SELECT h2.id_historico_salarial
      FROM historico_salarial h2
      WHERE h2.colaborador_id_colaborador = h.colaborador_id_colaborador
        AND h2.data_inicio <= ?
        AND (h2.data_fim IS NULL OR h2.data_fim >= ?)
      ORDER BY h2.data_inicio DESC, h2.id_historico_salarial DESC
      LIMIT 1
    )
  ''', today, today)
  return rows[0]['average_salary'] if rows else None


def monthly_hours_change():
  # Compare each employee's hours across the last two complete months.
  current_month_start = _today().replace(day=1)
  recent_month_start = _previous_month(current_month_start)
  previous_month_start = _previous_month(recent_month_start)

  rows = sqlexecute(f'''
    WITH daily_hours AS (
      SELECT
        p.id_colaborador AS employee_id,
        p.data AS work_date,
        {_WORKED_SECONDS_SQL} AS worked_seconds
      FROM ponto p
      WHERE p.data >= ? AND p.data < ?
        AND p.hora_entrada IS NOT NULL
        AND p.hora_saida IS NOT NULL
        AND (
          (p.inicio_intervalo IS NULL AND p.fim_intervalo IS NULL)
          OR (p.inicio_intervalo IS NOT NULL AND p.fim_intervalo IS NOT NULL)
        )
    ),
    employee_totals AS (
      SELECT
        c.id_colaborador,
        COALESCE(SUM(CASE
          WHEN h.work_date < ? AND h.worked_seconds >= 0 THEN h.worked_seconds ELSE 0
        END), 0) AS previous_seconds,
        COALESCE(SUM(CASE
          WHEN h.work_date >= ? AND h.worked_seconds >= 0 THEN h.worked_seconds ELSE 0
        END), 0) AS recent_seconds
      FROM colaborador c
      JOIN dados_profissionais d
        ON d.id_dados_profissionais = c.id_dados_profissionais
      LEFT JOIN daily_hours h ON h.employee_id = c.id_colaborador
      WHERE d.data_admissao <= ?
      GROUP BY c.id_colaborador
    )
    SELECT
      COALESCE(SUM(CASE WHEN recent_seconds > previous_seconds THEN 1 ELSE 0 END), 0) AS increased,
      COALESCE(SUM(CASE WHEN recent_seconds < previous_seconds THEN 1 ELSE 0 END), 0) AS decreased
    FROM employee_totals
  ''',
    previous_month_start.isoformat(), current_month_start.isoformat(),
    recent_month_start.isoformat(), recent_month_start.isoformat(),
    previous_month_start.isoformat()
  )

  return {
    'increased': int(rows[0]['increased'] or 0),
    'decreased': int(rows[0]['decreased'] or 0)
  }
