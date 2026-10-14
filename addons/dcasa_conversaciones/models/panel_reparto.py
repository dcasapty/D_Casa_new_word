"""La pantalla «Reparto» de Juan: cómo se están repartiendo las conversaciones que el asistente pasa a una persona.

* **Vendedora**: «Mis conversaciones de hoy» — solo lo suyo (cuántas le pasó Juan, cuántos clientes le esperan ahora,
  cuál fue la última y la lista). Nunca ve los números ni los nombres de las demás.
* **Gerencia**: además, una fila por persona del equipo (recibidas, esperando respuesta, última que le tocó y si hoy
  recibe o no), cuántas conversaciones esperan sin que nadie las tenga, y los botones para sacar a alguien del reparto
  (vacaciones, ausencia, quien no atiende clientes) sin quitarle ningún permiso, o para encender el reparto parejo.

Las cuentas salen del libro ``dcasa.reparto`` (ver ``reparto.py``); no se inventa ninguna cifra.
"""
from datetime import timedelta

from markupsafe import escape

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from . import horario as H
from . import panel_calculos as C
from .ajustes import CANALES
from .conversacion_panel import _entero
from .panel_juan import GRUPO_GERENCIA
from .reparto import MAX_FILAS_PROPIAS, REGLAS_DE_JUAN

NOMBRES_DEL_MODO = {
    'manual': 'Apagado: la toma quien quiera',
    'parejo': 'Parejo: a quien lleva menos hoy',
    'turnos': 'Por turnos',
}


