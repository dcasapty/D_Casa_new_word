"""Superficie RPC de los módulos de D'CASA (anti-regresión de la Fase 0 de seguridad).

Odoo expone por ``/web/dataset/call_kw`` y ``/json/2`` TODO método público de un modelo:
sin ``_`` delante y sin ``@api.private`` (``odoo.service.model.get_public_method``). El ACL
NO se comprueba al despachar el método; solo frena las operaciones ORM sin ``sudo()``. Un
método público que escribe con ``sudo()`` sin comprobar grupo es, por tanto, una puerta
abierta para cualquier usuario autenticado (incluido un portal creado en /web/signup).

Este test recorre todos los modelos instalados, toma los métodos que DEFINEN los módulos de
``addons/`` (``dcasa_*`` y ``website_dcasa``, también los añadidos a modelos de Odoo) y falla
si alguno es invocable por RPC y no está en ``LISTA_BLANCA`` con su motivo. Si añades un
método público: hazlo privado (``_nombre`` o ``@api.private``) o, si de verdad lo llama la
interfaz, compruébale el grupo en el servidor ANTES de cualquier ``sudo()`` y anótalo aquí.
"""
import inspect

from lxml import etree

from odoo.exceptions import AccessError
from odoo.service.model import get_public_method
from odoo.tests import TransactionCase, tagged

PREFIJOS = ('odoo.addons.dcasa_', 'odoo.addons.website_dcasa.')

SIN_SUDO = 'Corre como el usuario, sin sudo: lo frenan el ACL y las reglas de registro.'
ACCION_VENTANA = 'Solo devuelve una acción de ventana; no lee ni escribe datos.'
ASISTENTE = ('Botón de un asistente (TransientModel): leer sus campos exige el ACL del CSV, '
             'que lo limita al grupo correspondiente.')
OVERRIDE = 'Sobrescribe un método público estándar de Odoo; la superficie no cambia.'
CONTADOR = 'API de la pantalla de conciliación: exige account.group_account_user en el servidor.'
VENTAS_BOTON = ('Botón: exige sales_team.group_sale_salesman en el servidor (_exigir_vendedora) y el ACL '
                'antes de escribir.')
PANEL_GERENCIA = ('API de la pantalla de Juan solo para Gerencia: exige sales_team.group_sale_manager en el servidor '
                  '(_exigir_gerencia) ANTES de hablar con el Worker; nunca devuelve claves ni imprime el QR en logs.')
PANEL_VENTAS = ('API de la pantalla de conversaciones: exige sales_team.group_sale_salesman en el servidor '
                '(_exigir_vendedora) ANTES de leer o escribir con sudo; valida cada argumento.')

NOMINA_BOTON = ('Botón de nómina: check_access("write") (grupo «Administra la nómina») ANTES de cualquier sudo(); el '
                'sudo solo cambia el estado, que nunca se escribe por RPC (write lo exige).')
NOMINA_BLOQUEO = ('Bloquea: lo validado o ya usado por una planilla no se cambia (solo con sudo desde sus botones); '
                  'sin sudo, con el ACL del grupo «Administra la nómina».')
NOMINA_REEMBOLSO = ('Botón del reembolso: el colaborador solo el suyo; aprobar y rechazar exigen el grupo '
                    '«Administra la nómina» en el servidor; el estado solo cambia con sudo, ya comprobado.')

