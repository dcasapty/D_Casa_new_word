"""Etiquetas numeradas: un rollo de códigos del proveedor de etiquetas, cada número asignado a un producto.

Un rollo trae códigos que todavía no son de nadie (``DC0001``, ``DC0002``…). Se pega la etiqueta en la pieza de
exhibición o en la caja y, en el Escáner › Asignar, se escanea la etiqueta y se elige el producto: ese número queda como
el código de barras del producto. Si el mueble cambia, se pega otra etiqueta y se asigna: el número viejo queda
**retirado** y avisa si alguien lo escanea.

Reglas (docs/BARRAS.md):

* Solo Gerencia (administra Inventario y Productos: el código se escribe en el producto, con sus permisos).
* Un número es de un solo producto. Pasarlo a otro, o usar uno que ya estuvo retirado, pide confirmación.
* Cada cambio queda en un historial que no se edita ni se borra: qué número, de qué producto, quién y cuándo.
* Los números se guardan en mayúsculas (un lector con las mayúsculas invertidas escribe ``dc0001``); la búsqueda no
  distingue mayúsculas.
"""
from odoo import api, fields, models, tools
from odoo.exceptions import AccessError, UserError

from .asignacion import _imprimible
from .barras import LARGO_MAXIMO, limpiar_codigo


def codigo_de_etiqueta(texto):
    """Lo que leyó el lector como código de etiqueta (en mayúsculas), o ``None`` si no puede ser uno.

    Una etiqueta es corta y solo trae caracteres que el teclado escribe sin espacios; lo demás es un error de lectura o
    un texto que no es una etiqueta (un nombre de producto).
    """
    codigo = limpiar_codigo(texto)
    if not codigo or len(codigo) >= LARGO_MAXIMO or not _imprimible(codigo):
        return None
    return codigo.upper()


class DcasaBarrasEtiqueta(models.Model):
    """Historial de las etiquetas: solo se agrega, no se edita ni se borra."""
    _name = 'dcasa.barras.etiqueta'
    _description = "Historial de etiquetas de códigos de barras"
    _order = 'id desc'

    codigo = fields.Char(string="Etiqueta", required=True, readonly=True, index=True)
    accion = fields.Selection(
        [('asignada', "Asignada"), ('retirada', "Retirada")], string="Qué pasó", required=True, readonly=True)
    producto_id = fields.Many2one('product.product', string="Producto", readonly=True, ondelete='set null')
    producto_nombre = fields.Char(string="Nombre del producto", readonly=True)
    motivo = fields.Char(readonly=True)
    usuario_id = fields.Many2one('res.users', string="Quién", readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, default=lambda s: s.env.company)

    def write(self, vals):
        raise UserError(self.env._("El historial de etiquetas no se edita."))

    def unlink(self):
        raise UserError(self.env._("El historial de etiquetas no se borra."))


