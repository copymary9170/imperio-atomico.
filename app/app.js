const services = [
  { id: 'SRV-IMP-BN-CARTA', name: 'Impresion blanco y negro carta', cost: 0.066, price: 0.25 },
  { id: 'SRV-IMP-COLOR-CARTA', name: 'Impresion color carta', cost: 0.119, price: 0.35 },
  { id: 'SRV-COP-BN-CARTA', name: 'Copia blanco y negro carta', cost: 0.062, price: 0.25 },
  { id: 'SRV-COP-COLOR-CARTA', name: 'Copia color carta', cost: 0.114, price: 0.35 },
  { id: 'SRV-OPALINA-CLIENTE', name: 'Impresion opalina cliente', cost: 0.128, price: 0.35 },
  { id: 'SRV-FOTO-CARNET-4', name: 'Cuatro fotos carnet', cost: 0.389, price: 1.00 }
];

const inventory = [
  { name: 'Papel bond carta', stock: 500, min: 100 },
  { name: 'Opalina carta', stock: 0, min: 20 },
  { name: 'Fotografico brillante', stock: 50, min: 10 },
  { name: 'Tinta negra', stock: 5, min: 1 },
  { name: 'Tinta cyan', stock: 3, min: 1 },
  { name: 'Tinta magenta', stock: 3, min: 1 },
  { name: 'Tinta amarilla', stock: 3, min: 1 }
];

function money(value) {
  return '$' + Number(value).toFixed(2);
}

function renderServices() {
  const table = document.getElementById('servicesTable');
  table.innerHTML = '<tr><th>Servicio</th><th>Costo</th><th>Precio</th></tr>';
  services.forEach(function(service) {
    table.innerHTML += '<tr><td>' + service.name + '</td><td>' + money(service.cost) + '</td><td>' + money(service.price) + '</td></tr>';
  });
}

function renderInventory() {
  const table = document.getElementById('inventoryTable');
  table.innerHTML = '<tr><th>Material</th><th>Stock</th><th>Minimo</th><th>Estado</th></tr>';
  inventory.forEach(function(item) {
    const state = item.stock <= item.min ? 'Critico' : 'OK';
    table.innerHTML += '<tr><td>' + item.name + '</td><td>' + item.stock + '</td><td>' + item.min + '</td><td>' + state + '</td></tr>';
  });
}

function renderDashboard() {
  const critical = inventory.filter(function(item) { return item.stock <= item.min; }).length;
  const dashboard = document.getElementById('dashboard');
  dashboard.innerHTML = '';
  dashboard.innerHTML += '<div class="metric">Servicios activos: ' + services.length + '</div>';
  dashboard.innerHTML += '<div class="metric">Materiales criticos: ' + critical + '</div>';
  dashboard.innerHTML += '<div class="metric">Margen objetivo: 40%</div>';
  dashboard.innerHTML += '<div class="metric">Estado: operativo</div>';
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
    const quantity = Number(document.getElementById('quantity').value);
    const price = Number(unitPrice.value);
    const result = document.getElementById('saleResult');
    if (price < selected.cost) {
      result.innerHTML = '<strong>Error:</strong> el precio no puede ser menor que el costo.';
      return;
    }
    const income = price * quantity;
    const totalCost = selected.cost * quantity;
    const profit = income - totalCost;
    const margin = income > 0 ? (profit / income) * 100 : 0;
    result.innerHTML = '<strong>Venta calculada</strong><br>Ingreso: ' + money(income) + '<br>Costo: ' + money(totalCost) + '<br>Utilidad: ' + money(profit) + '<br>Margen: ' + margin.toFixed(1) + '%';
  });
}

renderDashboard();
renderServices();
renderInventory();
setupSaleForm();
