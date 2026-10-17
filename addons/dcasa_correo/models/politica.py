"""Qué correos pueden salir por Resend (funciones puras, sin base de datos).

Cada correo que Odoo manda lleva una **clase** (cabecera ``X-Dcasa-Clase``, la pone ``mail.mail`` solo si hay clave):

========== ==========================================================================================
Clase      Cuándo
========== ==========================================================================================
factura,   Los arma D'CASA (cabecera ``X-Dcasa-Correo``): la factura o el abono al pagar, la bienvenida,
abono, …   la cotización, la factura del botón «Enviar», el correo de prueba.
acceso     ``res.users``: cambiar la contraseña o la invitación a la tienda (lo necesita «Mi cuenta»).
documento  Un mensaje que una persona del equipo escribe en una factura o en una venta.
odoo       Todo lo demás: confirmaciones automáticas de Odoo, pago recibido, carrito abandonado…
========== ==========================================================================================

Y ``puede_salir`` decide:

* ``prueba`` sale solo si TODOS los destinatarios son correos del equipo, aunque el interruptor esté apagado;
* con el interruptor apagado, o en staging, no sale nada más;
* encendido salen las clases de ``CLASES_A_CLIENTES``; ``odoo`` nunca (lo decide la dueña).
"""

CABECERA_CORREO = 'X-Dcasa-Correo'   # la pone D'CASA al armar el correo
CABECERA_CLASE = 'X-Dcasa-Clase'     # la pone mail.mail justo antes de enviar; la lee el transporte
CLASE_ODOO = 'odoo'
CLASE_PRUEBA = 'prueba'
# Valores de X-Dcasa-Correo que se respetan (otro valor cuenta como «odoo»).
CLASES_DCASA = ('factura', 'abono', 'bienvenida', 'cotizacion', 'documento', CLASE_PRUEBA)
CLASES_A_CLIENTES = ('factura', 'abono', 'bienvenida', 'cotizacion', 'documento', 'acceso')
MODELOS_DOCUMENTO = ('account.move', 'sale.order')

MOTIVO_APAGADO = 'Correos a clientes apagados.'
MOTIVO_STAGING = 'Staging: nunca se envía a clientes.'
MOTIVO_ODOO = 'Correo automático de Odoo sin permiso.'
MOTIVO_PRUEBA = 'La prueba solo va a correos del equipo.'
MOTIVO_SIN_DESTINO = 'Sin destinatarios.'


def clase_de_correo(model, message_type, autor_interno, cabecera=None):
    """La clase de un correo (ver la tabla del módulo)."""
    valor = str(cabecera or '').strip().lower()
    if valor:
        return valor if valor in CLASES_DCASA else CLASE_ODOO
    if model == 'res.users':
        return 'acceso'
    if model in MODELOS_DOCUMENTO and message_type == 'comment' and autor_interno:
        return 'documento'
    return CLASE_ODOO


def puede_salir(clase, a_clientes, entorno, destinatarios, correos_internos):
    """``(True, '')`` si sale; si no, ``(False, motivo)``. ``a_clientes`` ya trae resueltos la clave y el entorno."""
    destinos = {(d or '').strip().lower() for d in destinatarios or [] if (d or '').strip()}
    if not destinos:
        return False, MOTIVO_SIN_DESTINO
    internos = {(c or '').strip().lower() for c in correos_internos or [] if c}
    if clase == CLASE_PRUEBA:
        return (True, '') if destinos <= internos else (False, MOTIVO_PRUEBA)
    if entorno == 'staging':
        return False, MOTIVO_STAGING
    if not a_clientes:
        return False, MOTIVO_APAGADO
    if clase in CLASES_A_CLIENTES:
        return True, ''
    return False, MOTIVO_ODOO
