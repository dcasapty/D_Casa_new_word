"""El CRM que se ajusta solo: la oportunidad de una conversación se mueve con hechos que Odoo ya sabe.

Pedido de la dueña (2026-10-10): que el CRM no dependa de las vendedoras. Diseño, fallas del plan y reglas:
``docs/CRM_AUTOMATICO.md``. Lo esencial, para quien toque este archivo:

* **Solo hechos**: cotización enviada, factura pagada, días sin escribir (``crm_reglas.py``). Nada que la IA «opine».
* **Solo hacia adelante** y solo en oportunidades que nacieron de una conversación (``dcasa_conversacion_ids``).
* **La persona manda**: si alguien cambia a mano la etapa o la temperatura (o restaura una oportunidad archivada), esa
  oportunidad queda con ``dcasa_auto_off`` y nada vuelve a moverla hasta que alguien lo devuelva.
* **Nada que rompa lo demás**: sin overrides en facturación, ventas ni inventario. Un cron (cada 15 min) lee los
  hechos y cada oportunidad se procesa en su propio ``savepoint``: un error se registra y no llega a quien llamó.
* **Un interruptor** (Ajustes de Juan › «El CRM se ajusta solo») apaga todo lo automático.
"""
import logging
from datetime import timedelta

from markupsafe import escape

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from . import crm_reglas as R

_logger = logging.getLogger(__name__)

