// Calcular todo al cargar la página por primera vez
window.addEventListener('DOMContentLoaded', aplicarFiltros);

function aplicarFiltros() {
    const ramaSeleccionada = document.getElementById('filtro-rama').value;
    const vendedorSeleccionado = document.getElementById('filtro-vendedor').value;

    let kpiPorciones = 0;
    let recaudadoVentas = 0; 
    let kpiACobrar = 0;
    let kpiTotalProyectado = 0;

    // 1. Filtrar tabla y sumar ventas
    document.querySelectorAll('.fila-venta').forEach(fila => {
        const ramaFila = fila.getAttribute('data-rama');
        const vendedorFila = fila.getAttribute('data-vendedor');
        let mostrar = true;

        if (ramaSeleccionada && ramaFila !== ramaSeleccionada) mostrar = false;
        if (vendedorSeleccionado && vendedorFila !== vendedorSeleccionado) mostrar = false;

        fila.style.display = mostrar ? '' : 'none';

        if (mostrar) {
            const cant = parseInt(fila.getAttribute('data-cantidad')) || 0;
            const total = parseInt(fila.getAttribute('data-total')) || 0;
            const pago = fila.getAttribute('data-pago');

            kpiPorciones += cant;
            kpiTotalProyectado += total;
            
            if (pago === 'pagado') {
                recaudadoVentas += total;
            } else {
                kpiACobrar += total;
            }
        }
    });

    // 2. Filtrar tarjetas de vendedores y sumar dinero entregado
    let kpiDineroAdmin = 0;
    document.querySelectorAll('.card-vendedor').forEach(card => {
        const ramaCard = card.getAttribute('data-rama');
        const vendedorCard = card.getAttribute('data-vendedor');
        let mostrar = true;

        if (ramaSeleccionada && ramaCard !== ramaSeleccionada) mostrar = false;
        if (vendedorSeleccionado && vendedorCard !== vendedorSeleccionado) mostrar = false;

        card.style.display = mostrar ? 'flex' : 'none';

        if (mostrar) {
            const entregado = parseInt(card.getAttribute('data-entregado')) || 0;
            kpiDineroAdmin += entregado;
        }
    });

    // 3. Escribir resultados en las tarjetas superiores
    const kpiDineroVendedor = recaudadoVentas - kpiDineroAdmin; 

    document.getElementById('kpi-porciones').innerText = kpiPorciones;
    document.getElementById('kpi-admin').innerText = "$" + kpiDineroAdmin.toLocaleString('es-AR');
    document.getElementById('kpi-vendedor').innerText = "$" + kpiDineroVendedor.toLocaleString('es-AR');
    document.getElementById('kpi-acobrar').innerText = "$" + kpiACobrar.toLocaleString('es-AR');
    document.getElementById('kpi-total').innerText = "$" + kpiTotalProyectado.toLocaleString('es-AR');

    // Actualizar link de descarga
    const btnDescargar = document.getElementById('btn-descargar-filtrado');
    let url = '/descargar_excel?';
    const params = new URLSearchParams();
    if (ramaSeleccionada) params.append('rama', ramaSeleccionada);
    if (vendedorSeleccionado) params.append('vendedor', vendedorSeleccionado);
    if (btnDescargar) btnDescargar.href = url + params.toString();
}

// Manejo de vendedores
function agregarVendedor() {
    Swal.fire({
        title: 'Agregar nuevo vendedor',
        html: `
            <input id="swal-nombre" class="swal2-input" placeholder="Nombre del vendedor (Ej: leones)">
            <select id="swal-rama" class="swal2-select">
                <option value="" disabled selected>Selecciona la rama</option>
                <option value="Manada">Manada</option>
                <option value="Unidad">Unidad</option>
                <option value="Caminantes">Caminantes</option>
                <option value="Rovers">Rovers</option>
                <option value="Educadores/acompañantes">Educadores/acompañantes</option>
            </select>
        `,
        focusConfirm: false,
        showCancelButton: true,
        confirmButtonText: 'Guardar',
        cancelButtonText: 'Cancelar',
        preConfirm: () => {
            const nombre = document.getElementById('swal-nombre').value;
            const rama = document.getElementById('swal-rama').value;
            
            if (!nombre || !rama) {
                Swal.showValidationMessage('¡Debes escribir un nombre y seleccionar una rama!');
                return false;
            }
            return { nombre: nombre, rama: rama };
        }
    }).then((result) => {
        if (result.isConfirmed) {
            fetch('/api/vendedores', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(result.value)
            })
            .then(async response => {
                const data = await response.json();
                if (response.ok) {
                    Swal.fire('¡Guardado!', data.mensaje, 'success').then(() => location.reload());
                } else {
                    Swal.fire('Error', data.detail || 'No se pudo agregar el vendedor.', 'error');
                }
            });
        }
    });
}

