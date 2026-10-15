"""Reparto de conversaciones: a quién le pasa Juan cada conversación que no puede resolver, y el libro de ese reparto.

Cuando el asistente pasa una conversación a una persona (``dcasa.conversacion._pasar_a_vendedora``), con el reparto
«parejo» (Ajustes de Juan) la decisión sigue este orden, de lo más importante a lo menos:

1. **Quién puede recibir** (las «disponibles»): solo las **vendedoras**, es decir, personas internas con el grupo de
   ventas que NO son Gerencia de ventas ni administradoras (ellas intervienen en cualquier conversación, pero el
   reparto no se las pasa). De ellas, las que Gerencia no sacó del reparto (vacaciones, ausencias) y que no se
   marcaron «No disponible» (almuerzo, fin del día). «No disponible» se reinicia solo cada mañana.
2. **Su vendedora de siempre**: si el cliente habló con una de ellas en los últimos N días
   (``reparto_dias_misma_vendedora``, 14 de fábrica), vuelve con ella. 0 = sin memoria.
3. **Quien lleva menos hoy**: la que menos conversaciones recibió hoy (día de Panamá); con empate, a quien menos
   clientes le esperan ahora; con empate, a quien lleva más tiempo sin recibir una (``res.users.dcasa_turno``).
4. **Nadie disponible**: la conversación no se asigna; la tarea queda con el responsable por defecto y se avisa a todo
   el equipo, como siempre.

Cada decisión queda en ``dcasa.reparto`` (un libro que no se edita): de ahí salen las cuentas de la pantalla «Reparto».
Aquí no hay ningún método público: la pantalla entra por ``dcasa.juan.panel`` (``panel_reparto.py``).

**Borde conocido:** quien tiene el rol de vendedora Y además el de Gerencia (o es administradora) deja de recibir: se
cuenta como Gerencia. Gerencia lo ve en la pantalla «Reparto», en «No reciben».
"""
import logging
from dataclasses import dataclass
from datetime import timedelta

from odoo import api, fields, models

from . import horario as H

_logger = logging.getLogger(__name__)

REGLAS = [
    ('parejo', 'Reparto parejo'),
    ('turno', 'Por turnos'),
    ('misma', 'Siguió con su vendedora'),
    ('manual', 'Asignada a mano'),
]
# Las que cuentan como «Juan se la pasó»: son las que se reparten. La asignación a mano (alguien eligió a quién) queda
# en el libro porque dice quién atendió al cliente, pero no cuenta como una conversación recibida.
REGLAS_DE_JUAN = ('parejo', 'turno', 'misma')
MAX_FILAS_PROPIAS = 100
GRUPO_VENDEDORA = 'sales_team.group_sale_salesman'
# Estas personas intervienen en cualquier conversación, pero el reparto no se las pasa.
GRUPOS_QUE_NO_RECIBEN = ('sales_team.group_sale_manager', 'base.group_system')
# «No disponible» se reinicia solo: a esta hora ANTES de que abra la tienda (6:00 a. m. con el horario de 8:00).
MARGEN_ANTES_DE_ABRIR = timedelta(hours=2)


@dataclass
class Decision:
    """Lo que se decidió con una conversación que Juan pasa: a quién (vacío = a nadie), por qué y si faltó alguien."""
    usuario: object
    razon: str = ''
    regla: str = ''
    sin_nadie: bool = False


