"""Asignar el código de barras a los productos que no lo tienen, a partir de su referencia interna.

Hoy ningún producto del catálogo tiene código de barras y casi todos tienen referencia (p. ej. ``XHT022-T-W``): sin
código el lector no tiene qué reconocer. Los muebles de proveedor casi nunca traen EAN, así que se usa la referencia
tal cual (Code 128 la admite).

Reglas (docs/BARRAS.md):

* Solo donde el código de barras está vacío: **nunca se pisa uno que ya existe**.
* Una referencia repetida en dos productos, o igual al código que ya tiene otro, **no se asigna**: se informa.
* Las medidas (Twin, Full, Queen, King) son variantes con su propia referencia, así que quedan con códigos distintos.
* Sin referencia no hay de dónde sacar el código: se informa (hay que completarla antes).
* Solo caracteres imprimibles sin espacios (letras, números y símbolos): lo demás no lo escribe bien un lector.
* Se revisa antes de aplicar, se puede repetir sin miedo y se puede deshacer (solo lo que sigue igual a lo asignado).
"""
from odoo import api, fields, models, tools
from odoo.exceptions import AccessError, UserError, ValidationError

DECISIONES = [
    ('asignar', "Se asigna"),
    ('ya_tiene', "Ya tiene código"),
    ('sin_referencia', "Sin referencia interna"),
    ('repetida', "Referencia repetida en otro producto"),
    ('usada', "Ese código ya lo tiene otro producto"),
    ('caracteres', "Caracteres no válidos para un lector"),
    ('error', "No se pudo guardar"),
]


def _imprimible(codigo):
    """Letras, números y símbolos del teclado, sin espacios (0x21–0x7E)."""
    return bool(codigo) and all(0x21 <= ord(c) <= 0x7E for c in codigo)


def planear_codigos(productos, codigos_usados=()):
    """Decide qué pasa con cada producto. Sin base de datos, para poder probarlo a fondo.

    ``productos``: ``[{'id', 'default_code', 'barcode'}]`` de los productos activos; ``codigos_usados``: códigos de
    barras que ya tiene cualquier producto (incluso archivado). Devuelve ``{id: (decisión, código)}``.
    """
    usados = {c.upper() for c in codigos_usados if c}
    decision = {}
    candidatos = {}
    for fila in productos:
        if fila.get('barcode'):
            decision[fila['id']] = ('ya_tiene', fila['barcode'])
            continue
        codigo = (fila.get('default_code') or '').strip()
        if not codigo:
            decision[fila['id']] = ('sin_referencia', '')
        elif not _imprimible(codigo):
            decision[fila['id']] = ('caracteres', codigo)
        else:
            candidatos.setdefault(codigo.upper(), []).append((fila['id'], codigo))
    for clave, pares in candidatos.items():
        for producto_id, codigo in pares:
            if len(pares) > 1:
                decision[producto_id] = ('repetida', codigo)
            elif clave in usados:
                decision[producto_id] = ('usada', codigo)
            else:
                decision[producto_id] = ('asignar', codigo)
    return decision


