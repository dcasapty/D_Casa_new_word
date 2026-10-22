"""Mermas, daños, muestras y regalos (F6 de DECISIONES_CONTABLES): el desecho de Odoo (``stock.scrap``) con su código.

* **Código (motivo)**: merma, daño, muestra o regalo. Obligatorio para confirmar.
* **Costo**: el del movimiento de Odoo (lo que vale la salida) o, si no lo tiene, el costo del producto por la cantidad.
  Un producto sin costo no se da de baja (F1: ningún producto con costo 0; si no, la pérdida no se vería).
* **Proveedor**: para reclamarle; se propone el primer proveedor del producto.
* **Quién**: lo crea cualquiera con Inventario (un reporte en borrador no mueve nada); **confirmarlo es de Gerencia**
  (baja la existencia: es un ajuste a mano).
* **Asiento**: con las cuentas que eligió la contadora (Ajustes de bodega), al confirmar: debe la cuenta de las mermas
  (partida propia del estado de resultados) y haber la cuenta que se rebaja. Sin cuentas, la merma queda registrada y
  el asiento «pendiente»; la pantalla lo dice y se contabiliza después con un botón.
* **Aviso del 0.5 %** (F6): el total del mes contra lo comprado en el mes (recepciones de proveedores a su costo).
"""
import logging
from datetime import datetime, time

import pytz
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain

from .bitacora import GRUPO_AJUSTA

_logger = logging.getLogger(__name__)

MOTIVOS = [('merma', 'Merma'), ('dano', 'Daño'), ('muestra', 'Muestra'), ('regalo', 'Regalo')]
# Lo que se le puede reclamar a un proveedor (una muestra o un regalo los decide la tienda).
RECLAMABLES = ('merma', 'dano')