# (módulo, modelo, método): motivo por el que puede llamarse por RPC.
LISTA_BLANCA = {
    # --- dcasa_base -------------------------------------------------------------------------
    ('dcasa_base', 'sale.order.line', 'create'):
        OVERRIDE + ' Agrega el tope de descuento de la vendedora; sin sudo().',
    ('dcasa_base', 'sale.order.line', 'write'):
        OVERRIDE + ' Agrega el tope de descuento de la vendedora; sin sudo().',
    ('dcasa_base', 'sale.order.line', 'unlink'):
        OVERRIDE + ' Vuelve a medir el tope de descuento del pedido entero al quitar una línea; sin sudo().',
    ('dcasa_base', 'stock.quant', 'create'):
        OVERRIDE + ' Solo Gerencia crea o edita un conteo de existencias (ajuste a mano); sin sudo().',
    ('dcasa_base', 'stock.quant', 'write'):
        OVERRIDE + ' Solo Gerencia crea o edita un conteo de existencias (ajuste a mano); sin sudo().',
    ('dcasa_base', 'product.template', 'write'):
        OVERRIDE + ' Agrega que el precio y el costo solo los cambia Gerencia; sin sudo().',
    ('dcasa_base', 'product.product', 'write'):
        OVERRIDE + ' Agrega que el precio y el costo solo los cambia Gerencia; sin sudo().',
    ('dcasa_base', 'sale.order', 'action_confirm'):
        OVERRIDE + ' Solo vuelve a tomar el costo de cada línea al confirmar (la ganancia de esa venta); corre como el '
                   'usuario, sin sudo().',
    ('dcasa_base', 'product.template', 'create'):
        OVERRIDE + ' Solo le pone al producto nuevo su código público (sorteado, único); sin sudo().',
    ('dcasa_base', 'product.product', 'name_search'):
        OVERRIDE + ' Solo suma al buscador de «Producto» el código público; busca con los permisos de la persona '
                   '(sin sudo) y no devuelve más que el nombre.',
    ('dcasa_base', 'product.template', 'action_dcasa_regenerar_codigo_publico'):
        'Botón: exige base.group_system (administrador) y escritura sobre el producto ANTES de cambiar el código; '
        'deja nota en el historial del producto; sin sudo().',
    ('website_dcasa', 'sale.order', 'action_dcasa_apartar'): SIN_SUDO,
    ('website_dcasa', 'ir.qweb.field.image', 'record_to_html'):
        OVERRIDE + ' Solo agrega srcset/sizes/width/height/loading a la <img>; sin sudo().',
    ('website_dcasa', 'ir.qweb.field.image_url', 'record_to_html'):
        OVERRIDE + ' Hereda la anterior (image_url extiende image); sin sudo().',
    # --- dcasa_catalogo -----------------------------------------------------------------
    ('dcasa_catalogo', 'sale.order', 'action_dcasa_whatsapp'): SIN_SUDO,
    ('dcasa_catalogo', 'sale.order', 'action_confirm'):
        OVERRIDE + ' Solo agrega que un combo sin sus piezas no se confirma; corre como el usuario, sin sudo().',
    # --- dcasa_contabilidad --------------------------------------------------------------
    ('dcasa_contabilidad', 'dcasa.importar.extracto', 'action_importar'): ASISTENTE + ' (account.group_account_user)',
    ('dcasa_contabilidad', 'dcasa.presupuesto', 'action_aprobar'): SIN_SUDO,
    ('dcasa_contabilidad', 'dcasa.presupuesto', 'action_cerrar'): SIN_SUDO,
    ('dcasa_contabilidad', 'dcasa.presupuesto', 'action_borrador'): SIN_SUDO,
    ('dcasa_contabilidad', 'dcasa.presupuesto', 'action_ver_apuntes'): ACCION_VENTANA,
    ('dcasa_contabilidad', 'dcasa.presupuesto.linea', 'action_ver_apuntes'): ACCION_VENTANA,
    ('dcasa_contabilidad', 'dcasa.reporte.contable', 'obtener'):
        'Único punto de entrada de los reportes: exige account.group_account_readonly (C-07).',
    ('dcasa_contabilidad', 'dcasa.reporte.contable', 'periodos'): 'Solo atajos de fechas; no lee apuntes.',
    ('dcasa_contabilidad', 'account.journal', 'open_action'): OVERRIDE + ' Solo devuelve la acción.',
    ('dcasa_contabilidad', 'dcasa.conciliacion', 'diarios'): CONTADOR,
    ('dcasa_contabilidad', 'dcasa.conciliacion', 'pendientes'): CONTADOR,
    ('dcasa_contabilidad', 'dcasa.conciliacion', 'candidatos'): CONTADOR,
    ('dcasa_contabilidad', 'dcasa.conciliacion', 'cuentas_rapidas'): CONTADOR,
    ('dcasa_contabilidad', 'dcasa.conciliacion', 'conciliar'): CONTADOR,
    ('dcasa_contabilidad', 'dcasa.conciliacion', 'automatico'): CONTADOR,
    ('dcasa_contabilidad', 'dcasa.conciliacion', 'deshacer'): CONTADOR,
    ('dcasa_contabilidad', 'dcasa.conciliacion', 'reglas'): CONTADOR,
    ('dcasa_contabilidad', 'dcasa.conciliacion', 'aplicar_regla'): CONTADOR,
    ('dcasa_contabilidad', 'dcasa.conciliacion', 'pagos_por_cruzar'): CONTADOR,
    ('dcasa_contabilidad', 'dcasa.conciliacion', 'cruzar_pago'): CONTADOR,
    ('dcasa_contabilidad', 'dcasa.cierre.mes', 'create'): OVERRIDE + ' Normaliza el mes y arma la lista; sin sudo.',
    ('dcasa_contabilidad', 'dcasa.cierre.mes', 'write'): OVERRIDE + ' Impide mover un mes cerrado; sin sudo.',
    ('dcasa_contabilidad', 'dcasa.cierre.mes', 'action_revisar'): SIN_SUDO,
    ('dcasa_contabilidad', 'dcasa.cierre.mes', 'action_cerrar'):
        'Botón: exige account.group_account_manager ANTES de escribir la fecha de bloqueo de la empresa con sudo.',
    ('dcasa_contabilidad', 'dcasa.cierre.mes', 'action_reabrir'):
        'Botón: exige account.group_account_manager y motivo ANTES de bajar la fecha de bloqueo con sudo.',
    ('dcasa_contabilidad', 'dcasa.cierre.mes.paso', 'action_ver'): ACCION_VENTANA,
    # --- dcasa_migracion ----------------------------------------------------------------
    ('dcasa_migracion', 'dcasa.migracion.carga', 'action_revisar'):
        ASISTENTE + ' (base.group_system); además exige administrador en el servidor (_exigir_administrador) y '
        'el ensayo se deshace por completo.',
    ('dcasa_migracion', 'dcasa.migracion.carga', 'action_cargar'):
        ASISTENTE + ' (base.group_system); además exige administrador en el servidor (_exigir_administrador) y '
        'haber revisado antes los mismos archivos.',
    # --- dcasa_nomina -------------------------------------------------------------------
    ('dcasa_nomina', 'dcasa.nomina.config', 'action_abrir'):
        ACCION_VENTANA + ' Exige leer la configuración (grupo Nómina).',
    ('dcasa_nomina', 'dcasa.nomina.parametros', 'action_validar'): NOMINA_BOTON,
    ('dcasa_nomina', 'dcasa.nomina.parametros', 'action_reabrir'): NOMINA_BOTON,
    ('dcasa_nomina', 'dcasa.nomina.parametros', 'create'): OVERRIDE + ' Una copia nunca nace validada.',
    ('dcasa_nomina', 'dcasa.nomina.parametros', 'write'): NOMINA_BLOQUEO,
    ('dcasa_nomina', 'dcasa.nomina.isr.tramo', 'create'): NOMINA_BLOQUEO,
    ('dcasa_nomina', 'dcasa.nomina.isr.tramo', 'write'): NOMINA_BLOQUEO,
    ('dcasa_nomina', 'dcasa.nomina.isr.tramo', 'unlink'): NOMINA_BLOQUEO,
    ('dcasa_nomina', 'dcasa.nomina.planilla', 'action_calcular'): NOMINA_BOTON,
    ('dcasa_nomina', 'dcasa.nomina.planilla', 'action_confirmar'): NOMINA_BOTON,
    ('dcasa_nomina', 'dcasa.nomina.planilla', 'action_pagar'): NOMINA_BOTON,
    ('dcasa_nomina', 'dcasa.nomina.planilla', 'action_borrador'): NOMINA_BOTON,
    ('dcasa_nomina', 'dcasa.nomina.planilla', 'action_cancelar'): NOMINA_BOTON,
    ('dcasa_nomina', 'dcasa.nomina.planilla', 'write'):
        'Bloquea: el estado solo cambia con los botones y una planilla confirmada no cambia de periodo; sin sudo.',
    ('dcasa_nomina', 'dcasa.nomina.linea', 'create'):
        'Bloquea: no se agregan colaboradores a una planilla confirmada; sin sudo.',
    ('dcasa_nomina', 'dcasa.nomina.linea', 'write'):
        'Bloquea: una línea confirmada no cambia y el pago solo se anota con «Pagar»; sin sudo.',
    ('dcasa_nomina', 'dcasa.nomina.vacacion', 'action_confirmar'): SIN_SUDO,
    ('dcasa_nomina', 'dcasa.nomina.vacacion', 'action_cancelar'): SIN_SUDO,
    ('dcasa_nomina', 'dcasa.nomina.vacacion', 'action_borrador'): SIN_SUDO,
    ('dcasa_nomina', 'dcasa.nomina.liquidacion', 'action_calcular'): NOMINA_BOTON,
    ('dcasa_nomina', 'dcasa.nomina.liquidacion', 'action_revisar'): NOMINA_BOTON,
    ('dcasa_nomina', 'dcasa.nomina.liquidacion', 'action_borrador'): NOMINA_BOTON,
    ('dcasa_nomina', 'dcasa.nomina.reembolso', 'action_enviar'): NOMINA_REEMBOLSO,
    ('dcasa_nomina', 'dcasa.nomina.reembolso', 'action_aprobar'): NOMINA_REEMBOLSO,
    ('dcasa_nomina', 'dcasa.nomina.reembolso', 'action_rechazar'): NOMINA_REEMBOLSO,
    ('dcasa_nomina', 'dcasa.nomina.reembolso', 'action_borrador'): NOMINA_REEMBOLSO,
    ('dcasa_nomina', 'dcasa.nomina.reembolso', 'create'):
        'Bloquea: el colaborador solo registra a su nombre y no pone estado ni aprobación; la foto sin dueño se '
        'le asigna con sudo solo si la subió él.',
    ('dcasa_nomina', 'dcasa.nomina.reembolso', 'write'):
        'Bloquea: el colaborador solo edita su borrador; estado y aprobación solo por los botones (sudo).',
    # --- dcasa_consolidacion (estados financieros de varias empresas) -----------------------------
    # El motor (dcasa.consolidacion.motor) es todo privado: solo lo llaman los botones de abajo.
    ('dcasa_consolidacion', 'dcasa.consolidacion', 'create'):
        OVERRIDE + ' Bloquea estado, advertencias y líneas puestos a mano (solo «Calcular» los pone); sin sudo.',
    ('dcasa_consolidacion', 'dcasa.consolidacion', 'write'):
        OVERRIDE + ' Bloquea estado, advertencias y líneas puestos a mano, y cambiar empresas, reporte o fechas de '
                   'una consolidación ya calculada; sin sudo.',
    ('dcasa_consolidacion', 'dcasa.consolidacion', 'action_calcular'):
        'Botón: exige account.group_account_user ANTES de calcular; lee los apuntes con los permisos de la persona '
        '(sin sudo) y solo escribe con sudo las líneas ya calculadas.',
    ('dcasa_consolidacion', 'dcasa.consolidacion', 'action_borrador'):
        'Botón: exige account.group_account_user y escritura sobre el registro ANTES de soltar las líneas con sudo.',
    ('dcasa_consolidacion', 'dcasa.consolidacion', 'action_ver_pivote'):
        ACCION_VENTANA + ' Comprueba check_access("read") antes.',
    ('dcasa_consolidacion', 'dcasa.consolidacion.mapa', 'create'):
        OVERRIDE + ' Solo quita espacios del código consolidado; sin sudo (ACL: contador).',
    ('dcasa_consolidacion', 'dcasa.consolidacion.mapa', 'write'):
        OVERRIDE + ' Solo quita espacios del código consolidado; sin sudo (ACL: contador).',
    # --- dcasa_contactos -------------------------------------------------------------------
    ('dcasa_contactos', 'dcasa.contacto.duplicado', 'action_ver'):
        ACCION_VENTANA + ' Solo lee las fichas de la fila (ACL: Gerencia).',
    ('dcasa_contactos', 'dcasa.contacto.duplicado', 'action_fusionar'):
        ACCION_VENTANA + ' El asistente de fusión de Odoo exige ser administrador de contactos; no escribe aquí.',
    ('dcasa_contactos', 'res.partner', 'create'):
        OVERRIDE + ' Solo agrega el candado de duplicados (sudo para buscar, nunca para escribir).',
    ('dcasa_contactos', 'res.partner', 'write'):
        OVERRIDE + ' Solo agrega el candado de duplicados (sudo para buscar, nunca para escribir).',
    ('dcasa_contactos', 'base.partner.merge.automatic.wizard', 'action_start_automatic_process'):
        OVERRIDE + ' Exige base.group_system en el servidor antes de fusionar en masa; sin sudo().',
    ('dcasa_contactos', 'base.partner.merge.automatic.wizard', 'action_update_all_process'):
        OVERRIDE + ' Exige base.group_system en el servidor antes de fusionar en masa; sin sudo().',
    ('dcasa_contactos', 'base.partner.merge.automatic.wizard', 'parent_migration_process_cb'):
        OVERRIDE + ' Exige base.group_system en el servidor antes de tocar los padres de los contactos; sin sudo().',
    ('dcasa_contactos', 'res.users', 'create'): OVERRIDE + ' Solo crea el usuario sin el candado de su contacto.',
    ('dcasa_contactos', 'res.company', 'create'): OVERRIDE + ' Solo crea la empresa sin el candado de su contacto.',
    # --- dcasa_barras -------------------------------------------------------------------------
    ('dcasa_barras', 'dcasa.barras', 'buscar'):
        'API del Escáner: exige stock.group_stock_user en el servidor ANTES de leer; no devuelve costos; sin sudo.',
    ('dcasa_barras', 'dcasa.barras', 'buscar_por_nombre'):
        'API del Escáner: exige stock.group_stock_user en el servidor ANTES de buscar; sin sudo.',
    ('dcasa_barras', 'dcasa.barras', 'ficha'):
        'API del Escáner: exige stock.group_stock_user en el servidor y lectura del producto; sin sudo.',
    ('dcasa_barras', 'dcasa.barras', 'contar'):
        'API del Escáner: exige stock.group_stock_manager (Gerencia) en el servidor ANTES de escribir; valida cada '
        'argumento y usa el Inventario físico de Odoo con los permisos de la persona (sin sudo).',
    ('dcasa_barras', 'dcasa.barras', 'etiqueta'):
        'API del Escáner › Asignar: exige stock.group_stock_manager y product.group_product_manager en el servidor '
        'ANTES de leer; solo lee con los permisos de la persona (sin sudo).',
    ('dcasa_barras', 'dcasa.barras', 'asignar_etiqueta'):
        'API del Escáner › Asignar: exige stock.group_stock_manager y product.group_product_manager en el servidor '
        'ANTES de escribir; el producto se escribe con los permisos de la persona (sin sudo); el único sudo es leer '
        'si un empaque ya usa el código y escribir el historial, después de comprobar el permiso; tomar una etiqueta '
        'ajena o retirada exige que la persona haya visto su estado actual.',
    ('dcasa_barras', 'dcasa.barras', 'quitar_etiqueta'):
        'API del Escáner › Asignar: exige stock.group_stock_manager y product.group_product_manager en el servidor '
        'ANTES de escribir; el producto se escribe con los permisos de la persona; solo el historial usa sudo.',
    ('dcasa_barras', 'product.product', 'write'):
        OVERRIDE + ' Solo anota en el historial de etiquetas (con sudo, sin cambiar permisos ni valores) cuando cambia '
                   'el código de barras.',
    ('dcasa_barras', 'product.product', 'unlink'):
        OVERRIDE + ' Solo anota en el historial de etiquetas el código del producto que se elimina; no cambia '
                   'permisos.',
    ('dcasa_barras', 'dcasa.barras.etiqueta', 'write'): 'Bloquea: el historial de etiquetas no se edita.',
    ('dcasa_barras', 'dcasa.barras.etiqueta', 'unlink'): 'Bloquea: el historial de etiquetas no se borra.',
    ('dcasa_barras', 'dcasa.barras.asignacion', 'action_revisar'):
        'Botón: exige stock.group_stock_manager y escritura sobre el registro; no cambia productos (la lista de '
        'líneas la arma con sudo, solo con lo que ya leyó).',
    ('dcasa_barras', 'dcasa.barras.asignacion', 'action_aplicar'):
        'Botón: exige stock.group_stock_manager y product.group_product_manager y escritura sobre el registro; vuelve '
        'a comprobar cada producto y nunca pisa un código existente; el producto se escribe con los permisos de la '
        'persona (sin sudo; solo las líneas de la lista se escriben con sudo).',
    ('dcasa_barras', 'dcasa.barras.asignacion', 'action_deshacer'):
        'Botón: exige stock.group_stock_manager y escritura sobre el registro; quita solo lo que sigue igual a lo '
        'asignado.',
    # --- dcasa_fe_pa (factura electrónica DGI) ------------------------------------------------
    ('dcasa_fe_pa', 'dcasa.fe.documento', 'action_procesar'):
        'Botón: exige account.group_account_invoice antes del sudo (envía al PAC).',
    ('dcasa_fe_pa', 'dcasa.fe.documento', 'action_reintentar'):
        'Botón: exige account.group_account_invoice antes del sudo (regenera un rechazado).',
    ('dcasa_fe_pa', 'dcasa.fe.documento', 'action_anular'): ACCION_VENTANA + ' El asistente exige Facturación.',
    ('dcasa_fe_pa', 'dcasa.fe.documento', 'write'):
        'Bloquea: número, punto, tipo y factura no cambian; un autorizado solo pasa a anulado (ACL solo lectura).',
    ('dcasa_fe_pa', 'dcasa.fe.documento', 'unlink'): 'Bloquea: los documentos electrónicos no se borran.',
    ('dcasa_fe_pa', 'dcasa.fe.intento', 'write'): 'Bloquea: el histórico de intentos no se edita.',
    ('dcasa_fe_pa', 'dcasa.fe.intento', 'unlink'): 'Bloquea: el histórico de intentos no se borra.',
    ('dcasa_fe_pa', 'dcasa.fe.anular.wizard', 'action_confirmar'):
        ASISTENTE + ' (Facturación); además exige account.group_account_invoice antes del sudo.',
    ('dcasa_fe_pa', 'account.move', 'button_draft'):
        OVERRIDE + ' Solo agrega el bloqueo si la factura ya existe ante la DGI; lee con sudo, no escribe.',
    ('dcasa_fe_pa', 'account.move', 'button_cancel'):
        OVERRIDE + ' Solo agrega el bloqueo si la factura ya existe ante la DGI; lee con sudo, no escribe.',
    ('dcasa_fe_pa', 'account.move', 'action_l10n_pa_fe_procesar'):
        'Delega en dcasa.fe.documento.action_procesar, que exige account.group_account_invoice.',
    # --- dcasa_interfaz -----------------------------------------------------------------
    ('dcasa_interfaz', 'dcasa.tablero', 'obtener_datos'):
        SIN_SUDO + ' Cada bloque del tablero pregunta has_access antes de leer.',
    ('dcasa_interfaz', 'dcasa.tablero', 'ventas_del_periodo'):
        'Lectura. Pregunta has_access de pedidos; quien vende sin controlar ve solo lo suyo, y la ganancia solo '
        'sale con el grupo de Gerencia o de administrador (la lee con sudo ya comprobado ese grupo).',
    ('dcasa_interfaz', 'product.product', 'dcasa_accion_sin_movimiento'):
        'Lectura: exige Gerencia o administrador en el servidor (AccessError si no) y solo devuelve una acción de '
        'ventana con un filtro; no escribe ni usa sudo().',
    ('dcasa_guia', 'dcasa.guia', 'obtener'):
        SIN_SUDO + ' Solo devuelve las tareas de la Guía cuyo menú (y los de arriba) ve quien pregunta; el catálogo '
        'es un archivo del repositorio, sin datos del negocio.',
    ('dcasa_guia', 'dcasa.guia', 'buscar'):
        SIN_SUDO + ' Busca solo entre las tareas que quien pregunta puede abrir; el texto buscado no toca la base.',
    ('dcasa_guia', 'dcasa.guia', 'registrar_uso'):
        SIN_SUDO + ' Anota «+1» solo para quien llama y solo de una tarea que existe y que esa persona puede abrir; '
        'cualquier otra cosa devuelve False sin error. La regla de registro de dcasa.guia.uso deja a cada quien la '
        'suya.',
    ('dcasa_interfaz', 'dcasa.sitio', 'vista_previa'):
        'Solo devuelve la URL pública del sitio (web.base.url, ya visible en cualquier enlace) y su nombre.',
    # El sitio se edita por código (models/sitio.py): solo AGREGAN un bloqueo, nunca un permiso.
    ('dcasa_interfaz', 'ir.ui.view', 'create'): 'Bloquea: ninguna copia por sitio de una plantilla de D\'CASA.',
    ('dcasa_interfaz', 'ir.ui.view', 'write'): 'Bloquea: las plantillas de D\'CASA no se editan desde el panel.',
    ('dcasa_interfaz', 'ir.ui.view', 'unlink'): 'Bloquea: las plantillas de D\'CASA no se borran desde el panel.',
    ('dcasa_interfaz', 'website.page', 'open_website_url'):
        OVERRIDE + ' Devuelve la acción de la vista previa propia con la URL de la página; sin sudo().',
    ('dcasa_interfaz', 'website.page', 'write'):
        'Bloquea: de una página de D\'CASA solo se cambia publicar y SEO; el contenido viene del código.',
    ('dcasa_interfaz', 'res.users', 'create'):
        OVERRIDE + ' Solo deja «Notificación: En Odoo» al usuario interno recién creado, con los mismos permisos de '
        'quien lo crea; sin sudo().',
    # --- dcasa_invoice -------------------------------------------------------------------
    ('dcasa_invoice', 'ir.qweb.field.monetary', 'value_to_html'): OVERRIDE + ' Solo formatea un valor.',
    ('dcasa_invoice', 'account.move.line', 'get_section_subtotal'):
        OVERRIDE + ' Solo suma los importes de las piezas del título de un combo; lectura, sin sudo().',
    ('dcasa_invoice', 'account.move.line', 'get_section_total'):
        OVERRIDE + ' Solo suma los importes de las piezas del título de un combo; lectura, sin sudo().',
    # «Imprimir documentos»: el PDF solo sale por /dcasa/paquete.pdf con los permisos de quien lo pide (sin sudo).
    ('dcasa_invoice', 'account.move', 'action_dcasa_imprimir_documentos'):
        ACCION_VENTANA + ' Solo facturas de clientes publicadas; el cuadro corre sin sudo.',
    ('dcasa_invoice', 'sale.order', 'action_dcasa_imprimir_documentos'):
        ACCION_VENTANA + ' Solo facturas de clientes publicadas; el cuadro corre sin sudo.',
    ('dcasa_invoice', 'dcasa.impresion.paquete', 'action_imprimir'):
        ASISTENTE + ' (Facturación o lector contable). Solo devuelve la acción que pide el PDF al servidor.',
    ('dcasa_invoice', 'dcasa.impresion.paquete', 'action_descargar'):
        ASISTENTE + ' (Facturación o lector contable). Solo devuelve la acción que pide el PDF al servidor.',
    ('dcasa_invoice', 'dcasa.impresion.paquete', 'action_cerrar'):
        ASISTENTE + ' (Facturación o lector contable). Solo devuelve la acción de cerrar o la del pago.',
    ('dcasa_invoice', 'account.payment.register', 'action_create_payments'):
        OVERRIDE + ' Solo ofrece el cuadro «Imprimir documentos» si la factura quedó pagada; un fallo no deshace '
        'el pago.',
    ('dcasa_invoice', 'dcasa.facturas.panel', 'obtener_datos'):
        SIN_SUDO + ' Las tarjetas de proveedores solo salen para contabilidad, Gerencia y administradores.',
    ('dcasa_invoice', 'dcasa.facturas.panel', 'abrir'):
        SIN_SUDO + ' Exige contabilidad para proveedores; solo devuelve la acción de la lista con su dominio.',
    ('dcasa_invoice', 'product.product', 'get_product_multiline_description_sale'):
        OVERRIDE + ' Solo quita la referencia del proveedor del nombre de la línea si la empresa lo pide; sin sudo().',
    # --- dcasa_socios -------------------------------------------------------------------
    ('dcasa_socios', 'res.partner', 'create'): OVERRIDE,
    ('dcasa_socios', 'res.partner', 'write'): OVERRIDE,
    ('dcasa_socios', 'res.partner', 'action_dcasa_crear_ficha'): 'Botón: exige sales_team.group_sale_salesman (S-01).',
    ('dcasa_socios', 'res.partner', 'action_dcasa_ver_movimientos'): ACCION_VENTANA,
    ('dcasa_socios', 'res.partner', 'action_dcasa_ajustar'): 'Botón: exige sales_team.group_sale_manager (S-01).',
    ('dcasa_socios', 'res.partner', 'action_dcasa_reiniciar_pin'):
        'Botón: exige sales_team.group_sale_manager y deja nota en el chatter (S-01).',
    ('dcasa_socios', 'res.partner', 'action_dcasa_desbloquear'):
        'Botón: exige sales_team.group_sale_manager y deja nota en el chatter (S-01). '
        'El login de /socios usa el privado _dcasa_desbloquear.',
    ('dcasa_socios', 'res.partner', 'action_dcasa_suspender'): 'Botón: exige sales_team.group_sale_manager (S-01).',
    ('dcasa_socios', 'res.partner', 'action_dcasa_activar'): 'Botón: exige sales_team.group_sale_manager (S-01).',
    ('dcasa_socios', 'dcasa.canje', 'action_entregar'): 'Botón: exige sales_team.group_sale_salesman (S-02).',
    ('dcasa_socios', 'dcasa.canje', 'action_cancelar'): 'Botón: exige sales_team.group_sale_salesman (S-02).',
    ('dcasa_socios', 'dcasa.compra', 'action_anular'): ACCION_VENTANA + ' El asistente es solo de gerencia.',
    ('dcasa_socios', 'dcasa.movimiento', 'write'): 'Bloquea: el libro de puntos no se edita.',
    ('dcasa_socios', 'dcasa.movimiento', 'unlink'): 'Bloquea: el libro de puntos no se borra.',
    ('dcasa_socios', 'sale.order.line', 'create'):
        OVERRIDE + ' Rechaza (AccessError) que quien no sea Gerencia ni el sistema escriba la marca de premio '
                   'canjeado; sin sudo().',
    ('dcasa_socios', 'sale.order.line', 'write'):
        OVERRIDE + ' Rechaza (AccessError) que quien no sea Gerencia ni el sistema escriba la marca de premio '
                   'canjeado; sin sudo().',
    ('dcasa_socios', 'sale.order.line', 'unlink'):
        OVERRIDE + ' Al quitar la línea del premio de un carrito web devuelve los puntos (sudo solo sobre el '
                   'canje de esa línea, ya autorizada por el ACL de la línea).',
    ('dcasa_socios', 'dcasa.ajuste.wizard', 'action_confirmar'): ASISTENTE + ' (gerencia)',
    ('dcasa_socios', 'dcasa.anular.compra.wizard', 'action_confirmar'): ASISTENTE + ' (gerencia)',
    ('dcasa_socios', 'dcasa.compra.manual.wizard', 'action_confirmar'): ASISTENTE + ' (gerencia)',
    ('dcasa_socios', 'dcasa.cobrar.premio.wizard', 'action_confirmar'): ASISTENTE + ' (vendedora)',
    ('dcasa_socios', 'account.move', 'button_draft'):
        OVERRIDE + ' Comprueba check_access("write") antes de anular puntos con sudo.',
    ('dcasa_socios', 'account.move', 'button_cancel'):
        OVERRIDE + ' Comprueba check_access("write") antes de anular puntos con sudo.',
    ('dcasa_socios', 'account.move', 'unlink'):
        OVERRIDE + ' Comprueba check_access("unlink") antes de anular con sudo los puntos y la comisión de un borrador '
                   'que se borra, y solo después de que Odoo aceptó borrarlo.',
    ('website_dcasa', 'sale.order', 'action_quotation_sent'): OVERRIDE + ' Solo agrega la fecha del apartado.',
    ('dcasa_socios', 'sale.order', 'action_confirm'):
        OVERRIDE + ' Comprueba check_access("write") antes de sellar premios con sudo.',
    ('dcasa_socios', 'sale.order', 'action_dcasa_cobrar_premio'): ACCION_VENTANA,
    # --- dcasa_socios: programa de vendedores ---------------------------------------------
    ('dcasa_socios', 'res.partner', 'action_dcasa_afiliar_vendedor'):
        'Botón: exige sales_team.group_sale_salesman en el servidor; solo abre el asistente.',
    ('dcasa_socios', 'res.partner', 'action_dcasa_suspender_vendedor'):
        'Botón: exige sales_team.group_sale_manager en el servidor.',
    ('dcasa_socios', 'res.partner', 'action_dcasa_reactivar_vendedor'):
        'Botón: exige sales_team.group_sale_manager en el servidor.',
    ('dcasa_socios', 'res.partner', 'action_dcasa_ajustar_vendedor'):
        'Botón: exige sales_team.group_sale_manager en el servidor; solo abre el asistente.',
    ('dcasa_socios', 'res.partner', 'action_dcasa_ver_movimientos_vendedor'): ACCION_VENTANA,
    ('dcasa_socios', 'dcasa.vend.canje', 'action_entregar'):
        'Botón: exige sales_team.group_sale_salesman en el servidor (igual que el canje de socios).',
    ('dcasa_socios', 'dcasa.vend.canje', 'action_cancelar'):
        'Botón: exige sales_team.group_sale_salesman en el servidor (igual que el canje de socios).',
    ('dcasa_socios', 'dcasa.vend.movimiento', 'write'): 'Bloquea: el libro de vendedores no se edita.',
    ('dcasa_socios', 'dcasa.vend.movimiento', 'unlink'): 'Bloquea: el libro de vendedores no se borra.',
    ('dcasa_socios', 'dcasa.afiliar.vendedor.wizard', 'action_confirmar'):
        ASISTENTE + ' (vendedora; la afiliación exige sales_team.group_sale_salesman en el servidor).',
    ('dcasa_socios', 'dcasa.vend.ajuste.wizard', 'action_confirmar'): ASISTENTE + ' (gerencia)',
    ('dcasa_socios', 'sale.order', 'create'):
        OVERRIDE + ' Solo anota quién escribió el código de vendedor.',
    ('dcasa_socios', 'sale.order', 'write'):
        OVERRIDE + ' Confirmada la venta, solo Gerencia cambia el vendedor, y nunca con una comisión ya pagada.',
    ('dcasa_socios', 'account.move', 'write'):
        OVERRIDE + ' Publicada la factura, solo Gerencia cambia el vendedor, y nunca con una comisión ya pagada.',
    # --- dcasa_socios: Ajustes › Programa de vendedores (Gerencia cambia las cifras; solo hacia adelante) ---------
    ('dcasa_socios', 'dcasa.vend.reglas', 'create'):
        OVERRIDE + ' Solo numera la versión y exige que rija hacia adelante; el ACL no deja crear a nadie (la crea '
                   'el servidor con sudo, después de exigir Gerencia o administrador).',
    ('dcasa_socios', 'dcasa.vend.reglas', 'write'): 'Bloquea: el historial de reglas no se edita.',
    ('dcasa_socios', 'dcasa.vend.reglas', 'unlink'): 'Bloquea: el historial de reglas no se borra.',
    ('dcasa_socios', 'dcasa.vend.ajustes', 'default_get'):
        OVERRIDE + ' Exige Gerencia o administrador (_exigir_gerencia) ANTES de leer las reglas; solo devuelve las '
                   'cifras de la pantalla.',
    ('dcasa_socios', 'dcasa.vend.ajustes', 'execute'):
        'Botón «Guardar»: exige Gerencia o administrador en el servidor ANTES de escribir; vuelve a convertir y a '
        'validar las cifras y solo entonces crea la versión (con sudo).',
    ('dcasa_socios', 'dcasa.vend.ajustes', 'cancel'): ACCION_VENTANA,
    ('dcasa_socios', 'dcasa.vend.ajustes', 'action_dcasa_vend_fabrica'):
        'Botón: exige Gerencia o administrador en el servidor ANTES de crear la versión de fábrica (con sudo).',
    ('dcasa_socios', 'dcasa.vend.ajustes', 'action_dcasa_vend_historial'):
        ACCION_VENTANA + ' Exige Gerencia o administrador.',
    ('dcasa_socios', 'dcasa.vend.ajustes.mixin', 'action_dcasa_vend_fabrica'):
        'Botón del molde de la pantalla de ajustes: exige Gerencia o administrador en el servidor ANTES de escribir.',
    ('dcasa_socios', 'dcasa.vend.ajustes.mixin', 'action_dcasa_vend_historial'):
        ACCION_VENTANA + ' Exige Gerencia o administrador.',
    ('dcasa_socios', 'res.config.settings', 'action_dcasa_vend_fabrica'):
        'Botón del bloque en Ajustes (solo administradores por ACL): exige Gerencia o administrador en el servidor '
        'ANTES de crear la versión de fábrica (con sudo).',
    ('dcasa_socios', 'res.config.settings', 'action_dcasa_vend_historial'):
        ACCION_VENTANA + ' Exige Gerencia o administrador.',
    ('dcasa_socios', 'res.config.settings', 'get_values'):
        OVERRIDE + ' Agrega las cifras del programa de vendedores solo si quien abre es Gerencia o administrador; '
                   'res.config.settings es solo de administradores.',
    ('dcasa_socios', 'res.config.settings', 'set_values'):
        OVERRIDE + ' Después de los ajustes estándar entrega las cifras a dcasa.vend.reglas, que exige Gerencia o '
                   'administrador y valida todo; res.config.settings es solo de administradores.',
    # --- dcasa_tienda_borde ----------------------------------------------------------------
    # Solo anotan «página pendiente» (dcasa.tienda.pendiente, tabla interna sin ACL de escritura)
    # en el precommit; el registro del usuario se escribe sin sudo, con su propio ACL.
    ('dcasa_tienda_borde', 'product.template', 'create'): OVERRIDE + ' Anota la marca de la tienda del borde.',
    ('dcasa_tienda_borde', 'product.template', 'write'): OVERRIDE + ' Anota la marca de la tienda del borde.',
    ('dcasa_tienda_borde', 'product.template', 'unlink'): OVERRIDE + ' Anota la marca de la tienda del borde.',
    ('dcasa_tienda_borde', 'product.product', 'write'): OVERRIDE + ' Anota la marca de la tienda del borde.',
    ('dcasa_tienda_borde', 'product.template.attribute.value', 'write'):
        OVERRIDE + ' Anota la marca de la tienda del borde.',
    ('dcasa_tienda_borde', 'product.public.category', 'create'): OVERRIDE + ' Marca «regenerar todo».',
    ('dcasa_tienda_borde', 'product.public.category', 'write'): OVERRIDE + ' Marca «regenerar todo».',
    ('dcasa_tienda_borde', 'product.public.category', 'unlink'): OVERRIDE + ' Marca «regenerar todo».',
    ('dcasa_tienda_borde', 'website', 'write'): OVERRIDE + ' Marca «regenerar todo».',
    ('dcasa_tienda_borde', 'ir.config_parameter', 'create'):
        OVERRIDE + ' Marca «regenerar todo» si es un parámetro de Black Weekend (ACL: solo group_system).',
    ('dcasa_tienda_borde', 'ir.config_parameter', 'write'):
        OVERRIDE + ' Marca «regenerar todo» si es un parámetro de Black Weekend (ACL: solo group_system).',
    ('dcasa_tienda_borde', 'ir.config_parameter', 'unlink'):
        OVERRIDE + ' Marca «regenerar todo» si es un parámetro de Black Weekend (ACL: solo group_system).',
    ('dcasa_tienda_borde', 'ir.ui.view', 'create'): OVERRIDE + ' Marca «regenerar todo» si es QWeb.',
    ('dcasa_tienda_borde', 'ir.ui.view', 'write'): OVERRIDE + ' Marca «regenerar todo» si es QWeb.',
    ('dcasa_tienda_borde', 'ir.ui.view', 'unlink'): OVERRIDE + ' Marca «regenerar todo» si es QWeb.',
    ('dcasa_tienda_borde', 'website.menu', 'create'): OVERRIDE + ' Marca «regenerar todo».',
    ('dcasa_tienda_borde', 'website.menu', 'write'): OVERRIDE + ' Marca «regenerar todo».',
    ('dcasa_tienda_borde', 'website.menu', 'unlink'): OVERRIDE + ' Marca «regenerar todo».',
    ('dcasa_tienda_borde', 'website.page', 'create'): OVERRIDE + ' Marca «regenerar todo».',
    ('dcasa_tienda_borde', 'website.page', 'write'): OVERRIDE + ' Marca «regenerar todo».',
    ('dcasa_tienda_borde', 'website.page', 'unlink'): OVERRIDE + ' Marca «regenerar todo».',
    ('dcasa_tienda_borde', 'product.pricelist.item', 'create'): OVERRIDE + ' Marca «regenerar todo».',
    ('dcasa_tienda_borde', 'product.pricelist.item', 'write'): OVERRIDE + ' Marca «regenerar todo».',
    ('dcasa_tienda_borde', 'product.pricelist.item', 'unlink'): OVERRIDE + ' Marca «regenerar todo».',
    # --- dcasa_brian ----------------------------------------------------------------------
    # El chat del panel: ACL de group_user + regla «cada quien sus conversaciones»; los
    # métodos validan dueño de la conversación y de la acción (B-04).
    ('dcasa_brian', 'brian.conversacion', 'estado_proveedor'): 'Exige base.group_user; nunca devuelve la clave.',
    ('dcasa_brian', 'brian.conversacion', 'estado_panel'):
        'Exige base.group_user; cada pastilla pregunta has_access y lee sin sudo (reglas de registro); '
        'el único sudo cuenta las claves de API del PROPIO usuario.',
    ('dcasa_brian', 'brian.conversacion', 'mis_conversaciones'): SIN_SUDO,
    ('dcasa_brian', 'brian.conversacion', 'nueva'): SIN_SUDO,
    ('dcasa_brian', 'brian.conversacion', 'historial'): 'Solo conversaciones propias (_propia lanza AccessError).',
    ('dcasa_brian', 'brian.conversacion', 'enviar'): 'Valida dueño de la conversación (_verificar_duenio).',
    ('dcasa_brian', 'brian.conversacion', 'confirmar_accion'):
        'Único camino público para confirmar: valida dueño de la conversación y de la acción (B-04).',
    ('dcasa_brian', 'brian.conversacion', 'rechazar_accion'): 'Valida dueño de la conversación y de la acción.',
    ('dcasa_brian', 'brian.conversacion', 'archivar'): 'Valida dueño de la conversación.',
    ('dcasa_brian', 'brian.conversacion', 'renombrar'):
        'Valida dueño de la conversación (_verificar_duenio); recorta a 60 caracteres; sin sudo.',
    ('dcasa_brian', 'brian.conversacion', 'write'):
        OVERRIDE + ' Impide cambiar dueño (usuario_id) y canal salvo superusuario; sin sudo.',
    ('dcasa_brian', 'brian.conversacion', 'unlink'):
        OVERRIDE + ' Valida dueño ANTES de cerrar con sudo SUS acciones por confirmar; el borrado '
        'corre sin sudo (ACL + regla «cada quien sus conversaciones»).',
    ('dcasa_brian', 'brian.mensaje', 'write'):
        OVERRIDE + ' Impide mover un mensaje a otra conversación (historial falso); sin sudo.',
    ('dcasa_brian', 'brian.accion', 'create'): 'Bloquea: solo el sistema escribe la auditoría (ACL solo lectura).',
    ('dcasa_brian', 'brian.accion', 'write'): 'Bloquea: la auditoría no se edita.',
    ('dcasa_brian', 'brian.accion', 'unlink'): 'Bloquea: la auditoría no se borra.',
    ('dcasa_brian', 'brian.accion', 'argumentos_dict'): SIN_SUDO,
    ('dcasa_brian', 'res.config.settings', 'set_values'): OVERRIDE + ' res.config.settings es solo de administradores.',
    ('dcasa_brian', 'res.config.settings', 'action_dcasa_brian_probar'): 'Exige base.group_system (gasta la clave).',
    ('dcasa_brian', 'res.config.settings', 'action_dcasa_brian_borrar_clave'): 'Exige base.group_system.',
    ('dcasa_brian', 'brian.telegram.enlace', 'action_vincular'): 'Genera el código del propio usuario interno.',
    ('dcasa_brian', 'brian.telegram.enlace', 'action_desvincular'):
        'Solo el dueño del chat o un administrador (se comprueba antes del sudo).',
    ('dcasa_brian', 'brian.telegram.enlace', 'action_registrar_webhook'): 'Exige base.group_system.',
    ('dcasa_brian', 'res.users', 'action_dcasa_brian_vincular_telegram'): 'Solo sobre el propio usuario.',
    ('dcasa_brian', 'res.users', 'write'):
        OVERRIDE + ' Después del write estándar (que ya exige permisos), si se archiva al usuario apaga sus chats de '
                   'Telegram; no devuelve datos.',
    # --- dcasa_conversaciones (Juan, el asistente de clientes) ---------------------------------
    # Todo lo que escribe con sudo() (registrar mensajes, estado, seguimiento, tokens) es privado (_ o @api.private)
    # y solo lo llama la API /dcasa/juan/v1 (con token) o el propio módulo. Lo público de abajo:
    ('dcasa_conversaciones', 'dcasa.conversacion', 'write'):
        OVERRIDE + ' Bloquea cambiar canal e id externo (salvo superusuario); sin sudo.',
    ('dcasa_conversaciones', 'dcasa.conversacion', 'unlink'):
        OVERRIDE + ' Comprueba check_access("unlink") ANTES de borrar los mensajes con sudo (derecho de borrado).',
    ('dcasa_conversaciones', 'dcasa.conversacion', 'action_atender'): VENTAS_BOTON,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'action_devolver_al_bot'): VENTAS_BOTON,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'action_cerrar'): VENTAS_BOTON,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'action_enviar'): VENTAS_BOTON,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'action_reintentar_envios'): VENTAS_BOTON,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'action_crear_oportunidad'): VENTAS_BOTON,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'action_ver_oportunidad'): ACCION_VENTANA,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'lista'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'hilo'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'refrescar'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'ficha'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'marcar_leida'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'enviar_respuesta'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'tomar'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'devolver'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'cerrar'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'eliminar'): PANEL_GERENCIA,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'documentos_del_cliente'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'cancelar_programado'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'adjuntar_a_documento'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'asignar'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'cancelar_seguimiento'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'poner_etiquetas'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'agregar_nota'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'buscar_catalogo'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'cotizaciones_abiertas'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'crear_cotizacion'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'descartar_adjunto'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'enviar_cotizacion'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'enviar_foto_catalogo'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'equipo'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'fotos_catalogo'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'iniciar_panel'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'fijar_disponible'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'presencia'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'resumir_conversacion'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'nueva_oportunidad'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'preparar_foto_catalogo'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'reintentar_envios_panel'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'subir_adjunto'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.conversacion', 'sugerir_respuesta'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.juan.panel', 'resumen'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.juan.panel', 'costos'): PANEL_GERENCIA,
    ('dcasa_conversaciones', 'dcasa.juan.panel', 'por_persona'): PANEL_GERENCIA,
    ('dcasa_conversaciones', 'dcasa.juan.panel', 'reparto'):
        PANEL_VENTAS + ' Cada vendedora recibe solo lo suyo; el equipo completo solo viaja si es de Gerencia.',
    ('dcasa_conversaciones', 'dcasa.juan.panel', 'fijar_fuera_del_reparto'):
        'Solo Gerencia (sales_team.group_sale_manager, comprobado en el servidor antes de escribir con sudo): saca a '
        'una persona del reparto o la vuelve a meter; no toca permisos y deja nota en el historial de los ajustes.',
    ('dcasa_conversaciones', 'dcasa.juan.panel', 'fijar_modo_reparto'):
        'Solo Gerencia (sales_team.group_sale_manager, comprobado en el servidor antes de escribir con sudo): '
        'enciende o apaga el reparto de Ajustes de Juan; el campo lleva seguimiento (queda quién y cuándo).',
    ('dcasa_conversaciones', 'dcasa.juan.panel', 'conexiones'): PANEL_GERENCIA,
    ('dcasa_conversaciones', 'dcasa.juan.panel', 'qr'): PANEL_GERENCIA,
    ('dcasa_conversaciones', 'dcasa.juan.panel', 'reiniciar_puente'): PANEL_GERENCIA,
    ('dcasa_conversaciones', 'dcasa.juan.panel', 'desvincular_puente'): PANEL_GERENCIA,
    ('dcasa_conversaciones', 'dcasa.mensaje', 'write'): 'Bloquea: el historial de la conversación no se edita.',
    ('dcasa_conversaciones', 'dcasa.mensaje', 'unlink'):
        OVERRIDE + ' Tras el unlink estándar (ACL y reglas de registro) borra con sudo la copia del mensaje en la '
                   'ficha del cliente (Ley 81); no devuelve datos.',
    ('dcasa_conversaciones', 'crm.lead', 'write'):
        OVERRIDE + ' Marca «una persona tomó el control» cuando alguien cambia etapa o temperatura a mano; escribe '
                   'con los permisos del usuario (ACL y reglas de registro de crm.lead).',
    ('dcasa_conversaciones', 'crm.lead', 'action_dcasa_devolver_control'):
        'Botón: devuelve la oportunidad al CRM automático escribiendo con los permisos del usuario (ACL y reglas de '
        'crm.lead).',
    ('dcasa_conversaciones', 'dcasa.mensaje', 'action_reintentar'): VENTAS_BOTON,
    ('dcasa_conversaciones', 'dcasa.mensaje', 'marcar_sensible'):
        'Exige sales_team.group_sale_salesman; busca los mensajes SIN sudo, así que solo marca adjuntos de mensajes '
        'que esa persona puede ver; solo escribe la marca de sensible.',
    ('dcasa_conversaciones', 'dcasa.juan.ajustes', 'create'): 'Bloquea: los ajustes son un solo registro; sin sudo.',
    ('dcasa_conversaciones', 'dcasa.juan.ajustes', 'unlink'): 'Bloquea: los ajustes no se borran.',
    ('dcasa_conversaciones', 'dcasa.juan.ajustes', 'action_abrir'):
        ACCION_VENTANA + ' Comprueba check_access("read") antes.',
    ('dcasa_conversaciones', 'dcasa.juan.ajustes', 'action_cargar_ejemplos'):
        ('Botón solo de staging: exige Gerencia y existencias de prueba en el servidor; crea filas ficticias '
         'y no escribe en ningún canal.'),
    ('dcasa_conversaciones', 'dcasa.juan.ajustes', 'action_probar_conexion'):
        'Botón: exige sales_team.group_sale_manager; solo pregunta la salud del Worker (sin enviar datos del cliente).',
    ('dcasa_conversaciones', 'dcasa.conocimiento', 'create'):
        OVERRIDE + ' Solo Gerencia crea (ACL); si nace de una pregunta, la marca atendida con sudo.',
    ('dcasa_conversaciones', 'dcasa.conocimiento', 'write'):
        OVERRIDE + ' Pone la fecha de revisión; sin sudo (ACL: Gerencia).',
    ('dcasa_conversaciones', 'dcasa.conocimiento', 'action_activar'): 'Botón: exige sales_team.group_sale_manager.',
    ('dcasa_conversaciones', 'dcasa.conocimiento', 'action_desactivar'): 'Botón: exige sales_team.group_sale_manager.',
    ('dcasa_conversaciones', 'dcasa.pregunta_pendiente', 'write'):
        'Bloquea: solo Gerencia atiende las preguntas sin respuesta (se comprueba antes de escribir).',
    ('dcasa_conversaciones', 'dcasa.pregunta_pendiente', 'action_convertir_en_conocimiento'):
        'Botón: exige sales_team.group_sale_manager; solo devuelve la acción de ventana.',
    ('dcasa_conversaciones', 'dcasa.pregunta_pendiente', 'action_descartar'):
        'Botón: exige sales_team.group_sale_manager.',
    ('dcasa_conversaciones', 'dcasa.pregunta_pendiente', 'action_reabrir'):
        'Botón: exige sales_team.group_sale_manager.',
    ('dcasa_conversaciones', 'dcasa.conversacion.etiqueta', 'create'):
        OVERRIDE + ' Solo limpia el nombre; sin sudo (ACL: solo Gerencia crea).',
    ('dcasa_conversaciones', 'dcasa.conversacion.etiqueta', 'write'):
        OVERRIDE + ' Solo limpia el nombre; sin sudo (ACL: solo Gerencia escribe).',
    ('dcasa_conversaciones', 'dcasa.conversacion.etiqueta', 'lista'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.respuesta.rapida', 'create'):
        OVERRIDE + ' Solo limpia el atajo; sin sudo (ACL: solo Gerencia crea).',
    ('dcasa_conversaciones', 'dcasa.respuesta.rapida', 'write'):
        OVERRIDE + ' Solo limpia el atajo; sin sudo (ACL: solo Gerencia escribe).',
    ('dcasa_conversaciones', 'dcasa.respuesta.rapida', 'lista'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'dcasa.respuesta.rapida', 'texto_para'): PANEL_VENTAS,
    ('dcasa_conversaciones', 'res.partner', 'action_dcasa_ver_conversaciones'): ACCION_VENTANA,
}

