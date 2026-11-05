"""Sofía revisa el CRM y deja propuestas (pedido de la dueña, 2026-11-05). No cambia nada por su cuenta.

Lo que mira, en este orden (una sola propuesta de mensaje por cliente y por revisión, la más urgente):

1. **Contestar**: clientes que una vendedora tiene y le escribieron hace más de una hora sin respuesta.
2. **Su cotización vence** hoy o mañana: un recordatorio amable para el cliente.
3. **Escribirle**: tibios y calientes a los que ninguna vendedora les escribió en 24 horas («A quién escribirle hoy»)
   y que Juan no está atendiendo en este momento. Si Juan está por mandarles su seguimiento automático (en las próximas
   2 horas, o ya lo está mandando) se le deja; si lo tenía para más adelante, la propuesta lo dice: al escribirle una
   persona, la conversación pasa a ella y ese seguimiento ya no sale (como siempre que una vendedora escribe).
4. **Pedir sus datos** (pedido de la dueña, 2026-11-05): a los tibios y calientes cuya ficha no tiene nombre y apellido
   de verdad (un emoji, una frase, una empresa, solo un nombre) o no tiene correo, un mensaje profesional que se los
   pide para avisarle de promociones, del programa Socios y de los beneficios de cumpleaños. Si ya toca escribirle, va
   al final del mismo mensaje. A quien ya se le pidió no se le vuelve a pedir en 30 días.
5. **Guardar su correo**: el cliente escribió su correo en el chat y su ficha no lo tiene.
6. **Llamarlo**: por Messenger, Instagram o WhatsApp oficial ya pasaron 24 horas desde su último mensaje (Meta no deja
   escribirle) y tiene celular: una tarea para llamarlo.
7. **Repartir** (solo Gerencia): oportunidades tibias o calientes sin vendedora (a su vendedora de siempre o a quien
   lleva menos) y oportunidades cuya vendedora no es la que atiende su chat.

Lo que NO toca: el proceso de Juan (sus conversaciones, su reparto, sus seguimientos), la etapa ni la temperatura.
"""
import logging
from datetime import timedelta

from psycopg2.errors import UniqueViolation

from odoo import api, fields, models
from odoo.addons.dcasa_contactos.models import claves
from odoo.addons.dcasa_conversaciones.models import crm_reglas as CRM
from odoo.addons.dcasa_conversaciones.models import horario as H
from odoo.addons.dcasa_conversaciones.models.ajustes import CANALES
from odoo.addons.dcasa_socios.models import bien_escrito as B
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import SQL

from . import reglas as R
from .propuesta import CON_MENSAJE, SOLO_GERENCIA

_logger = logging.getLogger(__name__)

MAX_OPORTUNIDADES = 3000      # las más recientes; si hay más, se anota cuántas quedaron fuera
MAX_POR_TIPO = 150            # la pantalla muestra las más urgentes de cada tipo; el resto se cuenta
HORAS_SIN_CONTESTAR = 1       # «contestar»: el cliente espera a una persona desde hace al menos una hora…
DIAS_SIN_CONTESTAR = 7        # …y desde hace menos de una semana (más que eso ya no es «esperando»)
HORAS_EN_CURSO = 2            # Juan está conversando con el cliente ahora: no se mete nadie
JUAN_POR_ESCRIBIR = timedelta(hours=2)   # Juan está por mandarle su seguimiento automático: se le deja
HORAS_APROBADA = 20           # lo que se aprobó hoy no vuelve en la revisión siguiente del mismo día
DIAS_CORREOS = 30             # mensajes del cliente en los que se busca su correo
MAX_MENSAJES_CON_CORREO = 500
DIAS_VENCE = 1                # cotizaciones que vencen hoy o mañana
INTERES_POR_DEFECTO = 'nuestros muebles'
CANDADO = 'dcasa_sofia_revision'


def nombre_de_pila(usuario):
    palabras = (usuario.name or '').split() if usuario else []
    return palabras[0] if palabras else ''