class DcasaBarrasAsignacion(models.Model):
    _name = 'dcasa.barras.asignacion'
    _description = "Asignación de códigos de barras"
    _order = 'id desc'

    estado = fields.Selection(
        [('borrador', "Por revisar"), ('aplicada', "Aplicada"), ('deshecha', "Deshecha")],
        default='borrador', required=True, readonly=True, copy=False)
    company_id = fields.Many2one('res.company', required=True, readonly=True, default=lambda s: s.env.company)
    usuario_id = fields.Many2one('res.users', string="Quién", readonly=True, default=lambda s: s.env.user)
    linea_ids = fields.One2many('dcasa.barras.asignacion.linea', 'asignacion_id', string="Productos", readonly=True)
    n_asignar = fields.Integer(string="Se asignan", compute='_compute_cuentas')
    n_asignados = fields.Integer(string="Asignados", compute='_compute_cuentas')
    n_ya_tienen = fields.Integer(string="Ya tenían", compute='_compute_cuentas')
    n_sin_referencia = fields.Integer(string="Sin referencia", compute='_compute_cuentas')
    n_repetidas = fields.Integer(string="Repetidas", compute='_compute_cuentas')
    n_otros = fields.Integer(string="Otros", compute='_compute_cuentas')

    @api.depends('linea_ids.decision', 'linea_ids.resultado')
    def _compute_cuentas(self):
        for asignacion in self:
            decisiones = asignacion.linea_ids.mapped('decision')
            asignacion.n_asignar = decisiones.count('asignar')
            asignacion.n_asignados = len(asignacion.linea_ids.filtered(lambda linea: linea.resultado == 'asignado'))
            asignacion.n_ya_tienen = decisiones.count('ya_tiene')
            asignacion.n_sin_referencia = decisiones.count('sin_referencia')
            asignacion.n_repetidas = decisiones.count('repetida') + decisiones.count('usada')
            asignacion.n_otros = decisiones.count('caracteres') + decisiones.count('error')

    @api.depends('create_date', 'estado')
    def _compute_display_name(self):
        for asignacion in self:
            fecha = fields.Datetime.context_timestamp(asignacion, asignacion.create_date) if asignacion.create_date \
                else None
            asignacion.display_name = self.env._("Códigos de barras %s", fecha.strftime('%Y-%m-%d %H:%M')) \
                if fecha else self.env._("Códigos de barras (nueva)")

    def _exigir_gerencia(self):
        """Gerencia: administra Inventario y Productos (el código se escribe en el producto, con sus permisos)."""
        self.check_access('write')
        if not self.env.su and not (self.env.user.has_group('stock.group_stock_manager')
                                    and self.env.user.has_group('product.group_product_manager')):
            raise AccessError(self.env._(
                "Solo Gerencia (administradores de Inventario y de Productos) puede asignar códigos de barras."))

    # ------------------------------------------------------------------
    def action_revisar(self):
        """Mira todos los productos activos y arma la lista de lo que se haría. No cambia ningún producto."""
        self.ensure_one()
        self._exigir_gerencia()
        if self.estado != 'borrador':
            raise UserError(self.env._("Esta asignación ya se aplicó. Crea otra para volver a revisar."))
        Producto = self.env['product.product']
        activos = Producto.search_read([], ['default_code', 'barcode'])
        todos = Producto.with_context(active_test=False).search_read([('barcode', '!=', False)], ['barcode'])
        plan = planear_codigos(activos, [fila['barcode'] for fila in todos])
        self.linea_ids.sudo().unlink()
        self.env['dcasa.barras.asignacion.linea'].sudo().create([
            {'asignacion_id': self.id, 'producto_id': producto_id, 'decision': decision, 'codigo': codigo}
            for producto_id, (decision, codigo) in plan.items()
        ])

    def action_aplicar(self):
        """Escribe el código de barras donde sigue vacío. Antes de cada uno vuelve a comprobar que nadie se lo puso."""
        self.ensure_one()
        self._exigir_gerencia()
        if self.estado != 'borrador':
            raise UserError(self.env._("Esta asignación ya se aplicó."))
        self.env['product.product'].check_access('write')
        pendientes = self.linea_ids.filtered(lambda linea: linea.decision == 'asignar' and not linea.resultado)
        if not pendientes:
            raise UserError(self.env._("No hay nada por asignar. Pulsa «Revisar productos» primero."))
        Producto = self.env['product.product']
        for linea in pendientes:
            producto = linea.producto_id
            try:
                with self.env.cr.savepoint():
                    if producto.barcode:
                        linea.sudo().write({'decision': 'ya_tiene', 'codigo': producto.barcode})
                        continue
                    if (producto.default_code or '').strip() != linea.codigo:
                        linea.sudo().write({'decision': 'error'})   # le cambiaron la referencia después de revisar
                        continue
                    if Producto.search_count([('default_code', '=ilike', tools.escape_psql(linea.codigo)),
                                              ('id', '!=', producto.id)]):
                        linea.sudo().write({'decision': 'repetida'})   # apareció otro con la misma referencia
                        continue
                    if Producto.with_context(active_test=False).search_count([('barcode', '=', linea.codigo)]):
                        linea.sudo().write({'decision': 'usada'})
                        continue
                    producto.write({'barcode': linea.codigo})
                    linea.sudo().write({'resultado': 'asignado'})
            except ValidationError:   # Odoo rechazó el código (p. ej. ya lo usa un empaque); un AccessError sí se ve
                linea.sudo().write({'decision': 'error'})
        self.estado = 'aplicada'

    def action_deshacer(self):
        """Quita el código solo a los productos que siguen con el código que se les asignó."""
        self.ensure_one()
        self._exigir_gerencia()
        if self.estado != 'aplicada':
            raise UserError(self.env._("Solo se puede deshacer una asignación aplicada."))
        for linea in self.linea_ids.filtered(lambda linea: linea.resultado == 'asignado'):
            if linea.producto_id.barcode == linea.codigo:
                linea.producto_id.write({'barcode': False})
                linea.sudo().resultado = 'deshecho'
        self.estado = 'deshecha'


class DcasaBarrasAsignacionLinea(models.Model):
    _name = 'dcasa.barras.asignacion.linea'
    _description = "Producto de una asignación de códigos de barras"
    _order = 'decision, id'

    asignacion_id = fields.Many2one('dcasa.barras.asignacion', required=True, ondelete='cascade', index=True)
    producto_id = fields.Many2one('product.product', required=True, ondelete='cascade')
    referencia = fields.Char(related='producto_id.default_code', string="Referencia")
    codigo = fields.Char(string="Código de barras")
    decision = fields.Selection(DECISIONES, required=True)
    resultado = fields.Selection([('asignado', "Asignado"), ('deshecho', "Deshecho")])