class DcasaJuanPanelReparto(models.AbstractModel):
    _inherit = 'dcasa.juan.panel'

    @api.model
    def _exigir_gerencia_del_reparto(self):
        if not self.env.su and not self.env.user.has_group(GRUPO_GERENCIA):
            raise AccessError(self.env._('Solo Gerencia cambia a quién le asigna conversaciones el asistente.'))

    @api.model
    def _minutos_desde(self, momento):
        return int((fields.Datetime.now() - momento).total_seconds() // 60) if momento else None

    @api.model
    def reparto(self, periodo='hoy'):
        """Lo que muestra «Reparto». Gerencia ve a todo el equipo; cada vendedora, solo lo suyo."""
        self.env['dcasa.conversacion']._exigir_vendedora()
        if periodo not in C.PERIODOS:
            raise UserError(self.env._('Periodo desconocido: %s.', periodo))
        Reparto = self.env['dcasa.reparto']
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        horario = ajustes.horario()
        hoy = Reparto._hoy()
        desde = hoy - timedelta(days=C.DIAS_DEL_PERIODO[periodo] - 1)
        yo = self.env.user.sudo()
        es_gerencia = self.env.user.has_group(GRUPO_GERENCIA)
        equipo = self.env['dcasa.conversacion']._usuarios_del_panel()
        # Los números de las demás solo se calculan (y viajan) para Gerencia.
        visibles = equipo if es_gerencia else yo
        cuentas = Reparto._cuentas(visibles | yo, desde, hoy)
        datos = {
            'periodo': periodo, 'periodo_nombre': C.NOMBRES_PERIODO[periodo], 'hoy': hoy.isoformat(),
            'es_gerencia': es_gerencia,
            'modo': ajustes.reparto_modo, 'modo_nombre': NOMBRES_DEL_MODO.get(ajustes.reparto_modo, ''),
            'dias_misma_vendedora': ajustes.reparto_dias_misma_vendedora,
            'yo': self._fila_de(yo, cuentas[yo.id], hoy, horario),
            'mis_conversaciones': self._mis_conversaciones(yo, desde, hoy),
            'equipo': [], 'sin_dueno': None, 'diferencia': None,
        }
        if es_gerencia:
            filas = [self._fila_de(u, cuentas[u.id], hoy, horario) for u in
                     equipo.sorted(lambda u: (u.name or '').lower())]
            filas.sort(key=lambda f: f['estado'] == 'fuera')   # quienes no reciben, al final (el orden se conserva)
            for fila in filas:
                fila['es_yo'] = fila['usuario_id'] == yo.id
            datos['equipo'] = filas
            recibiendo = [f['recibidas'] for f in filas if f['estado'] != 'fuera']
            datos['diferencia'] = (max(recibiendo) - min(recibiendo)) if recibiendo else None
            datos['sin_dueno'] = self._sin_dueno()
        return datos

    @api.model
    def _fila_de(self, usuario, cuenta, hoy, horario):
        fuera = not usuario._dcasa_en_el_reparto(hoy)
        return {
            'usuario_id': usuario.id, 'nombre': usuario.name or '',
            'estado': 'fuera' if fuera else ('disponible' if usuario.dcasa_disponible else 'no_disponible'),
            'fuera_hasta': usuario.dcasa_fuera_hasta.isoformat() if fuera and usuario.dcasa_fuera_hasta else None,
            'recibidas': cuenta['recibidas'], 'abiertas': cuenta['abiertas'],
            'ultima': H.a_iso(cuenta['ultima']),
        }

    @api.model
    def _mis_conversaciones(self, yo, desde, hasta):
        """Las que Juan le pasó a esta persona en el periodo, la más reciente primero (una fila por conversación)."""
        libro = self.env['dcasa.reparto'].sudo().search([
            ('usuario_id', '=', yo.id), ('regla', 'in', REGLAS_DE_JUAN), ('dia', '>=', desde), ('dia', '<=', hasta)],
            order='id desc', limit=MAX_FILAS_PROPIAS * 2)
        filas, vistas = [], set()
        canales = dict(CANALES)
        for linea in libro:
            conv = linea.conversacion_id
            if conv.id in vistas:
                continue
            vistas.add(conv.id)
            esperando = conv.estado == 'humano' and conv.ultimo_mensaje_autor == 'cliente'
            filas.append({
                'conversacion_id': conv.id, 'nombre': conv.partner_id.name or conv.id_externo,
                'canal_nombre': canales.get(conv.canal, conv.canal), 'estado': conv.estado,
                'asignada_en': H.a_iso(linea.momento),
                'esperando_desde': H.a_iso(conv.ultimo_mensaje_cliente) if esperando else None,
                'sigue_conmigo': conv.asignada_a == yo, 'regla': linea.regla,
            })
            if len(filas) >= MAX_FILAS_PROPIAS:
                break
        return filas

    @api.model
    def _sin_dueno(self):
        """Conversaciones donde el cliente espera a una persona y nadie la tiene (y desde cuándo la que más)."""
        sin_dueno = self.env['dcasa.conversacion'].sudo().search([
            ('estado', '=', 'humano'), ('ultimo_mensaje_autor', '=', 'cliente'), ('asignada_a', '=', False)])
        desde = min(filter(None, sin_dueno.mapped('ultimo_mensaje_cliente')), default=None)
        return {'conversaciones': len(sin_dueno), 'espera_mas_min': self._minutos_desde(desde)}

    @api.model
    def fijar_fuera_del_reparto(self, usuario_id, fuera, vuelve=None):
        """Gerencia saca a una persona del reparto (o la vuelve a meter). No le quita ningún permiso: solo deja de
        recibir las conversaciones que el asistente pasa. ``vuelve``: «AAAA-MM-DD», el día en que vuelve (opcional)."""
        self._exigir_gerencia_del_reparto()
        usuario_id = _entero(usuario_id, 'usuario_id', minimo=1)
        if not isinstance(fuera, bool):
            raise UserError(self.env._('Fuera del reparto es sí o no.'))
        usuario = self.env['dcasa.conversacion']._usuarios_del_panel().filtered(lambda u: u.id == usuario_id)
        if not usuario:
            raise UserError(self.env._('Esa persona no es del equipo de ventas.'))
        hoy = self.env['dcasa.reparto']._hoy()
        fecha = False
        if fuera and vuelve:
            fecha = C.fecha_de_iso(vuelve)
            if not fecha:
                raise UserError(self.env._('La fecha en que vuelve no es válida.'))
            if fecha <= hoy:
                raise UserError(self.env._('El día en que vuelve tiene que ser después de hoy.'))
        usuario.write({'dcasa_fuera_del_reparto': fuera, 'dcasa_fuera_hasta': fecha if fuera else False})
        # Queda en el historial de los ajustes quién lo hizo y cuándo.
        if fuera:
            texto = self.env._('%(quien)s sacó a %(a)s del reparto de conversaciones.', quien=self.env.user.name,
                               a=usuario.name)
            if fecha:
                texto = f"{texto} {self.env._('Vuelve el %s.', fecha.strftime('%d/%m/%Y'))}"
        else:
            texto = self.env._('%(quien)s volvió a meter a %(a)s en el reparto de conversaciones.',
                               quien=self.env.user.name, a=usuario.name)
        self.env['dcasa.juan.ajustes'].obtener().sudo().message_post(body=escape(texto), subtype_xmlid='mail.mt_note')
        return {'usuario_id': usuario.id, 'fuera': fuera, 'vuelve': fecha.isoformat() if fecha else None}

    @api.model
    def fijar_modo_reparto(self, modo):
        """Gerencia enciende o apaga el reparto desde la pantalla (lo mismo que Ajustes de Juan → Reparto)."""
        self._exigir_gerencia_del_reparto()
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        if not isinstance(modo, str) or modo not in dict(ajustes._fields['reparto_modo'].selection):
            raise UserError(self.env._('Ese reparto no existe.'))
        ajustes.write({'reparto_modo': modo})   # queda en el historial de los ajustes (campo con seguimiento)
        return {'modo': modo, 'modo_nombre': NOMBRES_DEL_MODO.get(modo, '')}