ETAPA_COTIZADA = 'crm.stage_lead3'                                   # «Propuesta»
MOTIVO_SIN_RESPUESTA = 'dcasa_conversaciones.perdida_sin_respuesta'
ESTADOS_COTIZADA = ('sent', 'sale')
LOTE_DEL_CRON = 500
HORAS_SIN_CONTACTO = 24   # «a quién escribirle hoy»: ninguna vendedora le escribió en las últimas 24 horas
FACTURA_PAGADA = ('paid', 'in_payment')   # como en «Socios» y en el seguimiento: ``_dcasa_conv_ya_compro``


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    dcasa_conversacion_ids = fields.One2many(
        'dcasa.conversacion', 'oportunidad_id', string='Conversaciones', copy=False)
    dcasa_zona_entrega = fields.Char(
        'Zona de entrega', size=R.MAX_TEXTO_DATO, copy=False,
        help='Distrito o corregimiento que dijo el cliente (nunca la dirección exacta). Lo anota Juan solo con lo que '
             'el cliente dijo; no pisa lo que ya escribió una persona.')
    dcasa_para_cuando = fields.Char(
        'Para cuándo lo quiere', size=R.MAX_TEXTO_DATO, copy=False,
        help='Lo que dijo el cliente («este fin de semana», «para el 20»), con sus palabras.')
    dcasa_temperatura = fields.Selection(
        R.TEMPERATURAS, 'Temperatura', index=True, copy=False,
        help='Qué tan cerca está de comprar, con hechos (cotización, para cuándo, cuánto escribe). Se recalcula sola; '
             'si la cambias tú, queda como tú dices y deja de recalcularse.')
    dcasa_temperatura_motivo = fields.Char('Por qué', readonly=True, copy=False)
    dcasa_para_hoy = fields.Boolean(
        'A quién escribirle hoy', compute='_compute_dcasa_para_hoy', search='_search_dcasa_para_hoy',
        help='Oportunidad tibia o caliente a la que ninguna vendedora le ha escrito en las últimas 24 horas. Es lo '
             'que muestra el filtro «A quién escribirle hoy», el acceso del Inicio y Brian.')
    dcasa_auto_off = fields.Boolean(
        'Una persona tomó el control', copy=False, tracking=True,
        help='Alguien cambió la etapa o la temperatura a mano (o restauró la oportunidad). Mientras esté marcado, el '
             'CRM automático no la toca. Desmárcalo para que Juan vuelva a manejarla.')

    # ------------------------------------------------------------------
    # A quién escribirle hoy
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_dominio_para_hoy(self):
        """Pendientes, de una conversación, tibias o calientes y sin mensaje de una vendedora en las últimas 24 h.

        Juan contesta al instante: «el último mensaje es del cliente» casi nunca se cumple. Lo útil para una vendedora
        es lo que ya está tibio o caliente y nadie del equipo ha tocado.
        """
        corte = fields.Datetime.now() - timedelta(hours=HORAS_SIN_CONTACTO)
        return [
            ('type', '=', 'opportunity'), ('active', '=', True), ('won_status', '=', 'pending'),
            ('dcasa_temperatura', 'in', [R.TIBIO, R.CALIENTE]), ('dcasa_conversacion_ids', '!=', False),
            ('dcasa_conversacion_ids', 'not any', [
                ('mensaje_ids', 'any', [('autor', '=', 'vendedora'), ('ts', '>=', corte)])])]

    def _compute_dcasa_para_hoy(self):
        ids = set(self._search(Domain(self._dcasa_dominio_para_hoy()) & Domain('id', 'in', self.ids)))
        for lead in self:
            lead.dcasa_para_hoy = lead.id in ids

    def _search_dcasa_para_hoy(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(self.env._('El filtro «A quién escribirle hoy» solo se usa como sí o no.'))
        dominio = self._dcasa_dominio_para_hoy()
        if (operator == '=') == value:
            return dominio
        return [('id', 'not in', self._search(Domain(dominio)))]

    # ------------------------------------------------------------------
    # La persona manda
    # ------------------------------------------------------------------

    def write(self, vals):
        if not self.env.context.get('dcasa_auto'):
            toca_a_mano = {'stage_id', 'dcasa_temperatura'} & vals.keys() or vals.get('active') is True
            if toca_a_mano:
                vals = {'dcasa_auto_off': True, **vals}   # lo explícito gana: el botón de devolver el control
        resultado = super().write(vals)
        if {'stage_id', 'active'} & vals.keys():
            # El seguimiento depende de que la oportunidad siga viva (ganada = etapa ganadora; perdida = archivada):
            # se recalcula aquí y no solo al enviarlo. ``probability`` no entra: Odoo la reescribe a cada rato.
            self.sudo().dcasa_conversacion_ids._programar_seguimiento()
        return resultado

    def action_dcasa_devolver_control(self):
        """«Que Juan la maneje de nuevo»."""
        self.write({'dcasa_auto_off': False})
        return True

    # ------------------------------------------------------------------
    # Qué oportunidades maneja el CRM automático
    # ------------------------------------------------------------------

    def _dcasa_manejables(self):
        """Pendientes, abiertas, de una conversación y que nadie se llevó a mano."""
        return self.filtered(lambda lead: (
            lead.type == 'opportunity' and lead.active and lead.won_status == 'pending'
            and not lead.dcasa_auto_off and lead.sudo().dcasa_conversacion_ids))

    @api.model
    def _dcasa_activo(self):
        return bool(self.env['dcasa.juan.ajustes'].obtener().crm_automatico)

    def _dcasa_nota(self, texto):
        self.sudo().message_post(body=escape(texto), subtype_xmlid='mail.mt_note')

    def _dcasa_seguro(self, que, funcion):
        """Corre ``funcion`` y NUNCA deja que su error llegue a quien llamó (una cotización, una herramienta)."""
        try:
            with self.env.cr.savepoint():
                return funcion()
        except Exception:   # noqa: BLE001 — el CRM automático no puede tumbar lo que hizo la vendedora o Juan
            _logger.exception('CRM automático: falló «%s» en la oportunidad %s', que, self.ids)
            self.env.invalidate_all()
            return None

    # ------------------------------------------------------------------
    # Etapas (solo hacia adelante)
    # ------------------------------------------------------------------

    def _dcasa_avanzar_a_cotizada(self, orden=None):
        """Pasa a «Propuesta» si estaba antes. Devuelve ``True`` si cambió."""
        self.ensure_one()
        etapa = self.env.ref(ETAPA_COTIZADA, raise_if_not_found=False)
        if not etapa:
            _logger.warning('CRM automático: no existe la etapa %s; no se mueve la oportunidad %s.',
                            ETAPA_COTIZADA, self.id)
            return False
        if etapa.is_won or (self.stage_id and self.stage_id.sequence >= etapa.sequence):
            return False
        antes = self.stage_id.display_name or '—'
        self.sudo().with_context(dcasa_auto=True).write({'stage_id': etapa.id})
        cotizacion = orden.name if orden else self.env._('la cotización')
        self._dcasa_nota(self.env._(
            'Etapa: de «%(antes)s» a «%(ahora)s» (automático): se envió %(cotizacion)s.',
            antes=antes, ahora=etapa.display_name, cotizacion=cotizacion))
        return True

    def _dcasa_ganar_si_hay_pago(self):
        """Ganada: una cotización ligada tiene una factura pagada. Devuelve ``True`` si cambió."""
        self.ensure_one()
        ordenes = self.sudo().order_ids.filtered(lambda o: o.state == 'sale')
        pagadas = ordenes.invoice_ids.filtered(
            lambda f: f.move_type == 'out_invoice' and f.state == 'posted' and f.payment_state in FACTURA_PAGADA)
        if not pagadas:
            return False
        orden = next((o for o in ordenes if o.invoice_ids & pagadas), ordenes[:1])
        self.sudo().with_context(dcasa_auto=True).action_set_won()
        self._dcasa_nota(self.env._(
            'Ganada (automático): se pagó la factura %(factura)s de la cotización %(orden)s.',
            factura=pagadas[0].name or pagadas[0].id, orden=orden.name))
        return True

    # ------------------------------------------------------------------
    # Temperatura
    # ------------------------------------------------------------------

    def _dcasa_hechos(self):
        self.ensure_one()
        ahora = fields.Datetime.now()
        conversaciones = self.sudo().dcasa_conversacion_ids
        ultimos = [fecha for fecha in conversaciones.mapped('ultimo_mensaje_cliente') if fecha]
        horas = (ahora - max(ultimos)).total_seconds() / 3600 if ultimos else None
        mensajes = self.env['dcasa.mensaje'].sudo().search_count([
            ('conversacion_id', 'in', conversaciones.ids), ('autor', '=', 'cliente'),
            ('ts', '>=', ahora - timedelta(days=R.DIAS_CONSTANTE))])
        return R.Hechos(
            cotizacion=any(o.state in ESTADOS_COTIZADA for o in self.sudo().order_ids),
            cuando=bool(self.dcasa_para_cuando), zona=bool(self.dcasa_zona_entrega),
            horas_sin_escribir=horas, mensajes_semana=mensajes,
            atiende_persona=any(c.estado == 'humano' for c in conversaciones))

    def _dcasa_recalcular_temperatura(self):
        """Devuelve ``True`` si cambió el NIVEL (solo entonces queda una nota en la ficha)."""
        self.ensure_one()
        nivel, motivo = R.temperatura(self._dcasa_hechos())
        if nivel == self.dcasa_temperatura and motivo == self.dcasa_temperatura_motivo:
            return False
        cambio = nivel != self.dcasa_temperatura
        self.sudo().with_context(dcasa_auto=True).write(
            {'dcasa_temperatura': nivel, 'dcasa_temperatura_motivo': motivo})
        if cambio:
            self._dcasa_nota(self.env._('Temperatura: %(nivel)s (automático): %(motivo)s.',
                                        nivel=R.NOMBRE_TEMPERATURA[nivel].lower(), motivo=motivo))
        return cambio

    # ------------------------------------------------------------------
    # Sin respuesta
    # ------------------------------------------------------------------

    def _dcasa_perder_si_sin_respuesta(self, ajustes):
        """Archiva como «Sin respuesta» tras los días de Ajustes, solo si nadie la está trabajando."""
        self.ensure_one()
        motivo = self.env.ref(MOTIVO_SIN_RESPUESTA, raise_if_not_found=False)
        if not motivo or not ajustes.crm_dias_para_perdida:
            return False
        conversaciones = self.sudo().dcasa_conversacion_ids
        movimientos = [c.ultima_actividad for c in conversaciones if c.ultima_actividad]
        if not movimientos:
            return False
        dias = (fields.Datetime.now() - max(movimientos)).days
        la_trabaja_una_persona = bool(
            self.sudo().activity_ids or any(c.estado == 'humano' for c in conversaciones)
            or any(o.state == 'sale' for o in self.sudo().order_ids))   # un pedido confirmado sin pagar: no se archiva
        if not R.toca_perder(dias, ajustes.crm_dias_para_perdida, la_trabaja_una_persona):
            return False
        self.sudo().with_context(dcasa_auto=True).action_set_lost(lost_reason_id=motivo.id)
        self._dcasa_nota(self.env._(
            'Archivada (automático): el cliente no escribió en %(dias)s días. Se puede restaurar.', dias=dias))
        return True

    # ------------------------------------------------------------------
    # Datos que dijo el cliente (los anota Juan; nunca pisan a una persona)
    # ------------------------------------------------------------------

    def _dcasa_anotar_datos(self, zona=None, cuando=None):
        """Llena la zona y el «para cuándo» si estaban vacíos. Si ya había otro valor, solo deja una nota.

        Devuelve los campos que cambió. Siempre texto plano, de una línea y con tope (``crm_reglas.limpiar_dato``).
        """
        self.ensure_one()
        cambios, notas = {}, []
        for campo, dato, nombre in (
                ('dcasa_zona_entrega', zona, self.env._('su zona de entrega')),
                ('dcasa_para_cuando', cuando, self.env._('para cuándo lo quiere'))):
            valor = R.limpiar_dato(dato)
            if not valor:
                continue
            actual = self[campo]
            if not actual:
                cambios[campo] = valor
            elif actual.casefold() != valor.casefold():
                notas.append(self.env._('El cliente dijo %(que)s: «%(valor)s» (la oportunidad dice «%(actual)s»).',
                                        que=nombre, valor=valor, actual=actual))
        if cambios:
            self.sudo().write(cambios)
        for nota in notas:
            self._dcasa_nota(nota)
        return cambios

    # ------------------------------------------------------------------
    # Lo que corre solo
    # ------------------------------------------------------------------

    def _dcasa_aplicar_reglas(self, ajustes=None):
        """Todas las reglas, en orden, sobre UNA oportunidad. Devuelve lo que hizo: ``{'ganada': 1, ...}``."""
        self.ensure_one()
        ajustes = ajustes or self.env['dcasa.juan.ajustes'].obtener()
        hecho = {}
        if not self._dcasa_manejables():
            return hecho
        if self._dcasa_ganar_si_hay_pago():
            return {'ganada': 1}
        ordenes_enviadas = self.sudo().order_ids.filtered(lambda o: o.state in ESTADOS_COTIZADA)
        if ordenes_enviadas and self._dcasa_avanzar_a_cotizada(ordenes_enviadas[0]):
            hecho['cotizada'] = 1
        if self._dcasa_recalcular_temperatura():
            hecho['temperatura'] = 1
        if self._dcasa_perder_si_sin_respuesta(ajustes):
            hecho['archivada'] = 1
        return hecho

    @api.model
    def _dcasa_cron_crm(self):
        """Cada 15 minutos: lee los hechos de las oportunidades de conversaciones y las ajusta. Devuelve un resumen."""
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        if not ajustes.crm_automatico:
            return {}
        leads = self.sudo().search([
            ('type', '=', 'opportunity'), ('won_status', '=', 'pending'), ('dcasa_auto_off', '=', False),
            ('dcasa_conversacion_ids', '!=', False)], order='id desc', limit=LOTE_DEL_CRON)
        if len(leads) >= LOTE_DEL_CRON:
            _logger.warning(
                'CRM automático: hay %s o más oportunidades pendientes; este turno revisa las %s más nuevas.',
                LOTE_DEL_CRON, LOTE_DEL_CRON)
        resumen = {}
        for lead in leads:
            hecho = lead._dcasa_seguro('reglas', lambda lead=lead: lead._dcasa_aplicar_reglas(ajustes)) or {}
            for clave, cuenta in hecho.items():
                resumen[clave] = resumen.get(clave, 0) + cuenta
        return resumen

    def _dcasa_al_cotizar(self, orden):
        """Una cotización de esta oportunidad se envió: etapa y temperatura al momento (sin esperar al cron)."""
        for lead in self:
            if not self._dcasa_activo() or not lead._dcasa_manejables():
                continue
            lead._dcasa_seguro('al cotizar', lambda lead=lead: (
                lead._dcasa_avanzar_a_cotizada(orden), lead._dcasa_recalcular_temperatura()))
