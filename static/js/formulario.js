// Función para ocultar o mostrar el domicilio
function toggleDireccion() {
    const esDelivery = document.querySelector('input[name="entrega"][value="delivery"]').checked;
    const divDireccion = document.getElementById('div-direccion');
    const inputDireccion = document.getElementById('direccion');

    if (esDelivery) {
        divDireccion.style.display = 'block'; 
        inputDireccion.required = true;       
    } else {
        divDireccion.style.display = 'none';  
        inputDireccion.required = false;      
        inputDireccion.value = '';            
    }
}

// Función para calcular la promoción automáticamente
function calcularTotal() {
    const inputCantidad = document.getElementById('cantidad');
    let cantidad = parseInt(inputCantidad.value);

    if (isNaN(cantidad) || cantidad < 0) {
        cantidad = 0;
    }

    const total = Math.floor(cantidad / 2) * 18000 + (cantidad % 2) * 10000;
    document.getElementById('precio-total').innerText = total.toLocaleString('es-AR');
}

// Para estilizar visualmente los botones de radio seleccionados
document.querySelectorAll('input[type=radio]').forEach(radio => {
    radio.addEventListener('change', function() {
        const name = this.name;
        document.querySelectorAll(`input[name="${name}"]`).forEach(r => {
            r.parentElement.style.backgroundColor = r.checked ? '#cce5ff' : '#e9ecef';
            r.parentElement.style.borderColor = r.checked ? '#b8daff' : 'transparent';
        });
    });
});

// Disparar el estilo inicial de los botones radio al cargar la página
window.dispatchEvent(new Event('change'));

// Enviar formulario mediante AJAX usando fetch
document.getElementById('ventaForm').addEventListener('submit', function(e) {
    e.preventDefault(); 

    const form = e.target;
    const formData = new FormData(form);
    const submitBtn = form.querySelector('.btn-submit');

    submitBtn.disabled = true;
    submitBtn.innerText = "Enviando...";

    fetch('/procesar_venta', {
        method: 'POST',
        body: formData
    })
    .then(async response => {
        const data = await response.json();

        if (response.ok) {
            Swal.fire({
                title: '¡Genial!',
                text: data.mensaje + '\nComprador: ' + data.comprador + '\nTotal: ' + data.total_a_cobrar,
                icon: 'success',
                confirmButtonText: 'Anotar otra venta',
                confirmButtonColor: '#28a745'
            }).then(() => {
                form.reset();
                document.querySelector('input[name="entrega"][value="retiro"]').checked = true;
                document.querySelector('input[name="pago"][value="pagado"]').checked = true;
                toggleDireccion();
                calcularTotal();
                window.dispatchEvent(new Event('change'));
            });
        } else {
            Swal.fire({
                title: 'Ups, algo salió mal',
                text: data.detail || 'Ocurrió un error al procesar la venta.',
                icon: 'error',
                confirmButtonText: 'Corregir',
                confirmButtonColor: '#d33'
            });
        }
    })
    .catch(error => {
        Swal.fire({
            title: 'Error de conexión',
            text: 'No se pudo conectar con el servidor. Revisa tu internet.',
            icon: 'error',
            confirmButtonText: 'Entendido'
        });
    })
    .finally(() => {
        submitBtn.disabled = false;
        submitBtn.innerText = "Anotar Venta";
    });
});