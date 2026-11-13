// Dashboard chart colors.
const TEXT_COLOR = '#e9edf5';
const GRID_COLOR = 'rgba(255, 255, 255, 0.10)';
const BAR_COLOR = 'rgba(38, 132, 171, 0.8)';
const DEPARTMENT_COLORS = [
  '#7338d5', '#f5a623', '#13a9ce', '#2263d6',
  '#40ae55', '#ea4e55', '#ce62ac', '#8294a7'
];

function drawBarChart(element, data, axisTitle) {
  if (!element || typeof Chart === 'undefined') return;

  new Chart(element, {
    type: 'bar',
    data: {
      labels: data.labels,
      datasets: [{
        data: data.values,
        backgroundColor: BAR_COLOR,
        borderRadius: 3,
        maxBarThickness: 40
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: { color: TEXT_COLOR },
          grid: { display: false }
        },
        y: {
          beginAtZero: true,
          ticks: { color: TEXT_COLOR, precision: 0 },
          grid: { color: GRID_COLOR },
          title: { display: true, text: axisTitle, color: TEXT_COLOR }
        }
      }
    }
  });
}

function drawDoughnutChart(element, departments) {
  if (!element || typeof Chart === 'undefined') return;

  if (!departments.length) {
    element.parentElement.textContent = 'Nenhum colaborador cadastrado';
    return;
  }

  new Chart(element, {
    type: 'doughnut',
    data: {
      labels: departments.map(department => department.name),
      datasets: [{
        data: departments.map(department => department.total),
        backgroundColor: departments.map((department, index) => department.color || DEPARTMENT_COLORS[index % DEPARTMENT_COLORS.length]),
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '55%',
      plugins: { legend: { display: false } }
    }
  });
}
