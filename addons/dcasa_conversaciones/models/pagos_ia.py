"""«Pagar» en «Costos de IA» (pedido de la dueña, 2026-11-12): el saldo con Meta vuelve a cero y empieza a contar.

«Me gustaría que un botón diga pagar y que el saldo que ya había ¡fuap! ya salga como pago y que la cuenta empiece de
nuevo.» Arriba de la pantalla, «Por pagar a Meta» (lo consumido desde el último pago; sin pagos, lo del mes, como antes)
y el botón «Pagar» con una sola confirmación. Debajo, «Último pago» con «Deshacer» por si se tocó sin querer.

Por dentro NADA se borra ni se reinicia: cada pago es un CORTE en la línea del gasto (las cuentas y sus bordes,
en ``panel_calculos.py``, «Consumido desde el último pago»). Es un libro, como los demás del sistema: un pago no se
edita ni se borra; «Deshacer» lo ANULA con su motivo (queda en la historia, con quién y cuándo). El corte es siempre
exacto: se le pide al Worker al pagar y, si no responde, no se registra nada (un corte adivinado dejaría el saldo mal).
Solo Gerencia y administradores; se escribe solo por los métodos del panel, que comprueban el grupo ANTES del
``sudo()`` (el ACL solo da lectura: nadie lo crea ni lo cambia por RPC con un acumulado inventado).
"""
import math

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from . import horario as H
from . import panel_calculos as C

GRUPOS_DE_PAGOS = ('sales_team.group_sale_manager', 'base.group_system')
MAX_MONTO = 100_000
MOTIVO_DESHACER = 'Deshecho desde la pantalla'
MESES_CORTOS = ('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sept', 'oct', 'nov', 'dic')
# Lo único que se escribe de un pago después de crearlo: su anulación (por ``_anular``).
CAMPOS_DE_ANULAR = frozenset({'anulado', 'anulado_el', 'anulado_por', 'motivo_anulacion'})
_ANULANDO = 'dcasa_pago_ia_anulando'