# Modelos abstractos sin ACL: por RPC no se puede llamar NINGÚN método suyo (S-09).
SIN_SUPERFICIE = ('brian.herramientas', 'brian.proveedores', 'brian.politica', 'dcasa.mantenimiento',
                  'dcasa.fe.pac', 'dcasa.fe.pac.simulado')


def es_publico(modelo, nombre):
    try:
        get_public_method(modelo, nombre)
    except (AccessError, AttributeError):
        return False
    return True


def metodos_de_dcasa(env):
    """{(módulo, modelo, método)} definidos en addons/ e invocables por RPC."""
    encontrados = set()
    for nombre_modelo in env.registry:
        modelo = env[nombre_modelo]
        for clase in type(modelo).mro():
            if not clase.__module__.startswith(PREFIJOS):
                continue
            modulo = clase.__module__.split('.')[2]
            for nombre, valor in vars(clase).items():
                if nombre.startswith('_') or not inspect.isfunction(valor):
                    continue
                if es_publico(modelo, nombre):
                    encontrados.add((modulo, nombre_modelo, nombre))
    return encontrados


@tagged('post_install', '-at_install')
class TestSuperficieRpc(TransactionCase):

    def test_metodos_publicos_en_lista_blanca(self):
        encontrados = metodos_de_dcasa(self.env)
        nuevos = sorted(encontrados - set(LISTA_BLANCA))
        self.assertFalse(nuevos, (
            'Métodos públicos (invocables por RPC) que no están en la lista blanca. Hazlos privados '
            '(_nombre o @api.private) o exige el grupo en el servidor y anótalos con su motivo en '
            f'LISTA_BLANCA: {nuevos}'))

    def test_lista_blanca_al_dia(self):
        """Una entrada que ya no es pública (o ya no existe) se borra: la lista no se pudre."""
        instalados = set(self.env['ir.module.module'].search([('state', '=', 'installed')]).mapped('name'))
        encontrados = metodos_de_dcasa(self.env)
        viejas = sorted(clave for clave in LISTA_BLANCA if clave[0] in instalados and clave not in encontrados)
        self.assertFalse(viejas, f'Entradas de LISTA_BLANCA que ya no son públicas: {viejas}')

    def test_motivo_en_cada_entrada(self):
        for clave, motivo in LISTA_BLANCA.items():
            self.assertTrue(motivo and len(motivo) > 10, f'{clave} necesita un motivo')

    def test_ningun_boton_de_las_vistas_llama_a_un_metodo_api_model(self):
        """Un botón ``type="object"`` llama con ``[ids]`` (vacía en la cabecera de una lista sin filas marcadas); un
        método ``@api.model`` no acepta ese argumento y falla con «takes 1 positional argument but 2 were given».
        Así falló «Vincular mi Telegram» en producción. Los métodos de botón van SIN ``@api.model`` (``self`` puede
        venir vacío)."""
        datos = self.env['ir.model.data'].search([
            ('model', '=', 'ir.ui.view'), '|', ('module', '=like', 'dcasa_%'), ('module', '=', 'website_dcasa')])
        vistas = self.env['ir.ui.view'].browse(datos.mapped('res_id')).exists()
        revisados, culpables = 0, []
        for vista in vistas:
            if not vista.model or vista.model not in self.env:
                continue
            raiz = etree.fromstring(vista.arch_db.encode())
            for boton in raiz.xpath('//button[@type="object"][@name]'):
                modelo = vista.model
                # Un botón dentro de <field name="x"><list>…</list></field> es del modelo relacionado.
                for campo in reversed([a for a in boton.iterancestors() if a.tag == 'field']):
                    definicion = self.env[modelo]._fields.get(campo.get('name'))
                    modelo = definicion.comodel_name if definicion and definicion.comodel_name else modelo
                metodo = getattr(type(self.env[modelo]), boton.get('name'), None)
                if metodo is None:
                    continue
                revisados += 1
                if getattr(metodo, '_api_model', False):
                    culpables.append(f'{modelo}.{boton.get("name")} (vista {vista.get_external_id().get(vista.id)})')
        self.assertTrue(revisados, 'La prueba no encontró ningún botón: ya no revisa nada')
        self.assertFalse(culpables, f'Botones ligados a métodos @api.model (quita el decorador): {sorted(culpables)}')

    def test_abstractos_sin_acl_no_exponen_nada(self):
        """S-09: brian.herramientas, brian.proveedores y brian.politica: nada propio por RPC."""
        for nombre_modelo in SIN_SUPERFICIE:
            if nombre_modelo not in self.env:
                continue
            modelo = self.env[nombre_modelo]
            for clase in type(modelo).mro():
                if not clase.__module__.startswith(PREFIJOS):
                    continue
                for nombre, valor in vars(clase).items():
                    if inspect.isfunction(valor):
                        self.assertFalse(es_publico(modelo, nombre), f'{nombre_modelo}.{nombre} es público')
