"""Abrir el documento al que apunta un QR de uso interno (``/dcasa/doc/<TIPO>/<REFERENCIA>``).

Lo usan la ruta web (``controllers/documento.py``, para la cámara del teléfono) y el Escáner (``dcasa_barras``). La
regla es una sola: se abre SOLO si quien escanea puede leer ese documento con sus permisos de siempre; y quien no puede
no se entera de nada del documento (ni siquiera de su cliente), solo de que no tiene permiso.
"""
from odoo import models
from odoo.tools import SQL

from .documento import LARGO_MAXIMO_REFERENCIA, TIPOS, leer_url, leer_url_tolerante, nombre_del_tipo

OK = 'ok'
SIN_PERMISO = 'sin_permiso'
NO_EXISTE = 'no_existe'

# A qué pantalla de Odoo se abre cada documento (la acción da el menú y la ruta de regreso correctos).
ACCIONES = {
    'FAC': {'out_refund': 'account.action_move_out_refund_type', None: 'account.action_move_out_invoice_type'},
    'COT': {'draft': 'sale.action_quotations_with_onboarding', 'sent': 'sale.action_quotations_with_onboarding',
            None: 'sale.action_orders'},
    'COM': {'draft': 'purchase.purchase_rfq', 'sent': 'purchase.purchase_rfq', 'to approve': 'purchase.purchase_rfq',
            None: 'purchase.purchase_form_action'},
    'ENT': {None: 'stock.action_picking_tree_all'},
}


def _comodines_escapados(texto):
    return texto.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


class DcasaDocumento(models.AbstractModel):
    _name = 'dcasa.documento'
    _description = "Abrir un documento desde su código QR"

    def _dcasa_dominio_documento(self, tipo, referencia, operador='='):
        valor = _comodines_escapados(referencia) if operador == '=ilike' else referencia
        dominio = [('name', operador, valor)]
        if tipo == 'FAC':   # solo facturas y notas de crédito de clientes (las de proveedores no llevan QR)
            dominio.append(('move_type', 'in', ['out_invoice', 'out_refund']))
        return dominio

    def _dcasa_ids_por_clave(self, tipo, clave):
        """Los documentos (de cualquier empresa) cuyo número, solo con letras y números, es ``clave`` (sin permisos)."""
        modelo = self.env[TIPOS[tipo][0]]
        solo_clientes = SQL(" AND move_type IN ('out_invoice', 'out_refund')") if tipo == 'FAC' else SQL()
        self.env.cr.execute(SQL(
            "SELECT id FROM %s WHERE regexp_replace(upper(name), '[^0-9A-Z]', '', 'g') = %s%s LIMIT 5",
            SQL.identifier(modelo._table), clave, solo_clientes))
        return [fila[0] for fila in self.env.cr.fetchall()]

    def _dcasa_buscar_documento(self, tipo, referencia, tolerante=False):
        """``(estado, registro)``: ``ok`` con el documento, ``sin_permiso`` o ``no_existe`` (registro vacío).

        Quien no es del equipo (un cliente con acceso al portal) nunca abre nada por aquí; y quien sí lo es solo abre lo
        que sus permisos le dejan leer. No existir y no poder verlo se distinguen SOLO para el equipo.

        ``tolerante``: ``referencia`` es la clave solo con letras y números (``leer_url_tolerante``): un lector con la
        distribución del teclado equivocada cambió los símbolos y se busca por lo que sí llegó.
        """
        tipo = (tipo or '').upper()
        if tipo not in TIPOS or not isinstance(referencia, str) or not referencia.strip() \
                or len(referencia) > LARGO_MAXIMO_REFERENCIA:
            return NO_EXISTE, self.env['account.move']
        modelo = self.env[TIPOS[tipo][0]]
        vacio = modelo.browse()
        if not self.env.user._is_internal() or not modelo.has_access('read'):
            return SIN_PERMISO, vacio
        referencia = referencia.strip()
        if tolerante:
            ids = self._dcasa_ids_por_clave(tipo, referencia)
            registro = modelo.search([('id', 'in', ids)], limit=1) if ids else vacio
            if registro:
                return OK, registro
            return (SIN_PERMISO if ids else NO_EXISTE), vacio
        for operador in ('=', '=ilike'):    # primero igual; si no, sin distinguir mayúsculas (un lector las invierte)
            registro = modelo.search(self._dcasa_dominio_documento(tipo, referencia, operador), limit=1)
            if registro:
                return OK, registro
        existe = modelo.sudo().with_context(active_test=False).search_count(
            self._dcasa_dominio_documento(tipo, referencia, '=ilike'), limit=1)
        return (SIN_PERMISO if existe else NO_EXISTE), vacio

    def _dcasa_mensaje_documento(self, estado, tipo):
        nombre = nombre_del_tipo(tipo)
        if estado == SIN_PERMISO:
            return self.env._(
                "No tienes permiso para ver esta %(documento)s. Si la necesitas, pídele acceso a quien administra el "
                "sistema.", documento=nombre)
        return self.env._(
            "No encontramos ese documento (%(documento)s) en el sistema. Revisa que el código QR sea de este sistema.",
            documento=nombre)

    def _dcasa_ruta_odoo(self, registro):
        """``/odoo/action-<id de la acción>/<id del documento>``: el formulario del documento dentro de su menú."""
        registro.ensure_one()
        por_estado = ACCIONES[next(t for t, (modelo, _n) in TIPOS.items() if modelo == registro._name)]
        clave = registro.move_type if registro._name == 'account.move' else registro.state
        xmlid = por_estado.get(clave) or por_estado[None]
        accion = self.env.ref(xmlid, raise_if_not_found=False)
        if accion:
            return f'/odoo/action-{accion.id}/{registro.id}'
        return f'/odoo/{registro._name}/{registro.id}'

    def _dcasa_accion_documento(self, registro):
        """La acción con que el Escáner abre el documento: su formulario. Otro módulo la cambia (dcasa_barras abre la
        nota de entrega en el panel de Bodega para quien usa Inventario)."""
        return registro.get_formview_action()

    def _dcasa_resolver_texto(self, texto):
        """Lo que el Escáner hace con lo que leyó: ``None`` si no es la dirección de un documento (el Escáner sigue
        como siempre); si lo es, ``{'estado', 'tipo', 'referencia'}`` más ``mensaje`` o, si se puede abrir, ``accion``
        y ``nombre``."""
        leido = leer_url(texto)
        tolerante = False
        if not leido:    # ¿un lector con otra distribución de teclado cambió los símbolos?
            leido, tolerante = leer_url_tolerante(texto), True
        if not leido:
            return None
        tipo, referencia = leido
        estado, registro = self._dcasa_buscar_documento(tipo, referencia, tolerante=tolerante)
        resultado = {'estado': estado, 'tipo': tipo, 'tipo_nombre': nombre_del_tipo(tipo), 'referencia': referencia}
        if estado == OK:
            resultado.update(nombre=registro.display_name, accion=self._dcasa_accion_documento(registro))
        else:
            resultado['mensaje'] = self._dcasa_mensaje_documento(estado, tipo)
        return resultado