class DcasaJuanPagoIa(models.Model):
    """Un cobro de la IA (Meta). Marca un corte en la línea del gasto; no se edita ni se borra, se anula con motivo."""
    _name = 'dcasa.juan.pago.ia'
    _description = 'Pago de la IA (un corte en el gasto)'
    _order = 'fecha desc, id desc'
    _rec_name = 'fecha'

    fecha = fields.Datetime('Fecha del pago', required=True, readonly=True, index=True)
    monto_meta_usd = fields.Float('Lo que cobró Meta (USD)', digits=(12, 2), readonly=True,
                                  help='Vacío si no se sabía al anotarlo.')
    nota = fields.Char(readonly=True)
    registrado_por = fields.Many2one('res.users', 'Lo anotó', required=True, readonly=True, ondelete='restrict',
                                     default=lambda self: self.env.user)
    al_momento = fields.Boolean('Anotado al momento del pago', readonly=True,
                                help='La fecha del pago era «ahora»: el corte se le pidió al Worker.')
    corte_mes = fields.Char('Mes del corte', required=True, readonly=True, help='AAAA-MM (mes de Panamá).')
    corte_acumulado_usd = fields.Float('Acumulado del mes en el corte (USD)', digits=(12, 6), readonly=True)
    corte_origen = fields.Selection([
        ('worker', 'El Worker, al anotarlo (exacto)'),
        ('foto', 'Una foto diaria del gasto (aproximado)'),
        ('inicio_de_mes', 'El inicio del mes (aproximado)'),
    ], 'De dónde salió el corte', required=True, readonly=True)
    corte_foto = fields.Date('Foto usada', readonly=True)
    anulado = fields.Boolean(readonly=True, index=True)
    anulado_el = fields.Datetime('Anulado el', readonly=True)
    anulado_por = fields.Many2one('res.users', 'Lo anuló', readonly=True, ondelete='restrict')
    motivo_anulacion = fields.Char('Motivo de la anulación', readonly=True)

    _monto_positivo = models.Constraint(
        'CHECK(monto_meta_usd IS NULL OR monto_meta_usd > 0)', 'Lo que cobró Meta es mayor que cero (o se deja vacío).')
    _corte_no_negativo = models.Constraint(
        'CHECK(corte_acumulado_usd IS NOT NULL AND corte_acumulado_usd >= 0)', 'El corte no puede ser negativo.')
    _anulado_con_motivo = models.Constraint(
        "CHECK(anulado IS NOT TRUE OR (motivo_anulacion IS NOT NULL AND motivo_anulacion <> '' "
        "AND anulado_el IS NOT NULL AND anulado_por IS NOT NULL))",
        'Un pago anulado lleva motivo, quién y cuándo.')

    def write(self, vals):
        if not self.env.context.get(_ANULANDO) or set(vals) - CAMPOS_DE_ANULAR or any(self.mapped('anulado')):
            raise UserError(self.env._(
                'Un pago registrado no se edita: si está mal, anúlalo con su motivo y anota el bueno.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(self.env._('Un pago registrado no se borra: si está mal, anúlalo con su motivo.'))

    def _anular(self, motivo):
        """Lo marca anulado con su motivo, quién y cuándo. Único camino para cambiar un pago (lo llama el panel)."""
        self.ensure_one()
        self.sudo().with_context(**{_ANULANDO: True}).write({
            'anulado': True, 'anulado_el': fields.Datetime.now(), 'anulado_por': self.env.user.id,
            'motivo_anulacion': motivo,
        })


def _numero(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)


class DcasaJuanPanelPagos(models.AbstractModel):
    _inherit = 'dcasa.juan.panel'

    @api.model
    def _exigir_pagos(self):
        if not self.env.su and not any(self.env.user.has_group(grupo) for grupo in GRUPOS_DE_PAGOS):
            raise AccessError(self.env._('Solo Gerencia o un administrador ve y marca los pagos de la IA.'))

    # ------------------------------------------------------------------
    # Pagar y deshacer
    # ------------------------------------------------------------------

    @api.model
    def pagar_ia(self, saldo):
        """«Pagar»: lo que había por pagar a Meta (``saldo``, el que vio la persona en la pantalla) queda como pagado
        AHORA y la cuenta empieza de nuevo. El corte se le pide al Worker; si no responde, no se registra nada.
        Solo Gerencia y administradores. Devuelve ``{ok, id, monto}``."""
        self._exigir_pagos()
        if not _numero(saldo) or saldo < 0 or saldo > MAX_MONTO:
            raise UserError(self.env._('El saldo no se entiende: vuelve a abrir la pantalla.'))
        saldo = round(float(saldo), 2)
        if saldo <= 0:
            raise UserError(self.env._('No hay nada por pagar.'))
        gasto = (self._tomar_foto_de_costos() or {}).get('gasto_ia_mes_usd')   # y de paso queda la foto de hoy
        if not _numero(gasto) or gasto < 0:
            raise UserError(self.env._('No pude hablar con Juan: inténtalo en un momento.'))
        ahora = self._ahora_local()
        actual = self._saldo_ia((ahora.strftime('%Y-%m'), float(gasto)))
        # Lo que se vio no puede ser más que lo que hay ahora (el gasto solo crece): si no, la pantalla estaba vieja.
        if actual['saldo'] is not None and saldo > actual['saldo'] + 0.01:
            raise UserError(self.env._('El saldo cambió: vuelve a abrir la pantalla.'))
        corte = C.corte_del_pago(ahora, {}, es_ahora=True, acumulado_worker=float(gasto))
        pago = self.env['dcasa.juan.pago.ia'].sudo().create({
            'fecha': fields.Datetime.now(), 'monto_meta_usd': saldo, 'registrado_por': self.env.user.id,
            'al_momento': True, 'corte_mes': corte['mes'], 'corte_acumulado_usd': corte['acumulado'],
            'corte_origen': corte['origen'],
        })
        return {'ok': True, 'id': pago.id, 'monto': saldo}

    @api.model
    def deshacer_pago_ia(self, pago_id):
        """«Deshacer» el último pago (por si se tocó sin querer): se anula con el motivo «Deshecho desde la pantalla»
        (queda en la historia) y el saldo vuelve a como estaba. Solo el último que cuenta; solo Gerencia y
        administradores."""
        self._exigir_pagos()
        if not isinstance(pago_id, int) or isinstance(pago_id, bool):
            raise UserError(self.env._('Pago desconocido.'))
        ultimo = self._ultimo_pago_ia()
        if not ultimo or ultimo.id != pago_id:
            raise UserError(self.env._('Solo se puede deshacer el último pago: vuelve a abrir la pantalla.'))
        ultimo._anular(MOTIVO_DESHACER)
        return {'ok': True}

    # ------------------------------------------------------------------
    # El saldo
    # ------------------------------------------------------------------

    @api.model
    def _ultimo_pago_ia(self):
        """El último pago que cuenta (el más reciente sin anular), o un registro vacío."""
        return self.env['dcasa.juan.pago.ia'].sudo().search([('anulado', '=', False)], limit=1)

    @api.model
    def _saldo_ia(self, ahora=None):
        """«Por pagar a Meta» con ``ahora`` = ``(mes, acumulado)`` que acaba de decir el Worker (sin él, ``None``).

        Con pagos, lo consumido desde el último (``periodos_de_pagos``); sin pagos, lo del mes, como siempre mostró la
        pantalla. ``aprox``: a algún mes de en medio le faltan fotos (la cifra es un mínimo). Devuelve
        ``{saldo, aprox, ultimo}``; ``ultimo`` = ``{id, monto, texto}`` o ``None``."""
        datos = {'saldo': None, 'aprox': False, 'ultimo': None}
        if not self.env.su and not any(self.env.user.has_group(grupo) for grupo in GRUPOS_DE_PAGOS):
            return datos
        vigentes = self.env['dcasa.juan.pago.ia'].sudo().search([('anulado', '=', False)])
        if vigentes:
            ultimo = vigentes[0]
            datos['ultimo'] = {'id': ultimo.id, 'monto': ultimo.monto_meta_usd or 0.0,
                               'texto': self._fecha_corta(ultimo.fecha)}
        if ahora is None:
            return datos
        if not vigentes:
            datos['saldo'] = round(max(float(ahora[1]), 0.0), 2)
            return datos
        fotos = {f.fecha: f.acumulado_usd for f in self.env['dcasa.juan.costo.dia'].sudo().search(
            [('mes', '>=', min(vigentes.mapped('corte_mes')))])}
        _cuentas, desde = C.periodos_de_pagos([{
            'id': p.id, 'fecha': p.fecha, 'corte': (p.corte_mes, p.corte_acumulado_usd),
            'exacto': p.corte_origen == 'worker', 'monto': p.monto_meta_usd or None, 'anulado': False,
        } for p in vigentes], C.cierres_de_mes(fotos), ahora)
        datos.update(saldo=desde['usd'], aprox=not desde['completo'] or desde['aproximado'])
        return datos

    @api.model
    def _fecha_corta(self, utc):
        """«11 nov, 9:30 p. m.» (y el año si no es el de ahora), en la hora de Panamá."""
        horario = self._horario()
        local = H.a_local(utc, horario)
        anio = '' if local.year == self._ahora_local().year else f' {local.year}'
        return f'{local.day} {MESES_CORTOS[local.month - 1]}{anio}, {H.texto_hora_amable(local.time())}'
