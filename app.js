const services = [
  { id: 'SRV-IMP-BN-CARTA', name: 'Impresión blanco y negro carta', cost: 0.066, price: 0.25 },
  { id: 'SRV-IMP-COLOR-CARTA', name: 'Impresión color carta', cost: 0.119, price: 0.35 },
  { id: 'SRV-COP-BN-CARTA', name: 'Copia blanco y negro carta', cost: 0.062, price: 0.25 },
  { id: 'SRV-COP-COLOR-CARTA', name: 'Copia color carta', cost: 0.114, price: 0.35 },
  { id: 'SRV-OPALINA-CLIENTE', name: 'Impresión opalina cliente', cost: 0.128, price: 0.35 },
  { id: 'SRV-FOTO-CARNET-4', name: 'Cuatro fotos carnet', cost: 0.389, price: 1.00 }
];

const inventory = [
  { name: 'Papel bond carta', stock: 500, min: 100 },
  { name: 'Opalina carta', stock: 0, min: 20 },
  { name: 'Fotográfico brillante', stock: 50, min: 10 },
  { name: 'Tinta negra', stock: 5, min: 1 },
  { name: 'Tinta cyan', stock: 3, min: 1 },
  { name: 'Tinta magenta', stock: 3, min: 1 },
  { name: 'Tinta amarilla', stock: 3, min: 1 }
];

let sales = JSON.parse(localStorage.getItem('copyMarySales') || '[]');
let clients = JSON.parse(localStorage.getItem('copyMaryClients') || '[{"id":"CL-001","name":"Cliente general","phone":"Sin teléfono"}]');

function money(value) { return '$' + Number(value).toFixed(2); }
function saveSales() { localStorage.setItem('copyMarySales', JSON.stringify(sales)); }
function saveClients() { localStorage.setItem('copyMaryClients', JSON.stringify(clients)); }

function renderServices() {
  const table = document.getElementById('servicesTable');
  table.innerHTML = '<tr><th>Servicio</th><th>Costo</th><th>Precio</th><th>Estado</th></tr>';
  services.forEach(function(service) {
    table.innerHTML += '<tr><td>' + service.name + '</td><td>' + money(service.cost) + '</td><td>' + money(service.price) + '</td><td><span class="badge badge-ok">Activo</span></td></tr>';
  });
}

function renderInventory() {
  const table = document.getElementById('inventoryTable');
  table.innerHTML = '<tr><th>Material</th><th>Stock</th><th>Mínimo</th><th>Estado</th></tr>';
  inventory.forEach(function(item) {
    const critical = item.stock <= item.min;
    const badge = critical ? '<span class="badge badge-critical">Crítico</span>' : '<span class="badge badge-ok">OK</span>';
    table.innerHTML += '<tr><td>' + item.name + '</td><td>' + item.stock + '</td><td>' + item.min + '</td><td>' + badge + '</td></tr>';
  });
}

function renderDashboard() {
  const critical = inventory.filter(function(item) { return item.stock <= item.min; }).length;
  const totalSales = sales.reduce(function(sum, sale) { return sum + sale.income; }, 0);
  const totalProfit = sales.reduce(function(sum, sale) { return sum + sale.profit; }, 0);
  const dashboard = document.getElementById('dashboard');
  dashboard.innerHTML = '';
  dashboard.innerHTML += '<div class="metric">' + money(totalSales) + '<span>Ventas registradas</span></div>';
  dashboard.innerHTML += '<div class="metric">' + money(totalProfit) + '<span>Ganancia acumulada</span></div>';
  dashboard.innerHTML += '<div class="metric">' + sales.length + '<span>Operaciones guardadas</span></div>';
  dashboard.innerHTML += '<div class="metric">' + critical + '<span>Materiales críticos</span></div>';
  renderChart(totalSales, totalProfit, critical, sales.length);
}

function renderChart(totalSales, totalProfit, critical, operations) {
  const chart = document.getElementById('profitChart');
  if (!chart) return;
  const max = Math.max(totalSales, totalProfit, critical, operations, 1);
  const rows = [
    { label: 'Ventas', value: totalSales, text: money(totalSales) },
    { label: 'Ganancia', value: totalProfit, text: money(totalProfit) },
    { label: 'Operaciones', value: operations, text: operations },
    { label: 'Críticos', value: critical, text: critical }
  ];
  chart.innerHTML = '';
  rows.forEach(function(row) {
    const width = Math.max((row.value / max) * 100, 4);
    chart.innerHTML += '<div class="bar-row"><strong>' + row.label + '</strong><div class="bar-track"><div class="bar-fill" style="width:' + width + '%"></div></div><span>' + row.text + '</span></div>';
  });
}

function renderSales() {
  const table = document.getElementById('salesTable');
  table.innerHTML = '<tr><th>Fecha</th><th>Cliente</th><th>Servicio</th><th>Ingreso</th><th>Utilidad</th><th>Pago</th></tr>';
  if (sales.length === 0) {
    table.innerHTML += '<tr><td colspan="6"><div class="empty-state">Aún no hay ventas guardadas.</div></td></tr>';
    return;
  }
  sales.slice().reverse().forEach(function(sale) {
    table.innerHTML += '<tr><td>' + sale.date + '</td><td>' + sale.client + '</td><td>' + sale.service + '</td><td>' + money(sale.income) + '</td><td>' + money(sale.profit) + '</td><td><span class="badge badge-warning">' + sale.payment + '</span></td></tr>';
  });
}

