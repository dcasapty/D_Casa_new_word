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

import psycopg2.errors

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
# Lo visto y lo de ahora pueden diferir en lo que se consumió mientras se confirmaba: hasta 5 centavos o el 1 %, lo que
# sea mayor. Más que eso, la pantalla estaba vieja y se pagaría menos de lo consumido (revisión, 2026-11-12).
TOLERANCIA_MINIMA = 0.05
TOLERANCIA_RELATIVA = 0.01
CLAVE_DEL_CERROJO = 'dcasa_conversaciones.pago_ia_cerrojo'
CAMBIO = 'El saldo cambió: vuelve a abrir la pantalla.'
OTROS_DE_MESES_ANTERIORES = ('No incluye lo que Brian de la tienda gastó en modelos de Meta en meses anteriores: '
                             'el Worker solo da el mes en curso.')


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
    # Lo que otros asistentes (hoy, Brian de la tienda) llevaban gastado en el mes en modelos de Meta al pagar: los
    # mismos modelos y la misma cuenta que Juan, así que Meta también lo cobra (revisión, 2026-11-14).
    corte_otros_mes = fields.Char('Mes del corte de otros asistentes', readonly=True, help='AAAA-MM (mes del Worker).')
    corte_otros_usd = fields.Float('Otros asistentes en modelos de Meta, en el corte (USD)', digits=(12, 6),
                                   readonly=True)
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