class DcasaReparto(models.Model):
    _name = 'dcasa.reparto'
    _description = 'Conversación que Juan le pasó a una persona'
    _order = 'id desc'

    conversacion_id = fields.Many2one('dcasa.conversacion', 'Conversación', required=True, ondelete='cascade',
                                      index=True, readonly=True)
    usuario_id = fields.Many2one('res.users', 'Le tocó a', required=True, ondelete='cascade', readonly=True)
    dia = fields.Date('Día (hora de Panamá)', required=True, readonly=True,
                      help='El día de Panamá en que se pasó: con él se cuentan las que recibió «hoy».')
    regla = fields.Selection(REGLAS, 'Cómo se decidió', required=True, readonly=True)
    razon = fields.Char('Por qué', readonly=True)
    momento = fields.Datetime('Cuándo', required=True, readonly=True, default=fields.Datetime.now)

    _dia_usuario_idx = models.Index('(dia, usuario_id)')

    # ------------------------------------------------------------------
    # Quién entra al reparto
    # ------------------------------------------------------------------

    @api.model
    def _hoy(self):
        """La fecha de hoy en Panamá (el día del reparto no cambia a las 7 p. m. por culpa de UTC)."""
        horario = self.env['dcasa.juan.ajustes'].obtener().horario()
        return H.a_local(fields.Datetime.now(), horario).date()

    @api.model
    def _vendedoras(self):
        """Quienes pueden recibir lo que reparte Juan por su ROL: personas internas del equipo de ventas que no son
        Gerencia de ventas ni administradoras. No cambia ``_usuarios_del_panel`` (quién ve, recibe avisos o puede ser
        mencionada): solo decide a quién se le pasan conversaciones."""
        Usuarios = self.env['res.users'].sudo()
        ventas = Usuarios.search([('all_group_ids', 'in', self.env.ref(GRUPO_VENDEDORA).ids), ('share', '=', False)])
        grupos = [self.env.ref(xmlid).id for xmlid in GRUPOS_QUE_NO_RECIBEN]
        return ventas - Usuarios.search([('all_group_ids', 'in', grupos)])

    @api.model
    def _equipo(self, hoy=None):
        """Las vendedoras que pueden recibir conversaciones: todas menos las que Gerencia sacó del reparto."""
        hoy = hoy or self._hoy()
        return self._vendedoras().filtered(lambda u: u._dcasa_en_el_reparto(hoy))

    @api.model
    def _no_reciben(self):
        """Quienes del equipo de ventas intervienen pero no reciben (Gerencia y administradoras)."""
        return self.env['dcasa.conversacion']._usuarios_del_panel() - self._vendedoras()

    @api.model
    def _disponibles(self, hoy=None):
        """Las vendedoras que pueden recibir Y no se marcaron «No disponible»: entre ellas se reparte."""
        return self._equipo(hoy).filtered('dcasa_disponible')

    # ------------------------------------------------------------------
    # Cuentas (las que decide el reparto y las que muestra la pantalla)
    # ------------------------------------------------------------------

    @api.model
    def _cuentas(self, usuarios, desde, hasta, excepto=None):
        """``{usuario_id: {recibidas, abiertas, ultima}}``.

        * ``recibidas``: las que Juan le pasó entre los días ``desde`` y ``hasta`` (fechas de Panamá, ambos incluidos).
        * ``abiertas``: clientes que le esperan ahora (conversación suya, con una persona, y el último mensaje es del
          cliente).
        * ``ultima``: cuándo fue la última que Juan le pasó (de cualquier día), o ``None``.

        ``excepto``: una conversación que no se cuenta como «esperando» (la que se está repartiendo ahora mismo: si ya
        tenía dueña, no puede pesarle en su contra).
        """
        cuentas = {u.id: {'recibidas': 0, 'abiertas': 0, 'ultima': None} for u in usuarios}
        if not cuentas:
            return cuentas
        libro = self.sudo()
        de_juan = [('usuario_id', 'in', list(cuentas)), ('regla', 'in', REGLAS_DE_JUAN)]
        for usuario, n in libro._read_group(de_juan + [('dia', '>=', desde), ('dia', '<=', hasta)],
                                            ['usuario_id'], ['__count']):
            cuentas[usuario.id]['recibidas'] = n
        for usuario, ultima in libro._read_group(de_juan, ['usuario_id'], ['momento:max']):
            cuentas[usuario.id]['ultima'] = ultima
        esperando = [('asignada_a', 'in', list(cuentas)), ('estado', '=', 'humano'),
                     ('ultimo_mensaje_autor', '=', 'cliente'), ('id', 'not in', excepto.ids if excepto else [])]
        for usuario, n in self.env['dcasa.conversacion'].sudo()._read_group(esperando, ['asignada_a'], ['__count']):
            cuentas[usuario.id]['abiertas'] = n
        return cuentas

    # ------------------------------------------------------------------
    # La decisión
    # ------------------------------------------------------------------

    @api.model
    def _ordenar(self, candidatas, cuentas):
        """La fila, de la primera a la última: menos recibidas hoy, menos clientes esperando, más tiempo sin recibir."""
        return candidatas.sorted(lambda u: (cuentas[u.id]['recibidas'], cuentas[u.id]['abiertas'], u.dcasa_turno, u.id))

    @api.model
    def _por_que_le_toco(self, ordenadas, cuentas):
        """Una frase sencilla de por qué ganó la primera: la que verá cualquiera en el hilo de la conversación."""
        primera = ordenadas[0]
        if len(ordenadas) == 1:
            return self.env._('Era la única disponible.')
        segunda = ordenadas[1]
        a, b = cuentas[primera.id], cuentas[segunda.id]
        if a['recibidas'] < b['recibidas']:
            return self.env._('Era quien llevaba menos conversaciones hoy (%s).', a['recibidas'])
        if a['abiertas'] < b['abiertas']:
            return self.env._('Iban parejos hoy y era a quien menos clientes le esperaban.')
        return self.env._('Iban parejos y era quien llevaba más tiempo sin recibir una.')

    @api.model
    def _anotar(self, conversacion, usuario, regla, razon='', hoy=None):
        """Deja la línea en el libro. Una conversación a la misma persona el mismo día cuenta una sola vez."""
        hoy = hoy or self._hoy()
        libro = self.sudo()
        if regla in REGLAS_DE_JUAN and libro.search_count([
                ('conversacion_id', '=', conversacion.id), ('usuario_id', '=', usuario.id), ('dia', '=', hoy),
                ('regla', 'in', REGLAS_DE_JUAN)]):
            return libro.browse()
        return libro.create({'conversacion_id': conversacion.id, 'usuario_id': usuario.id, 'dia': hoy,
                             'regla': regla, 'razon': (razon or '')[:300]})

    @api.model
    def _hace_cuanto(self, momento):
        """«hoy», «ayer» o «hace 3 días»: cuándo fue, en días de Panamá."""
        horario = self.env['dcasa.juan.ajustes'].obtener().horario()
        dias = (self._hoy() - H.a_local(momento, horario).date()).days
        if dias <= 0:
            return self.env._('hoy')
        if dias == 1:
            return self.env._('ayer')
        return self.env._('hace %s días', dias)

    @api.model
    def _vendedora_de_siempre(self, conversacion, candidatas, dias):
        """La persona disponible que atendió a este cliente más recientemente en los últimos ``dias`` días.

        Cuenta lo que escribió ella misma al cliente (en cualquiera de sus conversaciones: WhatsApp, Instagram…) y lo
        que Juan o Gerencia le asignó. Devuelve ``(usuario, momento)`` o ``(vacío, None)``.
        """
        vacio = self.env['res.users']
        if dias <= 0 or not candidatas:
            return vacio, None
        limite = fields.Datetime.now() - timedelta(days=dias)
        Conversacion = self.env['dcasa.conversacion'].sudo()
        conversaciones = conversacion | (Conversacion.search([('partner_id', '=', conversacion.partner_id.id)])
                                         if conversacion.partner_id else Conversacion.browse())
        pruebas = {}
        escritos = self.env['dcasa.mensaje'].sudo()._read_group(
            [('conversacion_id', 'in', conversaciones.ids), ('tipo', '=', 'mensaje'), ('autor', '=', 'vendedora'),
             ('usuario_id', 'in', candidatas.ids), ('ts', '>=', limite)], ['usuario_id'], ['ts:max'])
        asignados = self.sudo()._read_group(
            [('conversacion_id', 'in', conversaciones.ids), ('usuario_id', 'in', candidatas.ids),
             ('momento', '>=', limite)], ['usuario_id'], ['momento:max'])
        for usuario, momento in (*escritos, *asignados):
            if momento and (usuario.id not in pruebas or momento > pruebas[usuario.id]):
                pruebas[usuario.id] = momento
        if not pruebas:
            return vacio, None
        # La más reciente; si dos empatan al segundo, la de id más bajo (siempre la misma).
        uid = min(pruebas, key=lambda i: (-pruebas[i].timestamp(), i))
        return candidatas.browse(uid), pruebas[uid]

    # ------------------------------------------------------------------
    # «No disponible» se reinicia cada mañana
    # ------------------------------------------------------------------

    @api.model
    def _corte_de_la_manana(self):
        """Desde qué momento (UTC) de HOY se reinicia «No disponible»: dos horas antes de abrir la tienda, en la hora de
        Panamá (6:00 a. m. con el horario de 8:00; nunca antes de medianoche). Sigue al horario de Ajustes de Juan."""
        horario = self.env['dcasa.juan.ajustes'].obtener().horario()
        ahora = H.a_local(fields.Datetime.now(), horario)
        medianoche = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        apertura = ahora.replace(hour=horario.inicio.hour, minute=horario.inicio.minute, second=0, microsecond=0)
        return H.a_utc(max(apertura - MARGEN_ANTES_DE_ABRIR, medianoche))

    @api.model
    def _cron_reiniciar_disponibilidad(self):
        """Cada hora (ver el cron): pasada la hora de corte de hoy, deja «Disponible» a toda vendedora que se marcó «No
        disponible» ANTES de ese corte. Así cada mañana empieza con todo el equipo disponible.

        * No toca a quien Gerencia sacó del reparto (vacaciones, ausencia): sigue como estaba hasta que vuelva.
        * No toca a Gerencia ni a administradoras (no reciben, su «Disponible» no significa nada).
        * No toca lo que alguien marcó DESPUÉS del corte: si el contenedor estuvo dormido y el cron corre tarde, una
          pausa de hace cinco minutos no se borra.
        Es idempotente. Devuelve cuántas dejó disponibles.
        """
        ahora = fields.Datetime.now()
        corte = self._corte_de_la_manana()
        if ahora < corte:
            return 0
        hoy = self._hoy()
        pendientes = self._vendedoras().filtered(
            lambda u: not u.dcasa_disponible and u._dcasa_en_el_reparto(hoy)
            and (not u.dcasa_no_disponible_desde or u.dcasa_no_disponible_desde < corte))
        if pendientes:
            pendientes.write({'dcasa_disponible': True, 'dcasa_no_disponible_desde': False})
            _logger.info('Juan: %s vendedora(s) vuelven a «Disponible» al empezar el día.', len(pendientes))
        return len(pendientes)