function renderClients() {
  const select = document.getElementById('clientSelect');
  const table = document.getElementById('clientsTable');
  select.innerHTML = '';
  clients.forEach(function(client) {
    const option = document.createElement('option');
    option.value = client.id;
    option.textContent = client.name;
    select.appendChild(option);
  });
  table.innerHTML = '<tr><th>Cliente</th><th>Teléfono</th><th>Estado</th></tr>';
  clients.forEach(function(client) {
    table.innerHTML += '<tr><td>' + client.name + '</td><td>' + client.phone + '</td><td><span class="badge badge-ok">Activo</span></td></tr>';
  });
}

function renderQuotes() {
  const box = document.getElementById('quoteBox');
  if (!box) return;
  box.innerHTML = '';
  services.slice(0, 4).forEach(function(service) {
    const profit = service.price - service.cost;
    box.innerHTML += '<div class="quote-item"><strong>' + service.name + '</strong><br>Precio sugerido: ' + money(service.price) + '<br>Costo: ' + money(service.cost) + '<br>Utilidad estimada: ' + money(profit) + '</div>';
  });
}

function setupClientForm() {
  const form = document.getElementById('clientForm');
  if (!form) return;
  form.addEventListener('submit', function(event) {
    event.preventDefault();
    const name = document.getElementById('clientName').value.trim();
    const phone = document.getElementById('clientPhone').value.trim();
    if (!name) return;
    clients.push({ id: 'CL-' + String(Date.now()).slice(-6), name: name, phone: phone || 'Sin teléfono' });
    saveClients();
    document.getElementById('clientName').value = '';
    document.getElementById('clientPhone').value = '';
    renderClients();
  });
}

function setupSaleForm() {
  const select = document.getElementById('serviceSelect');
  const unitPrice = document.getElementById('unitPrice');
  services.forEach(function(service) {
    const option = document.createElement('option');
    option.value = service.id;
    option.textContent = service.name;
    select.appendChild(option);
  });
  unitPrice.value = services[0].price;
  select.addEventListener('change', function() {
    const selected = services.find(function(service) { return service.id === select.value; });
    unitPrice.value = selected.price;
  });
  document.getElementById('saleForm').addEventListener('submit', function(event) {
    event.preventDefault();
    const selected = services.find(function(service) { return service.id === select.value; });
    const client = clients.find(function(item) { return item.id === document.getElementById('clientSelect').value; });
    const quantity = Number(document.getElementById('quantity').value);
    const price = Number(unitPrice.value);
    const payment = document.getElementById('paymentMethod').value;
    const result = document.getElementById('saleResult');
    result.className = 'result';
    if (price < selected.cost) {
      result.classList.add('error');
      result.innerHTML = '<strong>Error:</strong> el precio no puede ser menor que el costo.';
      return;
    }
    const income = price * quantity;
    const totalCost = selected.cost * quantity;
    const profit = income - totalCost;
    const margin = income > 0 ? (profit / income) * 100 : 0;
    const sale = { date: new Date().toLocaleDateString('es-VE'), client: client ? client.name : 'Cliente general', service: selected.name, quantity: quantity, income: income, cost: totalCost, profit: profit, margin: margin, payment: payment };
    sales.push(sale);
    saveSales();
    renderDashboard();
    renderSales();
    result.classList.add('success');
    result.innerHTML = '<strong>Venta guardada</strong><br>Cliente: ' + sale.client + '<br>Ingreso: ' + money(income) + '<br>Costo: ' + money(totalCost) + '<br>Utilidad: ' + money(profit) + '<br>Margen: ' + margin.toFixed(1) + '%';
  });
}

function setupTheme() {
  const button = document.getElementById('themeButton');
  if (!button) return;
  if (localStorage.getItem('copyMaryTheme') === 'dark') document.body.classList.add('dark');
  button.addEventListener('click', function() {
    document.body.classList.toggle('dark');
    localStorage.setItem('copyMaryTheme', document.body.classList.contains('dark') ? 'dark' : 'light');
  });
}

function setupExport() {
  const button = document.getElementById('exportButton');
  if (!button) return;
  button.addEventListener('click', function() {
    const header = 'fecha,cliente,servicio,cantidad,ingreso,costo,utilidad,margen,pago\n';
    const rows = sales.map(function(sale) {
      return [sale.date, sale.client, sale.service, sale.quantity, sale.income, sale.cost, sale.profit, sale.margin, sale.payment].join(',');
    }).join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'ventas-copy-mary.csv';
    link.click();
  });
}

renderClients();
renderDashboard();
renderServices();
renderInventory();
renderQuotes();
renderSales();
setupClientForm();
setupSaleForm();
setupTheme();
setupExport();