function registrarEntrega(nombreVendedor) {
    Swal.fire({
        title: `Recibir dinero de ${nombreVendedor}`,
        input: 'number',
        inputLabel: '¿Cuánta plata te está entregando? (Solo números)',
        inputPlaceholder: 'Ej: 15000',
        showCancelButton: true,
        confirmButtonText: 'Registrar',
        cancelButtonText: 'Cancelar',
        confirmButtonColor: '#28a745',
        inputValidator: (value) => {
            if (!value || value <= 0) {
                return '¡Debes ingresar un monto válido mayor a 0!'
            }
        }
    }).then((result) => {
        if (result.isConfirmed) {
            fetch('/api/entregas', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ vendedor: nombreVendedor, monto: parseInt(result.value) })
            })
            .then(async response => {
                const data = await response.json();
                if (response.ok) {
                    Swal.fire('¡Registrado!', data.mensaje, 'success').then(() => location.reload());
                } else {
                    Swal.fire('No se pudo registrar', data.detail, 'warning');
                }
            });
        }
    });
}

function eliminarVendedor(id, nombre) {
    Swal.fire({
        title: '¿Estás seguro?',
        text: `Vas a eliminar a "${nombre}". Las ventas asociadas no se borrarán, pero el link dejará de funcionar para este vendedor.`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#3085d6',
        confirmButtonText: 'Sí, eliminar',
        cancelButtonText: 'Cancelar'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch(`/api/vendedores/${id}`, { method: 'DELETE' })
            .then(async response => {
                if (response.ok) {
                    Swal.fire('Eliminado', 'El vendedor ha sido eliminado.', 'success').then(() => location.reload());
                } else {
                    const data = await response.json();
                    Swal.fire('Error', data.detail || 'Ocurrió un error.', 'error');
                }
            });
        }
    });
}

// Manejo de ventas
function eliminarVenta(id, comprador) {
    Swal.fire({
        title: '¿Eliminar Venta?',
        text: `¿Borrar la venta de ${comprador}? Esta acción no se puede deshacer.`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#3085d6',
        confirmButtonText: 'Sí, borrar',
        cancelButtonText: 'Cancelar'
    }).then((result) => {
        if (result.isConfirmed) {
            fetch(`/api/ventas/${id}`, { method: 'DELETE' })
            .then(async response => {
                if (response.ok) {
                    Swal.fire('Eliminada', 'La venta fue eliminada.', 'success').then(() => location.reload());
                } else {
                    const data = await response.json();
                    Swal.fire('Error', data.detail || 'No se pudo eliminar la venta.', 'error');
                }
            });
        }
    });
}

function editarVenta(id, nombre, apellido, telefono, mail, entrega, direccion, cantidad, pago) {
    Swal.fire({
        title: 'Editar Venta',
        html: `
            <input id="swal-nombre" class="swal2-input" placeholder="Nombre" value="${nombre}">
            <input id="swal-apellido" class="swal2-input" placeholder="Apellido" value="${apellido}">
            <input id="swal-telefono" class="swal2-input" placeholder="Teléfono" value="${telefono}">
            <input id="swal-mail" class="swal2-input" placeholder="Mail" value="${mail}">

            <select id="swal-entrega" class="swal2-select" onchange="document.getElementById('swal-direccion').style.display = this.value === 'delivery' ? 'flex' : 'none'">
                <option value="retiro" ${entrega === 'retiro' ? 'selected' : ''}>Lo retira</option>
                <option value="delivery" ${entrega === 'delivery' ? 'selected' : ''}>Delivery</option>
            </select>

            <input id="swal-direccion" class="swal2-input" placeholder="Dirección" value="${direccion}" style="display: ${entrega === 'delivery' ? 'flex' : 'none'}">

            <input id="swal-cantidad" type="number" class="swal2-input" placeholder="Cantidad de porciones" value="${cantidad}" min="1">

            <select id="swal-pago" class="swal2-select">
                <option value="pagado" ${pago === 'pagado' ? 'selected' : ''}>Pagado</option>
                <option value="al_recibir" ${pago === 'al_recibir' ? 'selected' : ''}>Al recibir</option>
            </select>
        `,
        focusConfirm: false,
        showCancelButton: true,
        confirmButtonText: 'Guardar Cambios',
        cancelButtonText: 'Cancelar',
        preConfirm: () => {
            return {
                nombre: document.getElementById('swal-nombre').value,
                apellido: document.getElementById('swal-apellido').value,
                telefono: document.getElementById('swal-telefono').value,
                mail: document.getElementById('swal-mail').value || null,
                entrega: document.getElementById('swal-entrega').value,
                direccion: document.getElementById('swal-direccion').value || null,
                cantidad: parseInt(document.getElementById('swal-cantidad').value),
                pago: document.getElementById('swal-pago').value
            }
        }
    }).then((result) => {
        if (result.isConfirmed) {
            fetch(`/api/ventas/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(result.value)
            })
            .then(async response => {
                const data = await response.json();
                if (response.ok) {
                    Swal.fire('¡Actualizada!', 'La venta se ha guardado correctamente.', 'success').then(() => location.reload());
                } else {
                    Swal.fire('Error', data.detail || 'Error al actualizar la venta.', 'error');
                }
            });
        }
    });
}