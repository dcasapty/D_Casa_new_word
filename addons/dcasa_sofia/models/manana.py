"""La revisión de cada mañana y el resumen por Telegram (pedido de la dueña, 2026-11-05: «botón y cada mañana»).

El cron corre cada 30 minutos pero solo hace algo una vez al día: media hora después de abrir (horario de Ajustes de
Juan), si ese día todavía no hubo revisión de la mañana. Cada vendedora con Telegram vinculado recibe LO SUYO (cuántas
cosas tiene y las más urgentes) y Gerencia el resumen de todo. El aviso nunca hace fallar la revisión.
"""
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.dcasa_conversaciones.models import horario as H

_logger = logging.getLogger(__name__)

MINUTOS_DESPUES_DE_ABRIR = 30
MAS_URGENTES = 5
GRUPO_VENDEDORA = 'sales_team.group_sale_salesman'
# (una, varias) por tipo, para el resumen.
FRASES = {
    'contestar': ('cliente espera respuesta', 'clientes esperan respuesta'),
    'vence': ('cotización vence hoy o mañana', 'cotizaciones vencen hoy o mañana'),
    'escribir': ('cliente para escribirle', 'clientes para escribirles'),
    'llamar': ('cliente para llamar', 'clientes para llamar'),
    'pedir_datos': ('cliente para pedirle sus datos', 'clientes para pedirles sus datos'),
    'guardar_correo': ('correo para guardar en su ficha', 'correos para guardar en sus fichas'),
    'asignar': ('oportunidad sin vendedora', 'oportunidades sin vendedora'),
    'sincronizar': ('oportunidad con otra vendedora en el chat', 'oportunidades con otra vendedora en el chat'),
}
ORDEN = list(FRASES)
DONDE = 'Ábrelo en Odoo › CRM › Sofía.'


def lineas_por_tipo(propuestas):
    cuentas = {}
    for propuesta in propuestas:
        cuentas[propuesta.tipo] = cuentas.get(propuesta.tipo, 0) + 1
    return [f'• {n} {FRASES[tipo][0 if n == 1 else 1]}' for tipo in ORDEN if (n := cuentas.get(tipo))]


class SofiaManana(models.AbstractModel):
    _inherit = 'dcasa.sofia'

    @api.model
    def _cron_manana(self):
        """Una vez al día, media hora después de abrir: revisa el CRM y avisa por Telegram. Devuelve si lo hizo."""
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        if not ajustes.sofia_manana:
            return False
        horario = ajustes.horario()
        ahora = fields.Datetime.now()
        if not H.dentro_de_horario(ahora, horario):
            return False
        local = H.a_local(ahora, horario)
        apertura = local.replace(hour=horario.inicio.hour, minute=horario.inicio.minute, second=0, microsecond=0)
        if local < apertura + timedelta(minutes=MINUTOS_DESPUES_DE_ABRIR):
            return False
        Corrida = self.env['dcasa.sofia.corrida'].sudo()
        if Corrida.search_count([('origen', '=', 'manana'), ('dia', '=', local.date())]):
            return False
        corrida = self.sudo()._analizar('manana')
        if ajustes.sofia_telegram:
            corrida.avisos_telegram = self._avisar_por_telegram()
        return True

    @api.model
    def _avisar_por_telegram(self):
        """A cada vendedora lo suyo y a Gerencia el resumen. Devuelve cuántos avisos salieron. Nunca falla."""
        Enlace = self.env['brian.telegram.enlace'].sudo()
        enlaces = Enlace.search([('activo', '=', True)])
        if not enlaces:
            return 0
        pendientes = self.env['dcasa.sofia.propuesta'].sudo().search([('estado', '=', 'pendiente')])
        gerencia = self.env['dcasa.reparto']._gerencia_que_recibe_avisos()
        enviados = 0
        for enlace in enlaces:
            usuario = enlace.user_id
            if not usuario.active or not usuario.has_group(GRUPO_VENDEDORA):
                continue
            if usuario in gerencia:
                texto = self._resumen_para_gerencia(usuario, pendientes)
            else:
                texto = self._resumen_para_vendedora(
                    usuario, pendientes.filtered(lambda p, u=usuario: p.usuario_id == u and not p.solo_gerencia))
            if not texto:
                continue
            try:
                with self.env.cr.savepoint():
                    Enlace._enviar(enlace.chat_id, texto)
                    enviados += 1
            except Exception:   # noqa: BLE001 — el aviso es un extra: nunca tumba la revisión
                _logger.exception('Sofía: no se pudo avisar por Telegram a %s', usuario.login)
        return enviados

    @api.model
    def _resumen_para_vendedora(self, usuario, propias):
        if not propias:
            return ''
        nombre = (usuario.name or '').split()[0] if usuario.name else ''
        partes = [f'Buenos días, {nombre}. Sofía revisó el CRM y te dejó {len(propias)} '
                  f'{"cosa" if len(propias) == 1 else "cosas"} para hoy:', *lineas_por_tipo(propias), '',
                  'Lo más urgente:']
        for i, propuesta in enumerate(propias[:MAS_URGENTES], start=1):
            cliente = propuesta.partner_id.display_name or propuesta.conversacion_id.name or ''
            partes.append(f'{i}. {cliente}: {propuesta.titulo}')
        partes += ['', DONDE]
        return '\n'.join(partes)

    @api.model
    def _resumen_para_gerencia(self, usuario, pendientes):
        if not pendientes:
            return ''
        nombre = (usuario.name or '').split()[0] if usuario.name else ''
        partes = [f'Buenos días, {nombre}. Sofía revisó el CRM: {len(pendientes)} '
                  f'{"propuesta pendiente" if len(pendientes) == 1 else "propuestas pendientes"}.']
        repartir = pendientes.filtered('solo_gerencia')
        if repartir:
            partes += ['', 'Para ti (repartir):', *lineas_por_tipo(repartir)]
        por_persona = {}
        for propuesta in pendientes - repartir:
            quien = propuesta.usuario_id.name or 'Sin vendedora'
            por_persona[quien] = por_persona.get(quien, 0) + 1
        if por_persona:
            partes += ['', 'Por vendedora: ' + ' · '.join(
                f'{quien} {n}' for quien, n in sorted(por_persona.items(), key=lambda par: (-par[1], par[0])))]
        partes += ['', DONDE]
        return '\n'.join(partes)
