"""«Mermas del mes»: la pantalla de Gerencia con el total del mes por código, lo comprado, el porcentaje contra el tope
(F6: 0.5 %), el año mes a mes y lo que se le puede reclamar a cada proveedor."""
from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError

from ..models.bitacora import GRUPO_AJUSTA
from ..models.merma import MOTIVOS, RECLAMABLES, limites_del_mes

MESES = ('Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre',
         'Noviembre', 'Diciembre')


def _dinero(valor):
    return f'${valor:,.2f}'


class DcasaMermaResumen(models.TransientModel):
    _name = 'dcasa.merma.resumen'
    _description = 'Mermas del mes'

    mes = fields.Date('Mes', required=True, default=lambda self: fields.Date.context_today(self).replace(day=1),
                      help='Cualquier día del mes que quieres ver.')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    titulo = fields.Char(compute='_compute_cifras')
    total = fields.Monetary('Mermas, daños, muestras y regalos', compute='_compute_cifras')
    merma = fields.Monetary('Merma', compute='_compute_cifras')
    dano = fields.Monetary('Daño', compute='_compute_cifras')
    muestra = fields.Monetary('Muestra', compute='_compute_cifras')
    regalo = fields.Monetary('Regalo', compute='_compute_cifras')
    compras = fields.Monetary('Lo comprado en el mes', compute='_compute_cifras',
                              help='Lo que entró a la bodega desde proveedores (recepciones validadas), a su costo y '
                                   'sin ITBMS, menos lo devuelto.')
    porcentaje = fields.Float('Porcentaje de lo comprado', compute='_compute_cifras', digits=(5, 2))
    tope = fields.Float('Tope de la gerencia (%)', compute='_compute_cifras', digits=(5, 2))
    pasa = fields.Boolean(compute='_compute_cifras')
    cantidad = fields.Integer('Registros', compute='_compute_cifras')
    sin_compras = fields.Boolean(compute='_compute_cifras')
    faltan_cuentas = fields.Char(compute='_compute_cifras')
    pendientes = fields.Integer('Esperando su asiento', compute='_compute_cifras')
    total_anio = fields.Monetary('En el año', compute='_compute_cifras')
    tabla_anio = fields.Html(compute='_compute_cifras', sanitize=False)
    tabla_proveedores = fields.Html(compute='_compute_cifras', sanitize=False)

    @api.depends('mes', 'company_id')
    def _compute_cifras(self):
        Scrap = self.env['stock.scrap']
        for resumen in self:
            mes = (resumen.mes or fields.Date.context_today(self)).replace(day=1)
            datos = Scrap._dcasa_resumen_mes(resumen.company_id, mes)
            config = self.env['dcasa.existencias.config']._de(resumen.company_id)
            resumen.titulo = f'{MESES[mes.month - 1]} {mes.year}'
            resumen.total = datos['total']
            for clave, _nombre in MOTIVOS:
                resumen[clave] = datos['por_motivo'][clave]
            resumen.compras = datos['compras']
            resumen.porcentaje = datos['pct'] or 0.0
            resumen.tope = datos['tope']
            resumen.pasa = datos['pasa']
            resumen.cantidad = datos['cantidad']
            resumen.sin_compras = not datos['compras']
            resumen.faltan_cuentas = ', '.join(config._faltan_cuentas_mermas())
            resumen.pendientes = Scrap.sudo().search_count([
                ('company_id', '=', resumen.company_id.id), ('state', '=', 'done'),
                ('dcasa_contabilidad', 'in', ('falta_cuenta', 'error'))])
            resumen.tabla_anio, resumen.total_anio = resumen._tabla_anio(mes)
            resumen.tabla_proveedores = resumen._tabla_proveedores(mes)

    def _tabla_anio(self, mes):
        """El año del mes elegido, mes a mes hasta ese mes: mermas, comprado y porcentaje (marca los que pasan)."""
        Scrap = self.env['stock.scrap']
        filas, total = [], 0.0
        for numero in range(1, mes.month + 1):
            datos = Scrap._dcasa_resumen_mes(self.company_id, mes.replace(month=numero))
            total += datos['total']
            pct = f'{datos["pct"]:g} %' if datos['pct'] is not None else ('—' if not datos['total'] else 'sin compras')
            clase = ' class="o_dcasa_merma_pasa"' if datos['pasa'] else ''
            filas.append(Markup('<tr%s><td>%s</td><td class="text-end">%s</td><td class="text-end">%s</td>'
                                '<td class="text-end">%s</td></tr>') % (
                Markup(clase), MESES[numero - 1], _dinero(datos['total']), _dinero(datos['compras']), pct))
        tabla = Markup(
            '<table class="table table-sm o_dcasa_merma_tabla"><thead><tr><th>Mes</th><th class="text-end">Mermas'
            '</th><th class="text-end">Comprado</th><th class="text-end">%%</th></tr></thead><tbody>%s</tbody>'
            '<tfoot><tr><th>Año</th><th class="text-end">%s</th><th/><th/></tr></tfoot></table>') % (
            Markup('').join(filas), _dinero(total))
        return tabla, round(total, 2)

    def _tabla_proveedores(self, mes):
        """Por proveedor, lo que se puede reclamar en el año (merma y daño), lo pendiente y lo ya reclamado."""
        desde, _fin = limites_del_mes(self.env, mes.replace(month=1))
        _ini, hasta = limites_del_mes(self.env, mes)
        mermas = self.env['stock.scrap'].sudo().search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'done'), ('dcasa_motivo', 'in', RECLAMABLES),
            ('date_done', '>=', desde), ('date_done', '<', hasta)])
        por_proveedor = {}
        for scrap in mermas:
            clave = scrap.dcasa_proveedor_id
            fila = por_proveedor.setdefault(clave, {'pendiente': 0.0, 'reclamado': 0.0, 'n': 0})
            fila['n'] += 1
            fila['reclamado' if scrap.dcasa_reclamo == 'reclamado' else 'pendiente'] += scrap.dcasa_costo
        if not por_proveedor:
            return Markup('<p class="text-muted mb-0">%s</p>') % self.env._(
                'En el año no hay mermas ni daños de mercancía que reclamar.')
        filas = [Markup('<tr><td>%s</td><td class="text-end">%s</td><td class="text-end">%s</td></tr>') % (
            proveedor.name or self.env._('(sin proveedor)'), _dinero(datos['pendiente']), _dinero(datos['reclamado']))
            for proveedor, datos in sorted(por_proveedor.items(), key=lambda par: -par[1]['pendiente'])]
        return Markup(
            '<table class="table table-sm o_dcasa_merma_tabla"><thead><tr><th>Proveedor</th>'
            '<th class="text-end">Por reclamar</th><th class="text-end">Reclamado</th></tr></thead><tbody>%s</tbody>'
            '</table>') % Markup('').join(filas)

    # ------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------

    def _exigir(self):
        if not self.env.su and not self.env.user.has_group(GRUPO_AJUSTA):
            raise AccessError(self.env._('Las mermas las ve Gerencia.'))

    def action_ver_mermas(self):
        self._exigir()
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.env._('Mermas de %s', self.titulo),
            'res_model': 'stock.scrap',
            'views': [(self.env.ref('dcasa_existencias.merma_list').id, 'list'),
                      (self.env.ref('dcasa_existencias.merma_form').id, 'form')],
            'domain': self.env['stock.scrap']._dcasa_dominio_mes(self.company_id, self.mes.replace(day=1)),
        }

    def action_reclamo(self):
        self._exigir()
        return {'type': 'ir.actions.act_window', 'res_model': 'dcasa.merma.reclamo', 'view_mode': 'form',
                'target': 'new', 'name': self.env._('Reclamo a un proveedor')}

    def action_contabilizar(self):
        self._exigir()
        return self.env['dcasa.existencias.config']._de(self.company_id).with_env(self.env) \
            .action_contabilizar_pendientes()

    @api.model
    def action_abrir(self):
        """El menú abre el mes en curso."""
        self._exigir()
        resumen = self.create({})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': resumen.id, 'view_mode': 'form',
                'target': 'current', 'name': self.env._('Mermas del mes')}
