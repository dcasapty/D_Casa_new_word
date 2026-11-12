"""Pagos de la IA en «Costos de IA» (pedido de la dueña, 2026-11-12): anotar que Meta ya cobró, para ir a la par.

«Me está diciendo lo que cuesta, lo que se consume… pero ya se me cobró hace mucho el consumo en Meta y volví a empezar
en Meta. Quisiera poder ponerle que ya se pagó, y así ir a la par.»

Un pago NO borra ni reinicia lo consumido: marca un corte (las cuentas y sus bordes, en ``panel_calculos.py``,
«Consumido desde el último pago»). Es un libro, como los demás del sistema: un pago registrado no se edita ni se borra;
si está mal, se ANULA con su motivo (queda en la historia, con quién y cuándo) y se anota el bueno. Solo Gerencia y
administradores; se escribe solo por los métodos del panel, que comprueban el grupo ANTES del ``sudo()`` (el ACL solo da
lectura, así que nadie lo crea ni lo cambia por RPC con un acumulado inventado).
"""
import math
import re
from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from . import horario as H
from . import panel_calculos as C

GRUPOS_DE_PAGOS = ('sales_team.group_sale_manager', 'base.group_system')
# Un pago con fecha a menos de estos minutos de este momento es «ahora»: el corte lo da el Worker.
MINUTOS_AHORA = 10
DIAS_ATRAS_MAX = 400
MAX_MONTO = 100_000
MAX_TEXTO = 300
MAX_EN_LISTA = 12
MESES_CORTOS = ('ene.', 'feb.', 'mar.', 'abr.', 'may.', 'jun.', 'jul.', 'ago.', 'sept.', 'oct.', 'nov.', 'dic.')
FECHA_LOCAL = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?')
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
            raise AccessError(self.env._('Solo Gerencia o un administrador ve y anota los pagos de la IA.'))

    # ------------------------------------------------------------------
    # Anotar y anular
    # ------------------------------------------------------------------

    @api.model
    def registrar_pago_ia(self, fecha=None, monto=None, nota=None):
        """Anota un pago de la IA. ``fecha``: «AAAA-MM-DDTHH:MM» en la hora de Panamá (``None`` = ahora); ``monto``: lo
        que cobró Meta en dólares (``None`` si no lo sabe); ``nota``: texto libre corto. Solo Gerencia y
        administradores. Devuelve ``{ok, id, exacto, corte}`` (``corte``: de dónde salió, dicho para una persona)."""
        self._exigir_pagos()
        horario = self._horario()
        ahora = fields.Datetime.now()
        momento = self._fecha_del_pago(fecha, ahora, horario)
        monto = self._monto_del_pago(monto)
        nota = self._texto_corto(nota)
        es_ahora = abs(momento - ahora) <= timedelta(minutes=MINUTOS_AHORA)
        acumulado = None
        if es_ahora:
            # Se le pregunta al Worker cuánto va el mes (y de paso queda la foto de hoy).
            gasto = (self._tomar_foto_de_costos() or {}).get('gasto_ia_mes_usd')
            acumulado = float(gasto) if _numero(gasto) and gasto >= 0 else None
        local = H.a_local(momento, horario)
        fotos = {f.fecha: f.acumulado_usd for f in self.env['dcasa.juan.costo.dia'].sudo().search(
            [('mes', '=', local.strftime('%Y-%m'))])}
        corte = C.corte_del_pago(local, fotos, es_ahora=es_ahora, acumulado_worker=acumulado)
        valores = {
            'fecha': momento, 'nota': nota or False, 'registrado_por': self.env.user.id, 'al_momento': es_ahora,
            'corte_mes': corte['mes'], 'corte_acumulado_usd': corte['acumulado'], 'corte_origen': corte['origen'],
            'corte_foto': corte['foto'] or False,
        }
        if monto is not None:
            valores['monto_meta_usd'] = monto
        pago = self.env['dcasa.juan.pago.ia'].sudo().create(valores)
        return {'ok': True, 'id': pago.id, 'exacto': pago.corte_origen == 'worker',
                'corte': self._texto_del_corte(pago, horario)}

    @api.model
    def anular_pago_ia(self, pago_id, motivo):
        """Anula un pago con su motivo (queda en la historia; ya no cuenta para nada). Solo Gerencia y
        administradores."""
        self._exigir_pagos()
        if not isinstance(pago_id, int) or isinstance(pago_id, bool):
            raise UserError(self.env._('Pago desconocido.'))
        motivo = self._texto_corto(motivo)
        if not motivo:
            raise UserError(self.env._('Escribe por qué lo anulas: queda en la historia.'))
        pago = self.env['dcasa.juan.pago.ia'].sudo().browse(pago_id).exists()
        if not pago:
            raise UserError(self.env._('Ese pago no existe.'))
        if pago.anulado:
            raise UserError(self.env._('Ese pago ya estaba anulado.'))
        pago._anular(motivo)
        return {'ok': True}

    @api.model
    def _fecha_del_pago(self, fecha, ahora, horario):
        """«AAAA-MM-DDTHH:MM» en la hora de Panamá → UTC ingenuo. ``None`` o vacío = ``ahora``."""
        if fecha in (None, False, ''):
            return ahora
        if not isinstance(fecha, str) or not FECHA_LOCAL.fullmatch(fecha.strip()):
            raise UserError(self.env._('La fecha del pago no se entiende: elige el día y la hora.'))
        try:
            local = datetime.fromisoformat(fecha.strip())
        except ValueError:
            raise UserError(self.env._('La fecha del pago no se entiende: elige el día y la hora.')) from None
        momento = H.a_utc(local.replace(tzinfo=H.cargar_zona(horario.zona)))
        if momento > ahora + timedelta(minutes=MINUTOS_AHORA):
            raise UserError(self.env._('La fecha del pago no puede ser en el futuro.'))
        if momento < ahora - timedelta(days=DIAS_ATRAS_MAX):
            raise UserError(self.env._('Esa fecha es de hace más de un año: revisa el año.'))
        return min(momento, ahora)   # unos minutos «adelante» (el reloj del teléfono) son ahora

    @api.model
    def _monto_del_pago(self, monto):
        if monto in (None, False, ''):
            return None
        if isinstance(monto, str):
            try:
                monto = float(monto.strip().replace(',', '.'))
            except ValueError:
                raise UserError(self.env._('Lo que cobró Meta tiene que ser un número (o déjalo vacío).')) from None
        if not _numero(monto) or monto < 0 or monto > MAX_MONTO:
            raise UserError(self.env._('Lo que cobró Meta tiene que ser un número (o déjalo vacío).'))
        return round(float(monto), 2) or None

    @api.model
    def _texto_corto(self, texto):
        if texto in (None, False):
            return ''
        if not isinstance(texto, str):
            raise UserError(self.env._('Texto inválido.'))
        return ' '.join(texto.split())[:MAX_TEXTO]

    # ------------------------------------------------------------------
    # Lo que ve la pantalla
    # ------------------------------------------------------------------

    @api.model
    def _pagos_ia(self, ahora=None):
        """Los pagos para «Costos de IA»: la cifra «desde el último pago» (solo con ``ahora`` = ``(mes, acumulado)``
        que acaba de decir el Worker) y la lista corta (los más recientes, anulados incluidos)."""
        horario = self._horario()
        datos = {'hay': False, 'total': 0, 'zona': horario.zona,
                 'ahora_local': self._ahora_local().strftime('%Y-%m-%dT%H:%M'),
                 'desde_el_ultimo': None, 'ultimo': None, 'lista': []}
        if not self.env.su and not any(self.env.user.has_group(grupo) for grupo in GRUPOS_DE_PAGOS):
            return datos
        registros = self.env['dcasa.juan.pago.ia'].sudo().search([])   # pocos: uno por cobro de Meta
        if not registros:
            return datos
        vigentes = registros.filtered(lambda p: not p.anulado)
        fotos = {}
        if vigentes:
            fotos = {f.fecha: f.acumulado_usd for f in self.env['dcasa.juan.costo.dia'].sudo().search(
                [('mes', '>=', min(vigentes.mapped('corte_mes')))])}
        cuentas, desde = C.periodos_de_pagos([{
            'id': p.id, 'fecha': p.fecha, 'corte': (p.corte_mes, p.corte_acumulado_usd),
            'exacto': p.corte_origen == 'worker', 'monto': p.monto_meta_usd or None, 'anulado': p.anulado,
        } for p in registros], C.cierres_de_mes(fotos), ahora)
        primero = min(vigentes, key=lambda p: (p.fecha, p.id)) if vigentes else None
        lista = []
        for pago in registros[:MAX_EN_LISTA]:
            cuenta = cuentas[pago.id]
            calculado = cuenta['calculado']
            lista.append({
                'id': pago.id, 'fecha': H.a_iso(pago.fecha), 'fecha_texto': self._fecha_corta(pago.fecha, horario),
                'monto': pago.monto_meta_usd or None, 'nota': pago.nota or '',
                'registrado_por': pago.registrado_por.name or '',
                'calculado': calculado['usd'] if calculado else None,
                'calculado_completo': bool(calculado and calculado['completo']),
                'aproximado': cuenta['aproximado'], 'diferencia': cuenta['diferencia'],
                'primero': pago == primero, 'exacto': pago.corte_origen == 'worker',
                'corte': self._texto_del_corte(pago, horario),
                'anulado': pago.anulado,
                'anulado_texto': (self.env._('Anulado por %(quien)s el %(cuando)s: %(motivo)s',
                                             quien=pago.anulado_por.name or '',
                                             cuando=self._fecha_corta(pago.anulado_el, horario),
                                             motivo=pago.motivo_anulacion or '') if pago.anulado else ''),
            })
        ultimo = max(vigentes, key=lambda p: (p.fecha, p.id)) if vigentes else None
        if ultimo:
            datos['ultimo'] = {'id': ultimo.id, 'fecha_texto': H.texto_fecha_hora(ultimo.fecha, horario),
                               'monto': ultimo.monto_meta_usd or None}
        if desde:
            faltan = desde['meses_sin_datos'] + desde['meses_incompletos']
            datos['desde_el_ultimo'] = {
                'usd': desde['usd'], 'completo': desde['completo'], 'aproximado': desde['aproximado'],
                'meses_sin_datos': [self._nombre_del_mes(m) for m in desde['meses_sin_datos']],
                'meses_incompletos': [self._nombre_del_mes(m) for m in desde['meses_incompletos']],
                'faltan_texto': ', '.join(self._nombre_del_mes(m) for m in sorted(faltan)),
                'corte': self._texto_del_corte(ultimo, horario),
            }
        datos.update(hay=True, total=len(registros), lista=lista)
        return datos

    @api.model
    def _nombre_del_mes(self, mes):
        anio, numero = (int(x) for x in mes.split('-'))
        return f'{H.MESES[numero - 1]} de {anio}'

    @api.model
    def _fecha_corta(self, utc, horario):
        """«12 nov. 2026, 10:42 a. m.» en la hora de Panamá."""
        if not utc:
            return ''
        local = H.a_local(utc, horario)
        return f'{local.day} {MESES_CORTOS[local.month - 1]} {local.year}, {H.texto_hora_amable(local.time())}'

    @api.model
    def _texto_del_corte(self, pago, horario):
        """De dónde salió el corte de ese pago, dicho para una persona (y por qué es exacto o aproximado)."""
        if pago.corte_origen == 'worker':
            return self.env._('Corte exacto: el gasto del mes que dijo el Worker al anotar el pago.')
        despues = self.env._('Lo que se consumió entre ese punto y el pago se cuenta después del pago.')
        if pago.corte_origen == 'foto':
            foto = pago.corte_foto
            dia = f'{foto.day} de {H.MESES[foto.month - 1]}' if foto else ''
            if pago.al_momento:
                return self.env._('Corte aproximado: el Worker no respondió al anotarlo y se usó la foto del gasto '
                                  'del %(dia)s. %(despues)s', dia=dia, despues=despues)
            return self.env._('Corte aproximado: el pago es de otro momento y se usó la foto del gasto del %(dia)s, '
                              'la última antes del pago. %(despues)s', dia=dia, despues=despues)
        anio, numero = (int(x) for x in pago.corte_mes.split('-'))
        dia = f'1 de {H.MESES[numero - 1]}'
        if pago.al_momento:
            return self.env._('Corte aproximado: el Worker no respondió al anotarlo y todavía no había fotos del mes; '
                              'se cuenta desde el %(dia)s, cuando el gasto empezó en cero. %(despues)s',
                              dia=dia, despues=despues)
        return self.env._('Corte aproximado: no hay fotos de ese mes antes del pago; se cuenta desde el %(dia)s, '
                          'cuando el gasto empezó en cero. %(despues)s', dia=dia, despues=despues)