def tomar_el_cerrojo(cr, cuando):
    """Que dos «Pagar» a la vez (dos pestañas o dos personas) no dejen dos pagos con el mismo corte.

    Escribe una fila fija (``ir_config_parameter``, clave ``CLAVE_DEL_CERROJO``, con la hora) con ``INSERT … ON
    CONFLICT DO UPDATE``: su candado dura hasta el final de la transacción, llamada al Worker incluida, así que el
    segundo espera.
    Odoo trabaja en REPEATABLE READ: cuando el primero termina, el segundo recibe un error de serialización (la fila
    cambió después de que empezó su transacción, que no vería el pago nuevo). Pasa lo mismo si el otro pago terminó
    justo antes pero esta transacción empezó antes que eso. Devuelve ``False`` en esos casos: no se registra nada.
    """
    try:
        with cr.savepoint(flush=False):
            cr.execute("""
                INSERT INTO ir_config_parameter (key, value, create_date, write_date)
                     VALUES (%(k)s, %(v)s, %(t)s, %(t)s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = EXCLUDED.write_date""",
                       {'k': CLAVE_DEL_CERROJO, 'v': fields.Datetime.to_string(cuando), 't': cuando},
                       log_exceptions=False)   # el choque es esperado: no es un error del sistema
    except psycopg2.errors.SerializationFailure:
        return False
    return True


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
        AHORA y la cuenta empieza de nuevo. El corte se le pide al Worker; si no responde (o no pudo leer su contador),
        no se registra nada. Si lo visto ya no es lo de ahora (más que la tolerancia: pantalla vieja) u otro «Pagar» se
        registró a la vez, tampoco: «El saldo cambió». Solo Gerencia y administradores. Devuelve ``{ok, id, monto}``."""
        self._exigir_pagos()
        if not _numero(saldo) or saldo < 0 or saldo > MAX_MONTO:
            raise UserError(self.env._('El saldo no se entiende: vuelve a abrir la pantalla.'))
        saldo = round(float(saldo), 2)
        if saldo <= 0:
            raise UserError(self.env._('No hay nada por pagar.'))
        if not tomar_el_cerrojo(self.env.cr, fields.Datetime.now()):
            raise UserError(self.env._(CAMBIO))
        informe = self._tomar_foto_de_costos() or {}     # le pregunta al Worker y de paso deja la foto de hoy
        gasto = informe.get('gasto_ia_mes_usd')
        if not _numero(gasto) or gasto < 0:
            raise UserError(self.env._('No pude hablar con Juan: inténtalo en un momento.'))
        ahora = self._ahora_local()
        mes = informe['mes'] if C.mes_valido(informe.get('mes')) else ahora.strftime('%Y-%m')
        otros = self._otros_de_meta_ahora()
        actual = self._saldo_ia((mes, float(gasto)), otros)['saldo']
        # Se vuelve a mirar el saldo DESPUÉS de hablar con el Worker y con el cerrojo tomado: si lo visto quedó atrás
        # (se consumió más desde que se abrió la pantalla), pagar lo visto borraría consumo sin pagar.
        if actual is None or abs(actual - saldo) > max(TOLERANCIA_MINIMA, TOLERANCIA_RELATIVA * actual):
            raise UserError(self.env._(CAMBIO))
        corte = C.corte_del_pago(ahora, {}, es_ahora=True, acumulado_worker=float(gasto), mes_worker=mes)
        pago = self.env['dcasa.juan.pago.ia'].sudo().create({
            'fecha': fields.Datetime.now(), 'monto_meta_usd': saldo, 'registrado_por': self.env.user.id,
            'al_momento': True, 'corte_mes': corte['mes'], 'corte_acumulado_usd': corte['acumulado'],
            'corte_origen': corte['origen'],
            'corte_otros_mes': otros['mes'] if otros else False,
            'corte_otros_usd': otros['usd'] if otros else 0.0,
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
        # El mismo cerrojo que «Pagar» (revisión, 2026-11-12): un «Deshacer» del pago 1 mientras otro «Pagar» habla con
        # el Worker dejaba el pago 1 anulado y el 2 con el corte nuevo (se esfumaba lo del pago 1). Con el cerrojo
        # tomado, la base que se ve es la de ahora y se vuelve a revisar que siga siendo el último que cuenta.
        if not tomar_el_cerrojo(self.env.cr, fields.Datetime.now()):
            raise UserError(self.env._('Algo cambió mientras tanto: vuelve a abrir la pantalla.'))
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
    def _saldo_ia(self, ahora=None, otros=None):
        """«Por pagar a Meta» con ``ahora`` = ``(mes, acumulado)`` que acaba de decir el Worker (sin él, ``None``).

        ``otros`` = ``{mes, usd}``: lo que otros asistentes (Brian de la tienda) llevan en el mes en modelos de Meta
        (``_otros_de_meta``); se suma aparte, sin cambiar la cuenta de Juan, y queda en ``otros_usd``.

        Con pagos, lo consumido desde el último (``periodos_de_pagos``); sin pagos, lo del mes, como siempre mostró la
        pantalla. ``aprox``: la cifra es un mínimo (a algún mes le faltan fotos, o el contador del Worker volvió a
        empezar después del pago), con ``aprox_texto``, la explicación corta. Devuelve ``{saldo, aprox, aprox_texto,
        saldo_si_se_deshace, ultimo}``; ``ultimo`` = ``{id, monto, texto, dia}`` o ``None``."""
        datos = {'saldo': None, 'aprox': False, 'aprox_texto': '', 'saldo_si_se_deshace': None, 'ultimo': None}
        if not self.env.su and not any(self.env.user.has_group(grupo) for grupo in GRUPOS_DE_PAGOS):
            return datos
        vigentes = self.env['dcasa.juan.pago.ia'].sudo().search([('anulado', '=', False)])
        if vigentes:
            ultimo = vigentes[0]
            datos['ultimo'] = {'id': ultimo.id, 'monto': ultimo.monto_meta_usd or 0.0,
                               'texto': self._fecha_corta(ultimo.fecha), 'dia': self._fecha_corta(ultimo.fecha, False)}
        if ahora is None:
            return datos
        fotos = {}
        if vigentes:
            fotos = {f.fecha: f.acumulado_usd for f in self.env['dcasa.juan.costo.dia'].sudo().search(
                [('mes', '>=', min(vigentes.mapped('corte_mes')))])}
        cierres = C.cierres_de_mes(fotos)
        saldo, aprox, texto = self._saldo_desde(vigentes, cierres, ahora)
        datos.update(saldo=saldo, aprox=aprox, aprox_texto=texto)
        if vigentes:
            datos['saldo_si_se_deshace'] = self._saldo_desde(vigentes[1:], cierres, ahora)[0]
        if otros and datos['saldo'] is not None:
            pendiente, incompleto = self._pendiente_de_otros(vigentes[:1], otros)
            datos['saldo'] = round(datos['saldo'] + pendiente, 2)
            datos['otros_usd'] = round(pendiente, 2)
            if incompleto:
                datos['aprox'] = True
                datos['aprox_texto'] = f"{datos['aprox_texto']} {self.env._(OTROS_DE_MESES_ANTERIORES)}".strip()
            if datos['saldo_si_se_deshace'] is not None:
                datos['saldo_si_se_deshace'] = round(
                    datos['saldo_si_se_deshace'] + self._pendiente_de_otros(vigentes[1:2], otros)[0], 2)
        return datos

    # ------------------------------------------------------------------
    # Otros asistentes en modelos de Meta (Brian de la tienda)
    # ------------------------------------------------------------------

    @api.model
    def _otros_de_meta(self, extra):
        """``{mes, usd}`` de lo que otros asistentes gastaron este mes en modelos de Meta, con los renglones aparte de
        «Costos de IA» (``extra``, de ``_costos_extra``); ``None`` si no hay. Lo pone ``dcasa_brian_tienda``."""
        return None

    @api.model
    def _otros_de_meta_ahora(self):
        """Lo mismo, preguntándole al Worker ahora (al pagar)."""
        return None

    @api.model
    def _pendiente_de_otros(self, pago, otros):
        """``(usd, incompleto)``: lo de ``otros`` sin pagar desde ``pago`` (el último que cuenta, o vacío). Sin pago, lo
        del mes (como Juan); con el corte en este mes, lo de después del corte; con el corte en un mes anterior, lo del
        mes en curso, que es un mínimo (``incompleto``): el Worker no da los meses pasados."""
        if not pago:
            return otros['usd'], False
        if pago.corte_otros_mes == otros['mes']:
            return max(otros['usd'] - (pago.corte_otros_usd or 0.0), 0.0), False
        return otros['usd'], (pago.corte_otros_mes or pago.corte_mes) < otros['mes']

    @api.model
    def _saldo_desde(self, vigentes, cierres, ahora):
        """``(saldo, aprox, explicación)`` con esos pagos vigentes (sin pagos: lo del mes)."""
        if not vigentes:
            return round(max(float(ahora[1]), 0.0), 2), False, ''
        _cuentas, desde = C.periodos_de_pagos([{
            'id': p.id, 'fecha': p.fecha, 'corte': (p.corte_mes, p.corte_acumulado_usd),
            'exacto': p.corte_origen == 'worker', 'monto': p.monto_meta_usd or None, 'anulado': False,
        } for p in vigentes], cierres, ahora)
        if desde['bajo']:
            texto = self.env._('El contador de Juan volvió a empezar después del último pago: es lo que lleva desde '
                               'entonces.')
        elif not desde['completo'] or desde['aproximado']:
            texto = self.env._('Faltan fotos del gasto de algún mes: puede ser un poco más.')
        else:
            texto = ''
        return desde['usd'], bool(texto), texto

    @api.model
    def _fecha_corta(self, utc, con_hora=True):
        """«11 nov, 9:30 p. m.» (y el año si no es el de ahora), en la hora de Panamá; sin hora, «11 nov»."""
        horario = self._horario()
        local = H.a_local(utc, horario)
        anio = '' if local.year == self._ahora_local().year else f' {local.year}'
        dia = f'{local.day} {MESES_CORTOS[local.month - 1]}{anio}'
        return f'{dia}, {H.texto_hora_amable(local.time())}' if con_hora else dia
