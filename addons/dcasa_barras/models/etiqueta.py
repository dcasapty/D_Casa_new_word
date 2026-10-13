"""Etiquetas numeradas: un rollo de códigos del proveedor de etiquetas, cada número asignado a un producto.

Un rollo trae códigos que todavía no son de nadie (``DC0001``, ``DC0002``…). Se pega la etiqueta en la pieza de
exhibición o en la caja y, en el Escáner › Asignar, se escanea la etiqueta y se elige el producto: ese número queda como
el código de barras del producto. Si el mueble cambia, se pega otra etiqueta y se asigna: el número viejo queda
**retirado** y avisa si alguien lo escanea.

Reglas (docs/BARRAS.md):

* Solo Gerencia (administra Inventario y Productos: el código se escribe en el producto, con sus permisos).
* Un número es de un solo producto. Pasarlo a otro, o usar uno que ya estuvo retirado, pide confirmación, y la
  confirmación vale solo para lo que la persona vio: si la etiqueta cambió mientras tanto, se vuelve a preguntar.
* Cada cambio del código de barras de un producto queda en un historial que no se edita ni se borra (qué número, de qué
  producto, quién y cuándo), **venga de donde venga**: del Escáner, de la ficha del producto o de la asignación desde la
  referencia (``models/product.py``).
* Los números se guardan en mayúsculas (un lector con las mayúsculas invertidas escribe ``dc0001``); la búsqueda no
  distingue mayúsculas.
"""
from odoo import api, fields, models, tools
from odoo.exceptions import AccessError, UserError

from .asignacion import _imprimible
from .barras import LARGO_MAXIMO, limpiar_codigo

ESTADOS = ('libre', 'asignada', 'retirada')


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

    def _visto_valido(self, visto):
        """Lo que la pantalla le mostró: ``{'estado': …, 'dueno_id': id|False}`` → ``(estado, id|False)``."""
        if visto is None:
            return None
        dueno = (visto.get('dueno_id') or False) if isinstance(visto, dict) else None
        if (not isinstance(visto, dict) or visto.get('estado') not in ESTADOS
                or (dueno is not False and (isinstance(dueno, bool) or not isinstance(dueno, int)))):
            raise UserError(self.env._("Lo que se confirmó no se entiende: escanea la etiqueta otra vez."))
        return visto['estado'], dueno

    def _ultimo_registro_de_etiqueta(self, codigo):
        return self.env['dcasa.barras.etiqueta'].search(
            [('codigo', '=ilike', tools.escape_psql(codigo))], order='id desc', limit=1)

    def _estado_de_etiqueta(self, codigo):
        """(``'asignada'``, productos que la tienen) · (``'retirada'``, registro) · (``'libre'``, ``None``).

        Un producto archivado sigue siendo el dueño de su etiqueta (el mueble puede seguir en bodega con ella).
        """
        duenos = self.env['product.product'].with_context(active_test=False).search(
            [('barcode', '=ilike', tools.escape_psql(codigo))], order='id')
        if duenos:
            return 'asignada', duenos
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

    def _producto_archivado_con_codigo(self, codigo):
        """Si el código es de un producto archivado: su nombre (en Consultar el producto archivado no sale)."""
        producto = self.env['product.product'].with_context(active_test=False).search(
            [('barcode', '=ilike', tools.escape_psql(codigo)), ('active', '=', False)], limit=1)
        return {'producto': producto.display_name} if producto else False

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
        """¿De quién es esta etiqueta? → ``{'estado': 'libre'|'asignada'|'retirada', 'producto': ficha|None}``."""
        self._exigir_etiquetas()
        codigo = self._etiqueta_valida(codigo)
        estado, dato = self._estado_de_etiqueta(codigo)
        return {
            'codigo': codigo,
            'estado': estado,
            'producto': self._ficha_de(dato[0]) if estado == 'asignada' else None,
            'antes': self._datos_de_retiro(dato) if estado == 'retirada' else False,
        }

    @api.model
    def asignar_etiqueta(self, codigo, producto_id, visto=None):
        """Deja ``codigo`` como el código de barras del producto.

        Si la etiqueta es de otro producto, o estuvo retirada, hace falta que la persona lo haya visto: ``visto`` es lo
        que la pantalla le mostró (``{'estado': …, 'dueno_id': …}``). Si no coincide con lo que hay ahora (otra
        persona la pasó mientras tanto), no se hace nada y se devuelve ``{'resultado': 'confirmar', ...}`` para que la
        pantalla vuelva a preguntar. Un producto que ya tenía otra etiqueta la deja retirada.
        """
        self._exigir_etiquetas()
        codigo = self._etiqueta_valida(codigo)
        visto = self._visto_valido(visto)
        producto = self._producto(producto_id)
        producto.check_access('write')
        actual = producto.barcode or ''
        if actual.upper() == codigo:
            return {'resultado': 'igual', 'ficha': self._ficha_de(producto), 'etiqueta_anterior': '',
                    'dueno_anterior': ''}
        if self.env['product.uom'].sudo().search_count([('barcode', '=ilike', tools.escape_psql(codigo))], limit=1):
            raise UserError(self.env._(
                "El código %s ya lo usa el empaque de un producto: no puede ser una etiqueta.", codigo))
        estado, dato = self._estado_de_etiqueta(codigo)
        dueno_id = dato[0].id if estado == 'asignada' else False
        if estado != 'libre' and visto != (estado, dueno_id):
            return {'resultado': 'confirmar', 'motivo': 'dueno' if estado == 'asignada' else 'retirada',
                    'dueno': {'id': dueno_id, 'nombre': dato[0].display_name} if estado == 'asignada' else False,
                    'antes': self._datos_de_retiro(dato) if estado == 'retirada' else False}
        with self.env.cr.savepoint():
            dueno_anterior = ''
            if estado == 'asignada':
                dueno_anterior = ', '.join(dato.mapped('display_name'))
                # Cada cambio del código de barras lo anota el historial (models/product.py), con este motivo.
                dato.with_context(dcasa_etiqueta_retiro=self.env._("Pasó a «%s»", producto.display_name)) \
                    .write({'barcode': False})
            producto.with_context(
                dcasa_etiqueta_retiro=self.env._("Reemplazada por %s", codigo),
                dcasa_etiqueta_alta=self.env._("Venía de «%s»", dueno_anterior) if dueno_anterior else '',
            ).write({'barcode': codigo})
        return {'resultado': 'ok', 'ficha': self._ficha_de(producto), 'etiqueta_anterior': actual,
                'dueno_anterior': dueno_anterior}

    @api.model
    def quitar_etiqueta(self, producto_id, codigo):
        """Deja al producto sin etiqueta; el número queda retirado. ``codigo`` es la que se vio: si cambió, no."""
        self._exigir_etiquetas()
        codigo = self._etiqueta_valida(codigo)
        producto = self._producto(producto_id)
        producto.check_access('write')
        actual = producto.barcode or ''
        if not actual:
            raise UserError(self.env._("«%s» no tiene etiqueta que quitar.", producto.display_name))
        if actual.upper() != codigo:
            raise UserError(self.env._(
                "La etiqueta de «%s» cambió mientras tanto (ahora es %s). Escanéala otra vez.",
                producto.display_name, actual))
        producto.with_context(dcasa_etiqueta_retiro=self.env._("Quitada a mano")).write({'barcode': False})
        return {'resultado': 'ok', 'ficha': self._ficha_de(producto), 'etiqueta_anterior': actual,
                'dueno_anterior': ''}