class Sofia(models.AbstractModel):
    _name = 'dcasa.sofia'
    _description = 'Sofía, la asistente del CRM'

    # ------------------------------------------------------------------
    # La revisión
    # ------------------------------------------------------------------

    @api.model
    def _analizar(self, origen='boton'):
        """Revisa el CRM y deja las propuestas al día. Devuelve la revisión (``dcasa.sofia.corrida``).

        Solo una a la vez (candado de la base): si otra persona ya pidió una revisión, esta espera su turno o avisa.
        """
        self.env.cr.execute(SQL('SELECT pg_try_advisory_xact_lock(hashtext(%s))', CANDADO))
        if not self.env.cr.fetchone()[0]:
            raise UserError(self.env._('Sofía ya está revisando el CRM. Espera unos segundos y vuelve a mirar.'))
        Reparto = self.env['dcasa.reparto']
        ctx = {
            'ahora': fields.Datetime.now(),
            'hoy': Reparto._hoy(),
            'ajustes': self.env['dcasa.juan.ajustes'].obtener(),
            'juan': self.env.ref('dcasa_conversaciones.user_juan', raise_if_not_found=False) or self.env['res.users'],
            'equipo_partners': set(self.env['res.partner']._dcasa_contactos_del_equipo().ids),
            'con_mensaje': set(),      # ('p', cliente) y ('c', chat) que ya tienen un mensaje en esta revisión
            'datos_pedidos': self._datos_pedidos_hace_poco(),
            'omitidas': {},
        }
        ctx['suprimidas'] = self._claves_suprimidas(ctx)
        corrida = self.env['dcasa.sofia.corrida'].sudo().create({
            'origen': origen, 'usuario_id': self.env.uid if origen == 'boton' else False, 'dia': ctx['hoy']})
        leads = self._oportunidades(ctx)
        candidatas = []
        candidatas += self._contestar(ctx)
        candidatas += self._vencen(ctx)
        candidatas += self._escribir_y_pedir_datos(leads, ctx)
        candidatas += self._guardar_correos(ctx)
        candidatas += self._repartir(leads, ctx)
        cuentas = self._guardar(candidatas, corrida, ctx)
        corrida.write({'fin': fields.Datetime.now(), **cuentas, 'omitidas': ctx['omitidas'] or False})
        return corrida

    @api.model
    def _oportunidades(self, ctx):
        """Pendientes, abiertas y de una conversación: las que Sofía mira (las más recientes, con tope)."""
        Lead = self.env['crm.lead'].sudo()
        dominio = [('type', '=', 'opportunity'), ('active', '=', True), ('won_status', '=', 'pending'),
                   ('dcasa_conversacion_ids', '!=', False)]
        total = Lead.search_count(dominio)
        if total > MAX_OPORTUNIDADES:
            ctx['omitidas']['oportunidades'] = total - MAX_OPORTUNIDADES
            _logger.warning('Sofía: %s oportunidades; reviso las %s más recientes.', total, MAX_OPORTUNIDADES)
        return Lead.search(dominio, order='id desc', limit=MAX_OPORTUNIDADES)

    # ------------------------------------------------------------------
    # Ayudas
    # ------------------------------------------------------------------

    @api.model
    def _vale_como_vendedora(self, usuario, ctx):
        return bool(usuario) and usuario.active and not usuario.share and usuario != ctx['juan']

    @api.model
    def _para_quien(self, ctx, *usuarios):
        """La primera persona del equipo de la lista (la de la cotización, la de la oportunidad, la del chat)."""
        for usuario in usuarios:
            if self._vale_como_vendedora(usuario, ctx):
                return usuario
        return self.env['res.users']

    @api.model
    def _datos_pedidos_hace_poco(self):
        """Clientes a los que ya se les pidió su nombre o su correo en los días de Ajustes (para no insistir).

        Solo cuenta si el mensaje salió de verdad: con «Enviar ya», o con «Abrir el chat» y después una vendedora le
        escribió en ese chat. Aprobar con «Crear tarea» o abrir el chat sin escribir no cuenta como pedido."""
        dias = self.env['dcasa.juan.ajustes'].obtener().sofia_dias_datos or 30
        desde = fields.Datetime.now() - timedelta(days=dias)
        propuestas = self.env['dcasa.sofia.propuesta'].sudo().search([
            ('pide_datos', '=', True), ('estado', '=', 'aplicada'), ('resuelta_en', '>=', desde),
            ('accion', 'in', ('enviar', 'chat'))])
        pedidos = set(propuestas.filtered(lambda p: p.accion == 'enviar').partner_id.ids)
        Mensaje = self.env['dcasa.mensaje'].sudo()
        for propuesta in propuestas.filtered(lambda p: p.accion == 'chat' and p.conversacion_id):
            if Mensaje.search_count([
                    ('conversacion_id', '=', propuesta.conversacion_id.id), ('autor', '=', 'vendedora'),
                    ('tipo', '=', 'mensaje'), ('ts', '>=', propuesta.resuelta_en),
                    ('estado_envio', 'not in', ('programado', 'fallido'))], limit=1):
                pedidos.add(propuesta.partner_id.id)
        return pedidos

    @api.model
    def _claves_suprimidas(self, ctx):
        """Lo que no se vuelve a proponer todavía: lo descartado en los días de Ajustes y lo aprobado hace menos de
        20 horas. Se mira ANTES de apartar el mensaje del cliente: algo descartado no le quita lugar a lo demás."""
        dias = ctx['ajustes'].sofia_dias_sin_repetir or 7
        aprobada = ctx['ahora'] - timedelta(hours=HORAS_APROBADA)
        suprimidas = set()
        for fila in self.env['dcasa.sofia.propuesta'].sudo().search_read(
                [('estado', 'in', ('aplicada', 'descartada')),
                 ('resuelta_en', '>=', ctx['ahora'] - timedelta(days=dias))], ['clave', 'estado', 'resuelta_en']):
            if fila['estado'] == 'descartada' or fila['resuelta_en'] >= aprobada:
                suprimidas.add(fila['clave'])
        return suprimidas

    @api.model
    def _ocupado(self, ctx, partner, conv):
        """¿Ese cliente o ese chat ya tienen un mensaje propuesto en esta revisión? (uno solo, el más urgente)"""
        return ('p', partner.id) in ctx['con_mensaje'] or ('c', conv.id) in ctx['con_mensaje']

    @api.model
    def _ocupar(self, ctx, partner, conv):
        ctx['con_mensaje'].update({('p', partner.id), ('c', conv.id)})

    @api.model
    def _abierta(self, lead):
        """La oportunidad si sigue abierta (ni ganada ni perdida); si no, vacío."""
        return lead if lead and lead.active and lead.won_status == 'pending' else lead.browse()

    @api.model
    def _cliente(self, partner, ctx, conv=None):
        """¿Es un cliente al que se le puede escribir? (no del equipo, no pidió que no lo contacten). Se mira la ficha
        y también la del chat (pueden ser distintas: el contacto de una empresa)."""
        fichas = [f for f in (partner, conv.partner_id if conv else None) if f]
        return bool(partner) and all(
            f.id not in ctx['equipo_partners'] and not f.dcasa_no_contactar for f in fichas)

    @api.model
    def _provisionales(self, conv):
        return (self.env['res.partner']._dcasa_conv_nombre_provisional(conv.canal, conv.id_externo),)

    @api.model
    def _celular(self, partner, conv):
        return partner.phone or conv.celular or ''

    @api.model
    def _canal(self, conv):
        return dict(CANALES).get(conv.canal, conv.canal or '')

    @api.model
    def _faltan_datos(self, partner, conv, ctx):
        """``(sin_nombre, sin_correo, motivo)``: los datos de contacto que le faltan a su ficha (o ``False`` si ya se le
        pidieron hace poco o no falta nada)."""
        if partner.id in ctx['datos_pedidos']:
            return False, False, ''
        sin_nombre = R.falta_el_nombre(partner.name, self._provisionales(conv))
        sin_correo = R.falta_el_correo(partner.email)
        partes = []
        if sin_nombre:
            partes.append(sin_nombre)
        if sin_correo:
            partes.append('no tiene correo' if not partner.email else 'su correo está mal escrito')
        return bool(sin_nombre), sin_correo, ', '.join(partes)

    @api.model
    def _valores(self, partner, conv, lead=None, orden=None):
        """Los datos para llenar la plantilla (todo menos {vendedora}, que es quien la envía)."""
        # Lo que anotó Juan y lo que dijo el cliente pueden traer un precio: entonces no se usa (nunca cifras).
        interes = R.sin_montos(R.sin_canal(conv._interes() if conv and conv.oportunidad_id else '',
                                           [nombre for _clave, nombre in CANALES]))
        return {
            'nombre': R.primer_nombre(partner.name, self._provisionales(conv)) if conv else '',
            'interes': (interes or INTERES_POR_DEFECTO)[:80],
            'cotizacion': orden.name if orden else '',
            'vence': orden.validity_date.strftime('%d/%m/%Y') if orden and orden.validity_date else '',
            'para_cuando': R.sin_montos(lead.dcasa_para_cuando) if lead else '',
        }

    @api.model
    def _base(self, tipo, clave, ctx, **valores):
        """Una propuesta candidata con lo común ya puesto."""
        propuesta = {
            'tipo': tipo, 'clave': clave, 'solo_gerencia': tipo in SOLO_GERENCIA,
            'prioridad': R.prioridad(tipo, valores.get('temperatura'), valores.pop('vence_hoy', False)),
        }
        propuesta.update(valores)
        return propuesta

    @api.model
    def _juan_esta_por_escribir(self, conv, ctx):
        """¿Juan ya está mandando su seguimiento automático o lo manda en las próximas 2 horas? Entonces se le deja:
        dos mensajes seguidos (el de Juan y el de la vendedora) se verían mal."""
        proximo = conv.seguimiento_proximo
        return bool(conv.seguimiento_pedido_en) or bool(proximo and proximo <= ctx['ahora'] + JUAN_POR_ESCRIBIR)

    @api.model
    def _nota_de_juan(self, conv, ctx):
        """Si Juan tenía un seguimiento automático para más adelante: que quien aprueba sepa que ya no saldrá (al
        escribirle una persona, la conversación pasa a ella y Juan calla, como siempre)."""
        if not conv.seguimiento_proximo:
            return ''
        local = H.a_local(conv.seguimiento_proximo, ctx['ajustes'].horario())
        return self.env._(' Juan le iba a escribir solo el %s; si le escribes tú, ese seguimiento ya no sale.',
                          local.strftime('%d/%m'))

    @api.model
    def _llamar_o_nada(self, conv, partner, usuario, lead, ctx, motivo):
        """Ya no se le puede escribir por su canal (ventana de 24 horas de Meta): una tarea para llamarlo, si tiene
        celular. Si no lo tiene, no hay nada que proponer."""
        celular = self._celular(partner, conv)
        clave = f'llamar:partner:{partner.id}'
        if not celular or clave in ctx['suprimidas']:
            return []
        self._ocupar(ctx, partner, conv)
        return [self._base(
            'llamar', clave, ctx, temperatura=lead.dcasa_temperatura if lead else False,
            usuario_id=usuario.id or False, lead_id=lead.id if lead else False, conversacion_id=conv.id,
            partner_id=partner.id, titulo=self.env._('Llámalo al %s', celular),
            motivo=self.env._('%(motivo)s. Por %(canal)s ya pasaron 24 horas desde su último mensaje y no se le '
                              'puede escribir hasta que vuelva a escribir.', motivo=motivo, canal=self._canal(conv)),
            datos={'celular': celular})]

    # ------------------------------------------------------------------
    # 1. Contestar
    # ------------------------------------------------------------------

    @api.model
    def _contestar(self, ctx):
        ahora = ctx['ahora']
        conversaciones = self.env['dcasa.conversacion'].sudo().search([
            ('estado', '=', 'humano'), ('ultimo_mensaje_autor', '=', 'cliente'),
            ('ultimo_mensaje_cliente', '<=', ahora - timedelta(hours=HORAS_SIN_CONTESTAR)),
            ('ultimo_mensaje_cliente', '>=', ahora - timedelta(days=DIAS_SIN_CONTESTAR))])
        salida = []
        for conv in conversaciones:
            partner = conv.partner_id
            if not self._cliente(partner, ctx, conv) or self._ocupado(ctx, partner, conv):
                continue
            lead = self._abierta(conv.oportunidad_id)   # quien ya compró también espera respuesta
            usuario = self._para_quien(ctx, conv.asignada_a, conv.oportunidad_id.user_id)
            espera = self.env['dcasa.reparto']._hace_cuanto(conv.ultimo_mensaje_cliente)
            horas = int((ahora - conv.ultimo_mensaje_cliente).total_seconds() // 3600)
            motivo = self.env._('Te escribió %(cuando)s (hace %(horas)s h) y espera respuesta.',
                                cuando=espera, horas=horas)
            if not R.ventana_abierta(conv.canal, conv.ultimo_mensaje_cliente, ahora):
                salida += self._llamar_o_nada(conv, partner, usuario, lead, ctx, motivo)
                continue
            # Cada vez que el cliente vuelve a escribir es otra espera: descartar una no esconde las siguientes.
            clave = f'contestar:conv:{conv.id}:{conv.ultimo_cliente_msg_id or 0}'
            if clave in ctx['suprimidas']:
                continue
            self._ocupar(ctx, partner, conv)
            salida.append(self._base(
                'contestar', clave, ctx, temperatura=lead.dcasa_temperatura or False,
                usuario_id=usuario.id or False, lead_id=lead.id or False, conversacion_id=conv.id,
                partner_id=partner.id, titulo=self.env._('Contéstale: espera respuesta'), motivo=motivo))
        return salida

    # ------------------------------------------------------------------
    # 2. Su cotización vence
    # ------------------------------------------------------------------

    @api.model
    def _vencen(self, ctx):
        hoy = ctx['hoy']
        ordenes = self.env['sale.order'].sudo().search([
            ('state', 'in', ('draft', 'sent')), ('locked', '=', False), ('validity_date', '>=', hoy),
            ('validity_date', '<=', hoy + timedelta(days=DIAS_VENCE)), ('amount_total', '>', 0)],
            order='validity_date, id', limit=MAX_POR_TIPO * 2)
        salida = []
        Conversacion = self.env['dcasa.conversacion'].sudo()
        for orden in ordenes:
            partner = orden.partner_id.commercial_partner_id if orden.partner_id.parent_id else orden.partner_id
            clave = f'vence:orden:{orden.id}'
            if clave in ctx['suprimidas']:
                continue
            lead = self._abierta(orden.opportunity_id)
            conv = (orden.opportunity_id.dcasa_conversacion_ids[:1] if orden.opportunity_id else Conversacion) \
                or Conversacion.search([('partner_id', '=', partner.id)], limit=1)
            if not conv or not self._cliente(partner, ctx, conv) or self._ocupado(ctx, partner, conv):
                continue
            if self._juan_esta_por_escribir(conv, ctx):
                continue   # si Juan está por escribirle, se le deja
            usuario = self._para_quien(ctx, orden.user_id, orden.opportunity_id.user_id, conv.asignada_a)
            vence_hoy = orden.validity_date == hoy
            cuando = self.env._('hoy') if vence_hoy else self.env._('mañana')
            motivo = self.env._('Su cotización %(n)s vence %(cuando)s y no la ha confirmado.', n=orden.name,
                                cuando=cuando)
            if not R.ventana_abierta(conv.canal, conv.ultimo_mensaje_cliente, ctx['ahora']):
                salida += self._llamar_o_nada(conv, partner, usuario, lead, ctx, motivo)
                continue
            self._ocupar(ctx, partner, conv)
            sin_nombre, sin_correo, falta = self._faltan_datos(partner, conv, ctx)
            valores = self._valores(partner, conv, lead, orden)
            valores['que_falta'] = R.que_falta(sin_nombre, sin_correo)
            salida.append(self._base(
                'vence', clave, ctx, vence_hoy=vence_hoy,
                temperatura=lead.dcasa_temperatura or False, usuario_id=usuario.id or False, lead_id=lead.id or False,
                conversacion_id=conv.id, partner_id=partner.id, orden_id=orden.id,
                titulo=self.env._('Recuérdale su cotización (vence %s)', cuando),
                motivo=motivo + (self.env._(' Además, %s.', falta) if falta else '') + self._nota_de_juan(conv, ctx),
                plantilla='cotizacion_por_vencer', pide_datos=bool(sin_nombre or sin_correo),
                datos={'valores': valores, 'vence_el': fields.Date.to_string(orden.validity_date)}))
        return salida

    # ------------------------------------------------------------------
    # 3 y 4. Escribirle y pedir sus datos
    # ------------------------------------------------------------------

    @api.model
    def _escribir_y_pedir_datos(self, leads, ctx):
        ahora = ctx['ahora']
        tibias = leads.filtered(lambda lead: lead.dcasa_temperatura in (CRM.TIBIO, CRM.CALIENTE))
        para_hoy = set(self.env['crm.lead'].sudo()._search(
            Domain(self.env['crm.lead']._dcasa_dominio_para_hoy()) & Domain('id', 'in', tibias.ids)))
        salida = []
        for lead in tibias:
            conv = lead.dcasa_conversacion_ids[:1]
            partner = lead.partner_id or conv.partner_id
            if not conv or not self._cliente(partner, ctx, conv) or self._ocupado(ctx, partner, conv):
                continue
            if conv.estado == 'humano' and conv.ultimo_mensaje_autor == 'cliente':
                continue   # le está esperando a una persona: eso es «contestar»
            if conv.estado != 'humano' and conv.ultimo_mensaje_cliente \
                    and ahora - conv.ultimo_mensaje_cliente < timedelta(hours=HORAS_EN_CURSO):
                continue   # Juan está conversando con él ahora mismo: nadie se mete
            if self._juan_esta_por_escribir(conv, ctx):
                continue   # Juan está por mandarle su seguimiento (o ya lo está mandando): se le deja
            if f'escribir:lead:{lead.id}' in ctx['suprimidas']:
                continue   # alguien descartó (o acaba de aprobar) escribirle: tampoco se le piden datos aparte
            sin_nombre, sin_correo, falta = self._faltan_datos(partner, conv, ctx)
            pide = sin_nombre or sin_correo
            toca_escribir = lead.id in para_hoy
            if not toca_escribir and (not pide or f'pedir_datos:partner:{partner.id}' in ctx['suprimidas']):
                continue
            usuario = self._para_quien(ctx, lead.user_id, conv.asignada_a)
            temperatura = lead.dcasa_temperatura
            nivel = CRM.NOMBRE_TEMPERATURA.get(temperatura, '').lower()
            if not R.ventana_abierta(conv.canal, conv.ultimo_mensaje_cliente, ahora):
                if toca_escribir:
                    salida += self._llamar_o_nada(conv, partner, usuario, lead, ctx, self.env._(
                        'Está %(nivel)s y nadie del equipo le ha escrito en 24 horas', nivel=nivel))
                continue
            self._ocupar(ctx, partner, conv)
            orden = lead.order_ids.filtered(lambda o: o.state in ('draft', 'sent'))[:1]
            valores = self._valores(partner, conv, lead, orden)
            valores['que_falta'] = R.que_falta(sin_nombre, sin_correo)
            comun = {'temperatura': temperatura, 'usuario_id': usuario.id or False, 'lead_id': lead.id,
                     'conversacion_id': conv.id, 'partner_id': partner.id, 'orden_id': orden.id or False,
                     'pide_datos': bool(pide), 'datos': {'valores': valores}}
            if toca_escribir:
                plantilla = ('seguimiento_cotizacion' if orden else
                             'seguimiento_cuando' if valores['para_cuando'] else 'seguimiento_interes')
                motivo = self.env._('Está %(nivel)s (%(por_que)s) y nadie del equipo le ha escrito en 24 horas.',
                                    nivel=nivel, por_que=lead.dcasa_temperatura_motivo or nivel)
                salida.append(self._base(
                    'escribir', f'escribir:lead:{lead.id}', ctx, plantilla=plantilla,
                    titulo=self.env._('Escríbele: está %s', nivel),
                    motivo=motivo + (self.env._(' Además, %s: el mensaje le pide sus datos.', falta) if pide else '')
                    + self._nota_de_juan(conv, ctx),
                    **comun))
            else:
                salida.append(self._base(
                    'pedir_datos', f'pedir_datos:partner:{partner.id}', ctx, plantilla='pedir_datos',
                    titulo=self.env._('Pídele sus datos: está %s', nivel),
                    motivo=self.env._('Está %(nivel)s y %(falta)s. Con su nombre y su correo se le puede avisar de '
                                      'promociones, del programa Socios y de su cumpleaños.', nivel=nivel, falta=falta)
                    + self._nota_de_juan(conv, ctx),
                    **comun))
        return salida

    # ------------------------------------------------------------------
    # 5. Guardar su correo
    # ------------------------------------------------------------------

    @api.model
    def _guardar_correos(self, ctx):
        mensajes = self.env['dcasa.mensaje'].sudo().search([
            ('autor', '=', 'cliente'), ('tipo', '=', 'mensaje'), ('texto', 'ilike', '@'),
            ('tiene_sensible', '=', False), ('ts', '>=', ctx['ahora'] - timedelta(days=DIAS_CORREOS)),
            ('conversacion_id.partner_id', '!=', False)], order='ts desc, id desc', limit=MAX_MENSAJES_CON_CORREO)
        correos_del_equipo = self.env['res.partner']._dcasa_correos_del_equipo()
        salida, vistos = [], set()
        for mensaje in mensajes:
            conv = mensaje.conversacion_id
            partner = conv.partner_id
            if partner.id in vistos or partner.email or not self._cliente(partner, ctx) \
                    or f'guardar_correo:partner:{partner.id}' in ctx['suprimidas']:
                continue
            for escrito in R.correos_en(mensaje.texto):
                correo = B.correo_limpio(escrito)
                if not correo or correo in correos_del_equipo:
                    continue
                llave = claves.llave_correo(correo)
                otra = llave and partner._dcasa_otra_ficha('correo', llave)
                if otra:
                    continue   # ese correo es de otra ficha: lo resuelve Gerencia en «Posibles duplicados»
                vistos.add(partner.id)
                lead = conv.oportunidad_id
                usuario = self._para_quien(ctx, lead.user_id, conv.asignada_a)
                salida.append(self._base(
                    'guardar_correo', f'guardar_correo:partner:{partner.id}', ctx,
                    temperatura=lead.dcasa_temperatura or False, usuario_id=usuario.id or False,
                    lead_id=lead.id or False, conversacion_id=conv.id, partner_id=partner.id,
                    titulo=self.env._('Guarda su correo: %s', correo),
                    motivo=self.env._('Lo escribió en el chat %s y su ficha no tiene correo.',
                                      self.env['dcasa.reparto']._hace_cuanto(mensaje.ts)),
                    datos={'correo': correo}))
                break
        return salida

    # ------------------------------------------------------------------
    # 7. Repartir (solo Gerencia)
    # ------------------------------------------------------------------

    @api.model
    def _repartir(self, leads, ctx):
        Reparto = self.env['dcasa.reparto']
        vendedoras = Reparto._vendedoras()
        equipo = Reparto._equipo(ctx['hoy'])
        disponibles = equipo.filtered('dcasa_disponible') or equipo
        dias = ctx['ajustes'].reparto_dias_misma_vendedora
        carga = {u.id: 0 for u in equipo}
        if equipo:
            for usuario, cuenta in self.env['crm.lead'].sudo()._read_group(
                    [('type', '=', 'opportunity'), ('active', '=', True), ('won_status', '=', 'pending'),
                     ('user_id', 'in', equipo.ids)], ['user_id'], ['__count']):
                carga[usuario.id] = cuenta
        salida = []
        for lead in leads:
            conv = lead.dcasa_conversacion_ids.filtered(lambda c: c.asignada_a in vendedoras)[:1]
            asignada = conv.asignada_a
            temperatura = lead.dcasa_temperatura
            if asignada and lead.user_id != asignada:
                if f'sincronizar:lead:{lead.id}' in ctx['suprimidas']:
                    continue
                antes = lead.user_id.name or self.env._('nadie')
                salida.append(self._base(
                    'sincronizar', f'sincronizar:lead:{lead.id}', ctx, temperatura=temperatura, lead_id=lead.id,
                    conversacion_id=conv.id, partner_id=(lead.partner_id or conv.partner_id).id or False,
                    destino_id=asignada.id,
                    titulo=self.env._('Pon a %s en la oportunidad', asignada.name),
                    motivo=self.env._('%(ella)s atiende su chat, pero la oportunidad dice «%(antes)s».',
                                      ella=asignada.name, antes=antes),
                    datos={'antes': lead.user_id.id or False}))
                continue
            if temperatura not in (CRM.TIBIO, CRM.CALIENTE) or self._vale_como_vendedora(lead.user_id, ctx):
                continue
            if not disponibles or f'asignar:lead:{lead.id}' in ctx['suprimidas']:
                continue
            conv = lead.dcasa_conversacion_ids[:1]
            destino, momento = Reparto._vendedora_de_siempre(conv, equipo, dias)
            if destino:
                razon = self.env._('Era su vendedora de siempre (lo atendió %s).', Reparto._hace_cuanto(momento))
            else:
                destino = disponibles.sorted(lambda u: (carga.get(u.id, 0), u.dcasa_turno, u.id))[0]
                razon = self.env._('Es quien lleva menos oportunidades abiertas (%s).', carga.get(destino.id, 0))
            carga[destino.id] = carga.get(destino.id, 0) + 1
            nivel = CRM.NOMBRE_TEMPERATURA.get(temperatura, '').lower()
            salida.append(self._base(
                'asignar', f'asignar:lead:{lead.id}', ctx, temperatura=temperatura, lead_id=lead.id,
                conversacion_id=conv.id or False, partner_id=(lead.partner_id or conv.partner_id).id or False,
                destino_id=destino.id, titulo=self.env._('Dásela a %s', destino.name),
                motivo=self.env._('Está %(nivel)s y no tiene vendedora. %(razon)s', nivel=nivel, razon=razon),
                datos={'antes': lead.user_id.id or False}))
        return salida

    # ------------------------------------------------------------------
    # Guardar: poner al día las propuestas pendientes
    # ------------------------------------------------------------------

    @api.model
    def _guardar(self, candidatas, corrida, ctx):
        """Crea las nuevas, pone al día las que siguen y deja «ya no hacía falta» las que no. Devuelve las cuentas."""
        Propuesta = self.env['dcasa.sofia.propuesta'].sudo()
        ahora = ctx['ahora']
        pendientes = {p.clave: p for p in Propuesta.search([('estado', '=', 'pendiente')])}
        # Las más urgentes primero; por tipo, solo hasta el tope (el resto se cuenta, no se esconde en silencio).
        candidatas.sort(key=lambda c: (-c['prioridad'], -int(c.get('temperatura') or 0)))
        por_tipo, vistas, quedan = {}, set(), []
        siguen = set()
        for c in candidatas:
            if c['clave'] in vistas or c['clave'] in ctx['suprimidas']:
                continue
            vistas.add(c['clave'])
            por_tipo[c['tipo']] = por_tipo.get(c['tipo'], 0) + 1
            if por_tipo[c['tipo']] > MAX_POR_TIPO:
                ctx['omitidas'][c['tipo']] = ctx['omitidas'].get(c['tipo'], 0) + 1
                if c['clave'] in pendientes:
                    siguen.add(pendientes[c['clave']].id)   # sigue haciendo falta: no se marca «ya no hacía falta»
                continue
            quedan.append(c)
        nuevas = 0
        for c in quedan:
            valores = dict(c)
            valores.setdefault('plantilla', False)
            valores.setdefault('pide_datos', False)
            for campo in ('usuario_id', 'lead_id', 'conversacion_id', 'partner_id', 'orden_id', 'destino_id'):
                valores.setdefault(campo, False)
            existente = pendientes.get(c['clave'])
            if existente:
                siguen.add(existente.id)
                cambios = self._cambios(existente, valores)
                if cambios:   # solo lo que cambió: menos choques con quien la está aprobando
                    existente.write(cambios)
                continue
            try:
                # Otra revisión (de una foto de la base anterior) pudo crearla un instante antes: no es un error.
                with self.env.cr.savepoint():
                    Propuesta.create({**valores, 'corrida_id': corrida.id})
                nuevas += 1
            except UniqueViolation:
                _logger.info('Sofía: la propuesta %s ya la había creado otra revisión.', c['clave'])
        sobran = Propuesta.browse([p.id for p in pendientes.values() if p.id not in siguen])
        if sobran:
            sobran._resolver('vencida', self.env._('Ya no hacía falta en la revisión de %s.',
                                                   self.env['dcasa.reparto']._hace_cuanto(ahora)))
        resumen = {}
        for c in quedan:
            resumen[c['tipo']] = resumen.get(c['tipo'], 0) + 1
        return {'total': len(quedan), 'nuevas': nuevas, 'vencidas': len(sobran), 'resumen': resumen}

    @api.model
    def _cambios(self, propuesta, valores):
        """Los campos de ``valores`` que difieren de lo que ya tiene la propuesta."""
        cambios = {}
        for campo, valor in valores.items():
            actual = propuesta[campo]
            if propuesta._fields[campo].type == 'many2one':
                actual = actual.id or False
            if actual != valor and not (not actual and not valor):
                cambios[campo] = valor
        return cambios

    # ------------------------------------------------------------------
    # El mensaje que se propone
    # ------------------------------------------------------------------

    @api.model
    def _texto(self, propuesta, quien, textos=None):
        """El mensaje de una propuesta, armado con las plantillas vigentes y el nombre de quien lo enviará."""
        if propuesta.tipo not in CON_MENSAJE or not propuesta.plantilla:
            return ''
        textos = textos if textos is not None else self.env['dcasa.sofia.plantilla']._textos()
        valores = dict((propuesta.datos or {}).get('valores') or {})
        valores['vendedora'] = nombre_de_pila(quien)
        texto = R.rellenar(textos.get(propuesta.plantilla, ''), valores)
        if propuesta.pide_datos and propuesta.tipo != 'pedir_datos' and textos.get('posdata_datos'):
            texto = f"{texto}\n\n{R.rellenar(textos['posdata_datos'], valores)}"
        return texto