def limites_del_mes(env, mes):
    """``(desde, hasta)`` en UTC sin zona (como guarda Odoo) del mes de ``mes`` en hora de Panamá."""
    zona = pytz.timezone(env.user.tz or 'America/Panama')
    inicio = mes.replace(day=1)
    fin = inicio + relativedelta(months=1)

    def utc(dia):
        return zona.localize(datetime.combine(dia, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
    return utc(inicio), utc(fin)


class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    dcasa_motivo = fields.Selection(MOTIVOS, 'Código (motivo)', tracking=True,
                                    help='Merma (se perdió o se echó a perder), daño, muestra o regalo.')
    dcasa_nota = fields.Text('Qué pasó', help='Para recordarlo y, si es del proveedor, para reclamarle.')
    dcasa_proveedor_id = fields.Many2one(
        'res.partner', 'Proveedor (para reclamarle)', compute='_compute_dcasa_proveedor', store=True,
        readonly=False, tracking=True)
    dcasa_reclamo = fields.Selection(
        [('por_reclamar', 'Por reclamar'), ('reclamado', 'Reclamado'), ('no_aplica', 'No se reclama')],
        'Reclamo al proveedor', compute='_compute_dcasa_reclamo', store=True, readonly=False, tracking=True)
    dcasa_costo_unitario = fields.Float('Costo unitario', readonly=True, digits='Product Price', copy=False)
    dcasa_costo = fields.Monetary('Costo', readonly=True, copy=False, currency_field='dcasa_currency_id',
                                  help='Lo que valía lo que salió, a costo y sin ITBMS.')
    dcasa_currency_id = fields.Many2one(related='company_id.currency_id')
    dcasa_contabilidad = fields.Selection(
        [('falta_cuenta', 'Falta la cuenta contable'), ('hecho', 'Contabilizada'), ('error', 'No se pudo'),
         ('odoo', 'La contabiliza Odoo (cuenta de la ubicación de desecho)')],
        'Asiento', readonly=True, copy=False)
    dcasa_asiento_id = fields.Many2one('account.move', 'Asiento contable', readonly=True, copy=False)

    @api.depends('product_id')
    def _compute_dcasa_proveedor(self):
        for scrap in self:
            if not scrap.dcasa_proveedor_id and scrap.product_id:
                scrap.dcasa_proveedor_id = scrap.product_id.sudo().seller_ids[:1].partner_id

    @api.depends('dcasa_motivo', 'dcasa_proveedor_id')
    def _compute_dcasa_reclamo(self):
        for scrap in self:
            if scrap.dcasa_reclamo == 'reclamado':
                continue
            reclamable = scrap.dcasa_motivo in RECLAMABLES and scrap.dcasa_proveedor_id
            scrap.dcasa_reclamo = 'por_reclamar' if reclamable else 'no_aplica'

    # ------------------------------------------------------------------
    # Confirmar: solo Gerencia, con motivo y con costo
    # ------------------------------------------------------------------

    def _dcasa_exigir_gerencia(self):
        if not self.env.su and not self.env.user.has_group(GRUPO_AJUSTA):
            raise AccessError(self.env._(
                'Solo Gerencia confirma una merma (baja las existencias). Déjala en borrador y avísale.'))

    def _dcasa_costo_de(self):
        """``(unitario, total)`` a costo, en la unidad del producto."""
        self.ensure_one()
        producto = self.product_id.sudo().with_company(self.company_id)
        cantidad = self.product_uom_id._compute_quantity(self.scrap_qty, producto.uom_id)
        return producto.standard_price, producto.standard_price * cantidad

    def _dcasa_validar_para_confirmar(self):
        self._dcasa_exigir_gerencia()
        for scrap in self:
            if not scrap.dcasa_motivo:
                raise UserError(self.env._('Elige el código de la salida: merma, daño, muestra o regalo.'))
            if not scrap._dcasa_costo_de()[0]:
                raise UserError(self.env._(
                    '«%s» no tiene costo cargado: ponle su costo antes de darlo de baja (sin costo la pérdida no se '
                    've en el estado de resultados).', scrap.product_id.display_name))

    def action_validate(self):
        self._dcasa_validar_para_confirmar()
        return super().action_validate()

    def do_scrap(self):
        self._dcasa_validar_para_confirmar()
        antes = {s.id: s.product_id.with_context(location=s.location_id.id).qty_available for s in self}
        resultado = super().do_scrap()
        for scrap in self.filtered(lambda s: s.state == 'done' and s.dcasa_motivo):
            valor = sum(scrap.move_ids.mapped('value'))
            unitario, total = scrap._dcasa_costo_de()
            if valor:
                total = valor
            scrap.sudo().write({'dcasa_costo_unitario': unitario, 'dcasa_costo': total})
            scrap._dcasa_anotar_en_bitacora(antes.get(scrap.id, 0.0))
        hechas = self.filtered(lambda s: s.state == 'done' and s.dcasa_motivo)
        if hechas:
            hechas._dcasa_contabilizar()
            hechas._dcasa_revisar_tope()
        return resultado

    def _dcasa_anotar_en_bitacora(self, antes):
        self.ensure_one()
        cantidad = self.product_uom_id._compute_quantity(self.scrap_qty, self.product_id.uom_id)
        motivos = dict(self._fields['dcasa_motivo']._description_selection(self.env))
        texto = motivos.get(self.dcasa_motivo, '')
        if self.dcasa_nota:
            texto = f'{texto}: {self.dcasa_nota}'
        self.env['dcasa.bitacora.bodega']._anotar([{
            'producto_id': self.product_id.id, 'ubicacion_id': self.location_id.id, 'antes': antes,
            'despues': antes - cantidad, 'diferencia': -cantidad, 'costo_unitario': self.dcasa_costo_unitario,
            'valor': -self.dcasa_costo, 'motivo': f'{self.name} · {texto}', 'origen': 'merma',
            'move_id': self.move_ids[:1].id, 'scrap_id': self.id, 'company_id': self.company_id.id,
        }])

    # ------------------------------------------------------------------
    # Asiento
    # ------------------------------------------------------------------

    def _dcasa_contabilizar(self):
        """El asiento de cada merma (si las cuentas están elegidas). Devuelve ``(hechas, fallas)``; nunca hace fallar
        la merma: lo que no se pudo queda «pendiente» o «no se pudo», con el motivo en su historial."""
        hechas = fallas = 0
        motivos = dict(self._fields['dcasa_motivo']._description_selection(self.env))
        for scrap in self:
            if scrap.dcasa_asiento_id or not scrap.dcasa_costo:
                continue
            if scrap.scrap_location_id.valuation_account_id:
                # Odoo ya lleva esta salida a la cuenta de la ubicación (al cierre de inventario o al momento): no se
                # hace un segundo asiento.
                scrap.sudo().dcasa_contabilidad = 'odoo'
                continue
            config = self.env['dcasa.existencias.config']._de(scrap.company_id)
            if config._faltan_cuentas_mermas():
                scrap.sudo().dcasa_contabilidad = 'falta_cuenta'
                continue
            nombre = f'{scrap.name} · {motivos.get(scrap.dcasa_motivo, "")} · {scrap.product_id.display_name}'
            fecha = fields.Date.context_today(scrap, scrap.date_done) if scrap.date_done else fields.Date.today()
            # Solo CREA el asiento de la merma (ya comprobado que es Gerencia): no lee asientos ni los devuelve a quien
            # vende (la regla de dcasa_base vigila los sudo() que leen asientos).
            Asiento = self.env['account.move']
            try:
                with self.env.cr.savepoint():
                    asiento = Asiento.sudo().create({
                        'move_type': 'entry', 'journal_id': config._diario_mermas().id, 'date': fecha,
                        'company_id': scrap.company_id.id, 'ref': nombre,
                        'line_ids': [
                            (0, 0, {'account_id': config.mermas_cuenta_gasto_id.id, 'name': nombre,
                                    'debit': scrap.dcasa_costo, 'credit': 0.0,
                                    'partner_id': scrap.dcasa_proveedor_id.id or False}),
                            (0, 0, {'account_id': config.mermas_cuenta_contra_id.id, 'name': nombre,
                                    'debit': 0.0, 'credit': scrap.dcasa_costo}),
                        ]})
                    asiento.action_post()
            except (UserError, AccessError) as error:
                fallas += 1
                scrap.sudo().dcasa_contabilidad = 'error'
                scrap.message_post(body=self.env._('No se pudo hacer el asiento: %s', error))
                continue
            scrap.sudo().write({'dcasa_asiento_id': asiento.id, 'dcasa_contabilidad': 'hecho'})
            hechas += 1
        return hechas, fallas

    # ------------------------------------------------------------------
    # Cifras del mes y aviso del tope
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_dominio_mes(self, company, mes):
        desde, hasta = limites_del_mes(self.env, mes)
        return [('company_id', '=', company.id), ('state', '=', 'done'), ('dcasa_motivo', '!=', False),
                ('date_done', '>=', desde), ('date_done', '<', hasta)]

    @api.model
    def _dcasa_compras_del_mes(self, company, mes):
        """Lo comprado en el mes: lo que entró a la bodega desde proveedores (recepciones validadas) a su costo, menos
        lo devuelto a proveedores. Sin ITBMS (es costo)."""
        desde, hasta = limites_del_mes(self.env, mes)
        Movimiento = self.env['stock.move'].sudo()
        base = Domain([('company_id', '=', company.id), ('state', '=', 'done'), ('date', '>=', desde),
                       ('date', '<', hasta)])
        entradas = Movimiento._read_group(base & Domain([
            ('location_id.usage', '=', 'supplier'), ('location_dest_id.usage', 'in', ('internal', 'transit'))]),
            [], ['value:sum'])[0][0] or 0.0
        devueltas = Movimiento._read_group(base & Domain([
            ('location_id.usage', 'in', ('internal', 'transit')), ('location_dest_id.usage', '=', 'supplier')]),
            [], ['value:sum'])[0][0] or 0.0
        return round(entradas - devueltas, 2)

    @api.model
    def _dcasa_resumen_mes(self, company=None, mes=None):
        """Las cifras de un mes: total y por código, lo comprado, el porcentaje y si pasa del tope."""
        company = company or self.env.company
        mes = (mes or fields.Date.context_today(self)).replace(day=1)
        mermas = self.sudo().search(self._dcasa_dominio_mes(company, mes))
        por_motivo = {clave: round(sum(mermas.filtered(lambda s, c=clave: s.dcasa_motivo == c).mapped('dcasa_costo')),
                                   2) for clave, _n in MOTIVOS}
        total = round(sum(por_motivo.values()), 2)
        compras = self._dcasa_compras_del_mes(company, mes)
        tope = self.env['dcasa.existencias.config']._de(company).mermas_tope_pct
        pct = round(100.0 * total / compras, 2) if compras else None
        pasa = bool(total) and (compras <= 0 or total > compras * tope / 100.0)
        return {'mes': mes, 'total': total, 'por_motivo': por_motivo, 'compras': compras, 'pct': pct,
                'tope': tope, 'pasa': pasa, 'cantidad': len(mermas)}

    def _dcasa_revisar_tope(self):
        """Al pasar el tope por primera vez en el mes, queda la nota en la merma (y la alerta diaria lo repite)."""
        for company in self.company_id:
            resumen = self._dcasa_resumen_mes(company, fields.Date.context_today(self))
            if not resumen['pasa']:
                continue
            marca = f'dcasa_existencias.tope_avisado.{company.id}'
            mes = resumen['mes'].strftime('%Y-%m')
            icp = self.env['ir.config_parameter'].sudo()
            if icp.get_param(marca) == mes:
                continue
            icp.set_param(marca, mes)
            for scrap in self.filtered(lambda s, c=company: s.company_id == c):
                scrap.message_post(body=self.env._(
                    'Atención: las mermas de este mes (%(total)s) ya pasan del %(tope)s %% de lo comprado '
                    '(%(compras)s).', total=f'${resumen["total"]:,.2f}', tope=f'{resumen["tope"]:g}',
                    compras=f'${resumen["compras"]:,.2f}'))
