"""A quién va cada campaña (etapa 2, decisión de la dueña, 2026-11-06): chips del CRM que se combinan, siempre cruzados
con el permiso, la baja y el tope de 15 días POR CLIENTE.

* **Los chips** (``reglas.CHIPS``) se suman: quien cae en cualquiera de los elegidos entra. «Todos con permiso» es todo
  el que dijo que sí.

  - **Compraron** en los últimos 90 días: una factura de cliente publicada o una venta confirmada.
  - **Volver a traerlos**: compraron alguna vez y la última compra fue hace más de 6 meses.
  - **Cotizaron o preguntaron y no compraron**: una cotización o una oportunidad de los últimos 90 días y ninguna
    compra en esos 90 días.
  - **Tibios** y **calientes**: la misma temperatura del CRM que usan Juan y Sofía (``crm.lead.dcasa_temperatura``),
    en una oportunidad abierta.
  - **Recién agregados**: la ficha se creó en los últimos 30 días. **De hace más de un año**: se creó hace más de 365.
* **Quién queda fuera y por qué**: sin correo bien escrito; se dio de baja (o pidió que no lo contacten) en cualquier
  ficha con ese correo; no dijo que sí (o lo dijo con otro correo); o ya le llegó una campaña hace menos de 15 días.
  Se cuenta por correo (una persona, una vez).
* **El tope por cliente**: un correo que recibió una campaña (``dcasa.camila.destinatario``) desde el comienzo del día
  de Panamá de hace 14 días no recibe otra (si le salió el 6, la próxima puede ser desde el 21). Una campaña
  «enviada» dentro de esa ventana que NO tiene registro (las de la etapa 1, de antes del registro) cuenta para TODOS:
  no se sabe a quién le llegó. La migración ``19.0.2.0.0`` les escribe el registro con los que tenían permiso.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.addons.dcasa_conversaciones.models import crm_reglas as CRM
from odoo.addons.dcasa_correo.models.correo import correo_valido

from . import reglas as R

DIAS_COMPRA = 90
DIAS_VOLVER = 180
DIAS_COTIZO = 90
DIAS_NUEVOS = 30
DIAS_ANTIGUOS = 365
MOTIVOS_FUERA = [
    ('reciente', 'Ya les llegó una campaña hace menos de 15 días'),
    ('sin_permiso', 'No han dicho que sí (o lo dijeron con otro correo)'),
    ('baja', 'Se dieron de baja o pidieron que no los contacten'),
    ('sin_correo', 'Sin un correo bien escrito'),
]


class _TodosLosCorreos:
    """«Ya le llegó una hace menos de 15 días» vale para cualquier correo (una enviada sin registro de a quién)."""

    def __contains__(self, _correo):
        return True


class DcasaCamila(models.AbstractModel):
    _inherit = 'dcasa.camila'

    # ------------------------------------------------------------------
    # El tope de 15 días por cliente
    # ------------------------------------------------------------------

    @api.model
    def _corte_por_cliente(self):
        """Desde cuándo una campaña recibida cuenta para el tope (UTC sin zona): el comienzo del día de Panamá de hace
        ``DIAS_ENTRE_CAMPANAS - 1`` días."""
        zona = ZoneInfo('America/Panama')
        dia = self._ahora_panama().date() - timedelta(days=R.DIAS_ENTRE_CAMPANAS - 1)
        return datetime.combine(dia, time.min, tzinfo=zona).astimezone(ZoneInfo('UTC')).replace(tzinfo=None)

    @api.model
    def _enviadas_sin_registro(self, excepto=None):
        """Las campañas enviadas dentro del tope que no tienen registro de a quién salieron (las de la etapa 1)."""
        dominio = [('estado', '=', 'enviada'), ('enviada_en', '>=', self._corte_por_cliente()),
                   ('destinatario_ids', '=', False)]
        if excepto:
            dominio.append(('id', '!=', excepto.id))
        return self.env['dcasa.camila.campana'].sudo().search(dominio)

    @api.model
    def _registrar_enviadas_sin_registro(self):
        """(Migración 19.0.2.0.0.) A las enviadas dentro del tope sin registro se les anotan los correos que HOY tienen
        permiso, con su fecha de envío: lo conservador (alguno quizá no la recibió). Devuelve cuántas filas escribió."""
        enviadas = self._enviadas_sin_registro()
        if not enviadas:
            return 0
        permitidos = self.env['res.partner'].sudo()._dcasa_promos_con_permiso()
        filas = self.env['dcasa.camila.destinatario'].sudo().create([
            {'campana_id': campana.id, 'correo': correo, 'partner_id': ficha.id, 'enviada_en': campana.enviada_en}
            for campana in enviadas for correo, ficha in permitidos.items()])
        return len(filas)

    @api.model
    def _correos_recientes(self, excepto=None):
        """Los correos que recibieron una campaña dentro del tope (sin contar la campaña ``excepto``)."""
        dominio = [('enviada_en', '>=', self._corte_por_cliente())]
        if excepto:
            dominio.append(('campana_id', '!=', excepto.id))
        return set(self.env['dcasa.camila.destinatario'].sudo().search(dominio).mapped('correo'))

    # ------------------------------------------------------------------
    # Los chips
    # ------------------------------------------------------------------

    @api.model
    def _compras(self, desde=None):
        """``{ficha comercial: fecha de su última compra}`` (facturas publicadas y ventas confirmadas)."""
        compras = {}
        dominio_factura = [('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]
        dominio_venta = [('state', '=', 'sale')]
        if desde:
            dominio_factura.append(('invoice_date', '>=', desde))
            dominio_venta.append(('date_order', '>=', datetime.combine(desde, time.min)))
        for ficha, fecha in self.env['account.move'].sudo()._read_group(
                dominio_factura, ['commercial_partner_id'], ['invoice_date:max']):
            if ficha and fecha:
                compras[ficha.id] = max(fecha, compras.get(ficha.id, fecha))
        for partner, fecha in self.env['sale.order'].sudo()._read_group(
                dominio_venta, ['partner_id'], ['date_order:max']):
            if partner and fecha:
                ficha, dia = partner.commercial_partner_id.id, fecha.date()
                compras[ficha] = max(dia, compras.get(ficha, dia))
        return compras

    @api.model
    def _fichas_del_chip(self, chip):
        """Las fichas comerciales (ids) de un chip. ``None`` para «todos» (todo el que tiene permiso)."""
        hoy = self._ahora_panama().date()
        ahora = fields.Datetime.now()
        if chip == 'todos':
            return None
        if chip == 'compraron':
            return set(self._compras(hoy - timedelta(days=DIAS_COMPRA)))
        if chip == 'volver':
            limite = hoy - timedelta(days=DIAS_VOLVER)
            return {ficha for ficha, ultima in self._compras().items() if ultima < limite}
        if chip == 'cotizaron':
            desde = hoy - timedelta(days=DIAS_COTIZO)
            fichas = {p.commercial_partner_id.id for p in self.env['sale.order'].sudo().search(
                [('state', 'in', ('draft', 'sent', 'cancel')), ('date_order', '>=', datetime.combine(desde, time.min))]
            ).partner_id}
            fichas |= {p.commercial_partner_id.id for p in self.env['crm.lead'].sudo().with_context(
                active_test=False).search([('create_date', '>=', datetime.combine(desde, time.min)),
                                           ('partner_id', '!=', False)]).partner_id}
            return fichas - set(self._compras(desde))
        if chip in ('tibios', 'calientes'):
            temperatura = CRM.TIBIO if chip == 'tibios' else CRM.CALIENTE
            leads = self.env['crm.lead'].sudo().search([
                ('type', '=', 'opportunity'), ('active', '=', True), ('won_status', '=', 'pending'),
                ('dcasa_temperatura', '=', temperatura), ('partner_id', '!=', False)])
            return {p.commercial_partner_id.id for p in leads.partner_id}
        Partner = self.env['res.partner'].sudo()
        if chip == 'nuevos':
            return set(Partner.search([('parent_id', '=', False),
                                       ('create_date', '>=', ahora - timedelta(days=DIAS_NUEVOS))]).ids)
        if chip == 'antiguos':
            return set(Partner.search([('parent_id', '=', False),
                                       ('create_date', '<', ahora - timedelta(days=DIAS_ANTIGUOS))]).ids)
        return set()

    # ------------------------------------------------------------------
    # El público de una campaña
    # ------------------------------------------------------------------

    @api.model
    def _publico(self, chips, campana=None):
        """``{incluidos: {correo: ficha}, total, chips: [{clave, nombre, n, activo}], fuera: [{motivo, texto, n}]}``.

        ``campana``: la que se va a enviar (lo que ella misma ya registró no cuenta para su propio tope)."""
        chips = R.leer_chips(chips)
        Partner = self.env['res.partner'].sudo()
        permitidos = Partner._dcasa_promos_con_permiso()
        recientes = self._correos_recientes(excepto=campana)
        if self._enviadas_sin_registro(excepto=campana):
            recientes = _TodosLosCorreos()   # salió una sin registro hace menos de 15 días: a nadie todavía
        bloqueos = Partner._dcasa_promos_bloqueos_por_correo()
        del_equipo = Partner._dcasa_correos_del_equipo()
        incluidos, fuera, por_chip = {}, {motivo: set() for motivo, _t in MOTIVOS_FUERA}, {}

        def clasificar(fichas):
            """Las fichas de un chip, por correo: ``(incluidos {correo: ficha}, fuera {motivo: {claves}})``."""
            dentro, afuera = {}, {motivo: set() for motivo, _t in MOTIVOS_FUERA}
            if fichas is None:
                for correo, ficha in permitidos.items():
                    if correo in recientes:
                        afuera['reciente'].add(correo)
                    else:
                        dentro[correo] = ficha
                return dentro, afuera
            for ficha in Partner.browse(sorted(fichas)).exists():
                correo = correo_valido(ficha.email)
                if not correo:
                    afuera['sin_correo'].add(f'ficha:{ficha.id}')
                elif correo in del_equipo:
                    continue
                elif bloqueos.get(correo):
                    afuera['baja'].add(correo)
                elif correo not in permitidos:
                    afuera['sin_permiso'].add(correo)
                elif correo in recientes:
                    afuera['reciente'].add(correo)
                else:
                    dentro.setdefault(correo, permitidos[correo])
            return dentro, afuera

        # Todos los chips se cuentan (el número en vivo de cada uno, aunque no esté elegido); solo los elegidos suman.
        for clave, _nombre in R.CHIPS:
            dentro, afuera = clasificar(self._fichas_del_chip(clave))
            por_chip[clave] = len(dentro)
            if clave not in chips:
                continue
            incluidos.update({c: f for c, f in dentro.items() if c not in incluidos})
            for motivo, claves in afuera.items():
                fuera[motivo] |= claves
        # Quien entró por un chip no cuenta como «fuera» por otro; un correo que queda fuera en varios chips se cuenta
        # una vez (son conjuntos).
        for claves in fuera.values():
            claves -= set(incluidos)
        return {
            'incluidos': incluidos,
            'total': len(incluidos),
            'chips': [{'clave': clave, 'nombre': nombre, 'activo': clave in chips, 'n': por_chip.get(clave)}
                      for clave, nombre in R.CHIPS],
            'fuera': [{'motivo': motivo, 'texto': texto, 'n': len(fuera[motivo])}
                      for motivo, texto in MOTIVOS_FUERA if fuera[motivo]],
        }

    @api.model
    def _publico_para_pantalla(self, campana):
        """El público sin los correos (la pantalla solo ve cuántos)."""
        datos = self._publico(campana.publico, campana=campana)
        return {'chips': datos['chips'], 'total': datos['total'], 'fuera': datos['fuera'],
                'elegidos': R.leer_chips(campana.publico)}