class DcasaBarrasEtiquetas(models.AbstractModel):
    _inherit = 'dcasa.barras'

    # ------------------------------------------------------------------
    # Permisos y ayudas
    # ------------------------------------------------------------------
    def _exigir_etiquetas(self):
        usuario = self.env.user
        if not (usuario.has_group('stock.group_stock_manager') and usuario.has_group('product.group_product_manager')):
            raise AccessError(self.env._(
                "Solo Gerencia (administradores de Inventario y de Productos) puede asignar etiquetas."))

    def _etiqueta_valida(self, texto):
        codigo = codigo_de_etiqueta(texto)
        if not codigo:
            raise UserError(self.env._(
                "Eso no se lee como una etiqueta: escanéala otra vez (sin espacios y de menos de %s caracteres).",
                LARGO_MAXIMO))
        return codigo

    def _ultimo_registro_de_etiqueta(self, codigo):
        return self.env['dcasa.barras.etiqueta'].search(
            [('codigo', '=ilike', tools.escape_psql(codigo))], order='id desc', limit=1)

    def _estado_de_etiqueta(self, codigo):
        """(``'asignada'``, producto) · (``'retirada'``, registro del historial) · (``'libre'``, ``None``)."""
        dueno = self.env['product.product'].with_context(active_test=False).search(
            [('barcode', '=ilike', tools.escape_psql(codigo))], limit=1)
        if dueno:
            return 'asignada', dueno
        ultimo = self._ultimo_registro_de_etiqueta(codigo)
        if ultimo.accion == 'retirada':
            return 'retirada', ultimo
        return 'libre', None

    def _datos_de_retiro(self, registro):
        """Lo que se le cuenta a la persona de una etiqueta retirada."""
        if not registro:
            return False
        return {
            'producto': registro.producto_nombre or '',
            'motivo': registro.motivo or '',
            'fecha': fields.Datetime.to_string(registro.create_date) if registro.create_date else '',
        }

    def _etiqueta_retirada(self, codigo):
        """Si el código es una etiqueta que se retiró (y nadie la tiene ahora): de quién era y por qué se retiró."""
        etiqueta = codigo_de_etiqueta(codigo)
        if not etiqueta:
            return False
        ultimo = self._ultimo_registro_de_etiqueta(etiqueta)
        return self._datos_de_retiro(ultimo) if ultimo.accion == 'retirada' else False

    def _anotar_etiqueta(self, codigo, accion, producto, motivo):
        # El historial solo lo escribe el sistema (el ACL de la gente es de lectura): después de comprobar el permiso.
        self.env['dcasa.barras.etiqueta'].sudo().create({
            'codigo': codigo,
            'accion': accion,
            'producto_id': producto.id,
            'producto_nombre': producto.display_name,
            'motivo': motivo,
            'usuario_id': self.env.user.id,
            'company_id': self.env.company.id,
        })

    # ------------------------------------------------------------------
    # Lo que pide la pantalla
    # ------------------------------------------------------------------
    @api.model
    def etiqueta(self, codigo):
        """¿De quién es esta etiqueta? → ``{'estado': 'libre'|'asignada'|'retirada', 'producto': ficha|None, ...}``."""
        self._exigir_etiquetas()
        codigo = self._etiqueta_valida(codigo)
        estado, dato = self._estado_de_etiqueta(codigo)
        return {
            'codigo': codigo,
            'estado': estado,
            'producto': self._ficha_de(dato) if estado == 'asignada' else None,
            'antes': self._datos_de_retiro(dato) if estado == 'retirada' else False,
        }

    @api.model
    def asignar_etiqueta(self, codigo, producto_id, confirmar=False):
        """Deja ``codigo`` como el código de barras del producto.

        Si la etiqueta es de otro producto, o estuvo retirada, no se hace nada hasta que ``confirmar`` sea verdadero:
        se devuelve ``{'resultado': 'confirmar', ...}`` para que la pantalla pregunte. Un producto que ya tenía otra
        etiqueta la deja retirada.
        """
        self._exigir_etiquetas()
        codigo = self._etiqueta_valida(codigo)
        producto = self._producto(producto_id)
        producto.check_access('write')
        confirmar = confirmar is True
        actual = producto.barcode or ''
        if actual.upper() == codigo:
            return {'resultado': 'igual', 'ficha': self._ficha_de(producto), 'etiqueta_anterior': '',
                    'dueno_anterior': ''}
        if self.env['product.uom'].sudo().search_count([('barcode', '=ilike', tools.escape_psql(codigo))], limit=1):
            raise UserError(self.env._(
                "El código %s ya lo usa el empaque de un producto: no puede ser una etiqueta.", codigo))
        estado, dato = self._estado_de_etiqueta(codigo)
        if estado == 'asignada' and not confirmar:
            return {'resultado': 'confirmar', 'motivo': 'dueno',
                    'dueno': {'id': dato.id, 'nombre': dato.display_name}, 'antes': False}
        if estado == 'retirada' and not confirmar:
            return {'resultado': 'confirmar', 'motivo': 'retirada', 'dueno': False,
                    'antes': self._datos_de_retiro(dato)}
        with self.env.cr.savepoint():
            dueno_anterior = ''
            if estado == 'asignada':
                dueno_anterior = dato.display_name
                dato.write({'barcode': False})
                self._anotar_etiqueta(
                    codigo, 'retirada', dato, self.env._("Pasó a «%s»", producto.display_name))
            if actual:
                self._anotar_etiqueta(
                    actual, 'retirada', producto, self.env._("Reemplazada por %s", codigo))
            producto.write({'barcode': codigo})
            self._anotar_etiqueta(
                codigo, 'asignada', producto,
                self.env._("Venía de «%s»", dueno_anterior) if dueno_anterior else '')
        return {'resultado': 'ok', 'ficha': self._ficha_de(producto), 'etiqueta_anterior': actual,
                'dueno_anterior': dueno_anterior}

    @api.model
    def quitar_etiqueta(self, producto_id):
        """Deja al producto sin etiqueta; el número queda retirado."""
        self._exigir_etiquetas()
        producto = self._producto(producto_id)
        producto.check_access('write')
        codigo = producto.barcode or ''
        if not codigo:
            raise UserError(self.env._("«%s» no tiene etiqueta que quitar.", producto.display_name))
        with self.env.cr.savepoint():
            producto.write({'barcode': False})
            self._anotar_etiqueta(codigo, 'retirada', producto, self.env._("Quitada a mano"))
        return {'resultado': 'ok', 'ficha': self._ficha_de(producto), 'etiqueta_anterior': codigo,
                'dueno_anterior': ''}
