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

# (módulo, modelo, método): motivo por el que puede llamarse por RPC.
LISTA_BLANCA = {
    # --- dcasa_base -------------------------------------------------------------------------
    ('dcasa_base', 'sale.order.line', 'create'):
        OVERRIDE + ' Agrega el tope de descuento de la vendedora; sin sudo().',
    ('dcasa_base', 'sale.order.line', 'write'):
        OVERRIDE + ' Agrega el tope de descuento de la vendedora; sin sudo().',
    ('website_dcasa', 'ir.qweb.field.image', 'record_to_html'):
        OVERRIDE + ' Solo agrega srcset/sizes/width/height/loading a la <img>; sin sudo().',
    ('website_dcasa', 'ir.qweb.field.image_url', 'record_to_html'):
        OVERRIDE + ' Hereda la anterior (image_url extiende image); sin sudo().',
    # --- dcasa_catalogo -----------------------------------------------------------------
    ('dcasa_catalogo', 'sale.order', 'action_dcasa_whatsapp'): SIN_SUDO,
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
    ('dcasa_contabilidad', 'dcasa.cierre.mes', 'create'): OVERRIDE + ' Normaliza el mes y arma la lista; sin sudo.',
    ('dcasa_contabilidad', 'dcasa.cierre.mes', 'write'): OVERRIDE + ' Impide mover un mes cerrado; sin sudo.',
    ('dcasa_contabilidad', 'dcasa.cierre.mes', 'action_revisar'): SIN_SUDO,
    ('dcasa_contabilidad', 'dcasa.cierre.mes', 'action_cerrar'):
        'Botón: exige account.group_account_manager ANTES de escribir la fecha de bloqueo de la empresa con sudo.',
    ('dcasa_contabilidad', 'dcasa.cierre.mes', 'action_reabrir'):
        'Botón: exige account.group_account_manager y motivo ANTES de bajar la fecha de bloqueo con sudo.',
    ('dcasa_contabilidad', 'dcasa.cierre.mes.paso', 'action_ver'): ACCION_VENTANA,
    # --- dcasa_interfaz -----------------------------------------------------------------
    ('dcasa_interfaz', 'dcasa.tablero', 'obtener_datos'):
        SIN_SUDO + ' Cada bloque del tablero pregunta has_access antes de leer.',
    # --- dcasa_invoice -------------------------------------------------------------------
    ('dcasa_invoice', 'ir.qweb.field.monetary', 'value_to_html'): OVERRIDE + ' Solo formatea un valor.',
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
    ('dcasa_socios', 'dcasa.ajuste.wizard', 'action_confirmar'): ASISTENTE + ' (gerencia)',
    ('dcasa_socios', 'dcasa.anular.compra.wizard', 'action_confirmar'): ASISTENTE + ' (gerencia)',
    ('dcasa_socios', 'dcasa.compra.manual.wizard', 'action_confirmar'): ASISTENTE + ' (gerencia)',
    ('dcasa_socios', 'dcasa.cobrar.premio.wizard', 'action_confirmar'): ASISTENTE + ' (vendedora)',
    ('dcasa_socios', 'account.move', 'button_draft'):
        OVERRIDE + ' Comprueba check_access("write") antes de anular puntos con sudo.',
    ('dcasa_socios', 'account.move', 'button_cancel'):
        OVERRIDE + ' Comprueba check_access("write") antes de anular puntos con sudo.',
    ('dcasa_socios', 'sale.order', 'action_confirm'):
        OVERRIDE + ' Comprueba check_access("write") antes de sellar premios con sudo.',
    ('dcasa_socios', 'sale.order', 'action_dcasa_cobrar_premio'): ACCION_VENTANA,
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
    # --- dcasa_brian ----------------------------------------------------------------------
    # El chat del panel: ACL de group_user + regla «cada quien sus conversaciones»; los
    # métodos validan dueño de la conversación y de la acción (B-04).
    ('dcasa_brian', 'brian.conversacion', 'estado_proveedor'): 'Exige base.group_user; nunca devuelve la clave.',
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
}

# Modelos abstractos sin ACL: por RPC no se puede llamar NINGÚN método suyo (S-09).
SIN_SUPERFICIE = ('brian.herramientas', 'brian.proveedores', 'brian.politica', 'dcasa.mantenimiento')


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
