"""Las pantallas «Resumen», «Costos de IA» y «Conexiones» de Juan (docs/JUAN_PANEL.md).

* **Resumen** (ventas): mensajes, clientes únicos, resueltas sin una persona, oportunidades creadas, ventas atribuidas
  y tiempo de primera respuesta. Todo sale de lo que Odoo ya guarda; no se inventa ninguna cifra.
* **Costos de IA** (gerencia): gasto del mes, tope, proyección «terminarás el mes en…», por modelo y por día. Lo que
  gastó el Worker se lee de ``GET /odoo/salud`` y ``GET /odoo/costos``. El Worker solo guarda el acumulado del mes por
  modelo, así que el gasto POR DÍA lo arma Odoo con una foto diaria del acumulado (``dcasa.juan.costo.dia``).
* **Conexiones** (gerencia): estado en vivo de cada canal, el QR para vincular WhatsApp (nunca se guarda ni se
  escribe en un registro), reiniciar y desvincular el puente, y qué NOMBRES de claves faltan (jamás valores).

Si el Worker no está configurado, cada pantalla lo dice con claridad («Falta conectar el bot») en vez de fallar.
"""
import logging

from markupsafe import escape

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from . import horario as H
from . import panel_calculos as C
from .ajustes import CANALES

_logger = logging.getLogger(__name__)

GRUPO_GERENCIA = 'sales_team.group_sale_manager'
PREFIJO_QR = 'data:image/png;base64,'
MAX_QR = 200_000
NOMBRES_DE_CLAVES_DEL_ENTORNO = ('JUAN_URL', 'JUAN_WORKER_TOKEN')


class DcasaJuanCostoDia(models.Model):
    """Una foto diaria del gasto de IA acumulado del mes (el Worker no guarda el gasto por día)."""
    _name = 'dcasa.juan.costo.dia'
    _description = 'Gasto de IA acumulado al final de un día'
    _order = 'fecha desc'
    _rec_name = 'fecha'

    fecha = fields.Date('Día (hora de Panamá)', required=True, index=True)
    mes = fields.Char('Mes', required=True, help='AAAA-MM: el Worker reinicia la cuenta cada mes.')
    acumulado_usd = fields.Float('Acumulado del mes (USD)', digits=(12, 6))

    _fecha_unica = models.Constraint('UNIQUE(fecha)', 'Ya hay una foto del gasto de ese día.')

    @api.model
    def _guardar(self, fecha, acumulado):
        """Deja (o sube) la foto del ``fecha``: dentro de un mismo día el acumulado solo crece."""
        existente = self.sudo().search([('fecha', '=', fecha)], limit=1)
        if existente:
            if acumulado > existente.acumulado_usd:
                existente.write({'acumulado_usd': acumulado})
            return existente
        return self.sudo().create({'fecha': fecha, 'mes': fecha.strftime('%Y-%m'), 'acumulado_usd': acumulado})

    @api.model
    def _cron_foto_diaria(self):
        """Cada noche: pide el gasto al Worker y guarda la foto de hoy (si el Worker no responde, no pasa nada)."""
        return self.env['dcasa.juan.panel']._tomar_foto_de_costos()


class DcasaJuanPanel(models.AbstractModel):
    _name = 'dcasa.juan.panel'
    _description = 'Pantallas de resumen, costos y conexiones de Juan'

    # ------------------------------------------------------------------
    # Permisos y ayudas
    # ------------------------------------------------------------------

    @api.model
    def _exigir_gerencia(self):
        if not self.env.su and not self.env.user.has_group(GRUPO_GERENCIA):
            raise AccessError(self.env._('Solo Gerencia ve los costos y las conexiones de Juan.'))

    @api.model
    def _horario(self):
        return self.env['dcasa.juan.ajustes'].obtener().horario()

    @api.model
    def _ahora_local(self):
        return H.a_local(fields.Datetime.now(), self._horario())

    @api.model
    def _detalle_del_fallo(self, respuesta):
        """Por qué no se pudo hablar con el Worker, dicho para una persona."""
        if respuesta.get('estado_http') in (401, 403):
            return ('El Worker no aceptó la clave de Odoo: JUAN_WORKER_TOKEN tiene que ser exactamente la misma '
                    'en Odoo y en el Worker de Juan.')
        return respuesta.get('error') or 'El Worker no respondió.'

    @api.model
    def _sin_conectar(self, extra=None):
        return {
            'configurado': False, 'mensaje': 'Falta conectar el bot',
            'detalle': 'Odoo todavía no sabe dónde está el Worker de Juan ni tiene su clave. Gerencia la carga '
                       '(variables JUAN_URL y JUAN_WORKER_TOKEN) y esta pantalla se llena sola.',
            'faltan': [nombre for nombre, hay in (
                ('JUAN_URL', bool(self.env['dcasa.juan.ajustes'].url_worker())),
                ('JUAN_WORKER_TOKEN', bool(self.env['dcasa.juan.ajustes'].token_worker()))) if not hay],
            **(extra or {}),
        }

    # ------------------------------------------------------------------
    # Resumen
    # ------------------------------------------------------------------

    @api.model
    def resumen(self, periodo='hoy'):
        """Los números del periodo (``hoy``, ``7_dias`` o ``30_dias``, en la hora de Panamá)."""
        self.env['dcasa.conversacion']._exigir_vendedora()
        if periodo not in C.PERIODOS:
            raise UserError(self.env._('Periodo desconocido: %s.', periodo))
        horario = self._horario()
        ahora_local = self._ahora_local()
        inicio_local, fin_local = C.limites_del_periodo(periodo, ahora_local)
        inicio, fin = H.a_utc(inicio_local), H.a_utc(fin_local)
        cr = self.env.cr

        cr.execute("""
            SELECT direccion, autor, COUNT(*), COUNT(DISTINCT conversacion_id)
              FROM dcasa_mensaje
             WHERE tipo = 'mensaje' AND ts >= %s AND ts < %s
          GROUP BY direccion, autor""", [inicio, fin])
        por_autor = {(direccion, autor): n for direccion, autor, n, _c in cr.fetchall()}
        entrantes = por_autor.get(('entrante', 'cliente'), 0)
        del_asistente = por_autor.get(('saliente', 'bot'), 0)
        de_vendedoras = por_autor.get(('saliente', 'vendedora'), 0)

        cr.execute("""
            SELECT COUNT(DISTINCT COALESCE(partner_id::text, 'c' || conversacion_id::text)),
                   COUNT(DISTINCT conversacion_id)
              FROM dcasa_mensaje
             WHERE tipo = 'mensaje' AND autor = 'cliente' AND ts >= %s AND ts < %s""", [inicio, fin])
        clientes_unicos, conversaciones = cr.fetchone()

        # «Resuelta sin humano»: el cliente escribió, contestó el asistente y ninguna persona escribió ni la tomó.
        cr.execute("""
            SELECT COUNT(*)
              FROM dcasa_conversacion c
             WHERE c.estado <> 'humano'
               AND EXISTS (SELECT 1 FROM dcasa_mensaje m WHERE m.conversacion_id = c.id AND m.tipo = 'mensaje'
                              AND m.autor = 'cliente' AND m.ts >= %(i)s AND m.ts < %(f)s)
               AND EXISTS (SELECT 1 FROM dcasa_mensaje m WHERE m.conversacion_id = c.id AND m.tipo = 'mensaje'
                              AND m.autor = 'bot' AND m.ts >= %(i)s AND m.ts < %(f)s)
               AND NOT EXISTS (SELECT 1 FROM dcasa_mensaje m WHERE m.conversacion_id = c.id AND m.tipo = 'mensaje'
                              AND m.autor = 'vendedora' AND m.ts >= %(i)s AND m.ts < %(f)s)""",
                   {'i': inicio, 'f': fin})
        resueltas_sin_humano = cr.fetchone()[0]

        cr.execute("""
            SELECT COUNT(DISTINCT l.id)
              FROM crm_lead l JOIN dcasa_conversacion c ON c.oportunidad_id = l.id
             WHERE l.create_date >= %s AND l.create_date < %s""", [inicio, fin])
        oportunidades = cr.fetchone()[0]

        return {
            'periodo': periodo, 'periodo_nombre': C.NOMBRES_PERIODO[periodo],
            'desde': H.a_iso(inicio), 'hasta': H.a_iso(fin),
            'mensajes': {'total': entrantes + del_asistente + de_vendedoras, 'entrantes': entrantes,
                         'del_asistente': del_asistente, 'de_vendedoras': de_vendedoras},
            'clientes_unicos': clientes_unicos, 'conversaciones': conversaciones,
            'resueltas_sin_humano': resueltas_sin_humano,
            'oportunidades_creadas': oportunidades,
            'ventas': self._ventas_atribuidas(inicio_local.date(), fin_local.date()),
            'primera_respuesta': self._primera_respuesta(inicio, fin),
            'necesitan_atencion': self.env['dcasa.conversacion'].search_count(
                [('estado', '=', 'humano'), ('ultimo_mensaje_autor', '=', 'cliente')]),
            'sin_leer_total': len(self.env['dcasa.conversacion']._ids_con_sin_leer()),
            'es_gerencia': self.env.user.has_group(GRUPO_GERENCIA),
            'bot_conectado': bool(self.env['dcasa.juan.cliente'].configurado()),
            'bot_encendido': bool(self.env['dcasa.juan.ajustes'].obtener().bot_activo_global),
            'zona': horario.zona,
        }

    @api.model
    def _ventas_atribuidas(self, desde, hasta):
        """Facturas PAGADAS de clientes que hablaron con el asistente (el asistente ya había contestado ese día).

        Es atribución por conversación, no causalidad: una compra que el cliente habría hecho igual también cuenta.
        El monto va sin ITBMS (el precio de D'CASA es sin ITBMS).
        """
        self.env.cr.execute("""
            SELECT COUNT(*), COALESCE(SUM(m.amount_untaxed_signed), 0)
              FROM account_move m
             WHERE m.move_type = 'out_invoice' AND m.state = 'posted' AND m.payment_state IN ('paid', 'in_payment')
               AND m.invoice_date >= %(d)s AND m.invoice_date < %(h)s AND m.company_id = %(compania)s
               AND EXISTS (
                   SELECT 1 FROM dcasa_conversacion c
                     JOIN res_partner p ON p.id = c.partner_id
                    WHERE COALESCE(p.commercial_partner_id, p.id) = m.commercial_partner_id
                      AND EXISTS (SELECT 1 FROM dcasa_mensaje b
                                   WHERE b.conversacion_id = c.id AND b.tipo = 'mensaje' AND b.autor = 'bot'
                                     AND b.ts < (m.invoice_date + 1)::timestamp + interval '5 hours'))""",
                            {'d': desde, 'h': hasta, 'compania': self.env.company.id})
        facturas, monto = self.env.cr.fetchone()
        return {'facturas': facturas, 'monto': round(float(monto), 2), 'moneda': self.env.company.currency_id.symbol}

    @api.model
    def _primera_respuesta(self, inicio, fin):
        """Mediana de segundos entre el primer mensaje del cliente y la primera respuesta, de las conversaciones que
        EMPEZARON en el periodo: la primera de cualquiera (asistente o persona) y la primera de una persona."""
        self.env.cr.execute("""
            WITH t AS (
                SELECT m.conversacion_id, MIN(m.ts) AS t_cliente
                  FROM dcasa_mensaje m JOIN dcasa_conversacion c ON c.id = m.conversacion_id
                 WHERE c.inicio >= %s AND c.inicio < %s AND m.tipo = 'mensaje' AND m.autor = 'cliente'
              GROUP BY m.conversacion_id)
            SELECT t.t_cliente,
                   MIN(r.ts) FILTER (WHERE r.autor IN ('bot', 'vendedora')),
                   MIN(r.ts) FILTER (WHERE r.autor = 'vendedora')
              FROM t LEFT JOIN dcasa_mensaje r
                ON r.conversacion_id = t.conversacion_id AND r.tipo = 'mensaje' AND r.direccion = 'saliente'
               AND r.ts >= t.t_cliente
          GROUP BY t.conversacion_id, t.t_cliente""", [inicio, fin])
        filas = self.env.cr.fetchall()
        cualquiera = [(primera - t_cliente).total_seconds() for t_cliente, primera, _p in filas if primera]
        personas = [(persona - t_cliente).total_seconds() for t_cliente, _a, persona in filas if persona]
        mediana_total, mediana_personas = C.mediana(cualquiera), C.mediana(personas)
        return {
            'conversaciones': len(filas),
            'cualquiera_seg': mediana_total, 'cualquiera_texto': C.duracion_corta(mediana_total),
            'persona_seg': mediana_personas, 'persona_texto': C.duracion_corta(mediana_personas),
            'con_respuesta': len(cualquiera), 'con_respuesta_persona': len(personas),
        }

    # ------------------------------------------------------------------
    # Costos de IA
    # ------------------------------------------------------------------

    @api.model
    def _tomar_foto_de_costos(self, informe=None):
        """Guarda el acumulado de hoy (hora de Panamá). Devuelve el informe de salud que usó, o ``None``."""
        Cliente = self.env['dcasa.juan.cliente']
        if informe is None:
            respuesta = Cliente.informe_de_salud() if Cliente.configurado() else None
            informe = respuesta['cuerpo'] if respuesta and respuesta['conectado'] and not respuesta['error'] else None
        gasto = (informe or {}).get('gasto_ia_mes_usd')
        if isinstance(gasto, (int, float)) and not isinstance(gasto, bool) and gasto >= 0:
            self.env['dcasa.juan.costo.dia']._guardar(self._ahora_local().date(), float(gasto))
        return informe

    @api.model
    def costos(self):
        """El gasto de IA del mes, el tope, la proyección y el desglose. Solo Gerencia."""
        self._exigir_gerencia()
        Cliente = self.env['dcasa.juan.cliente']
        if not Cliente.configurado():
            return self._sin_conectar({'ok': False})
        salud = Cliente.informe_de_salud()
        if not salud['conectado'] or salud['error']:
            return {'configurado': True, 'ok': False, 'mensaje': 'No pude hablar con el Worker',
                    'detalle': self._detalle_del_fallo(salud)}
        informe = salud['cuerpo']
        ahora_local = self._ahora_local()
        gasto = float(informe.get('gasto_ia_mes_usd') or 0)
        tope = float(informe.get('tope_usd') or 0)
        self._tomar_foto_de_costos(informe)
        detalle = Cliente.costos()
        cuerpo = detalle['cuerpo'] if detalle['conectado'] and not detalle['error'] else {}
        por_modelo = [{
            'modelo': str(m.get('modelo') or '')[:80], 'usd': round(float(m.get('usd') or 0), 4),
            'turnos': int(m.get('turnos') or 0), 'estimado': bool(m.get('estimado')),
        } for m in (cuerpo.get('por_modelo') or []) if isinstance(m, dict)]
        por_modelo.sort(key=lambda m: -m['usd'])
        mes = ahora_local.strftime('%Y-%m')
        fotos = {f.fecha: f.acumulado_usd for f in self.env['dcasa.juan.costo.dia'].sudo().search(
            [('mes', '=', mes)])}
        por_dia = [{'fecha': dia.isoformat(), 'usd': usd} for dia, usd in C.gasto_por_dia(fotos, mes)]
        proyeccion = C.proyeccion_del_mes(gasto, ahora_local)
        estado = C.estado_del_tope(gasto, proyeccion, tope)
        ia = informe.get('ia') or {}
        return {
            'configurado': True, 'ok': True,
            'mes': mes, 'mes_nombre': f'{H.MESES[ahora_local.month - 1]} de {ahora_local.year}',
            'dia_del_mes': ahora_local.day, 'dias_del_mes': C.dias_del_mes(ahora_local),
            'gasto_usd': round(gasto, 2), 'tope_usd': round(tope, 2),
            'porcentaje_del_tope': round(gasto / tope * 100, 1) if tope > 0 else None,
            'proyeccion_usd': proyeccion, 'estado_del_tope': estado,
            'tope_alcanzado': bool(informe.get('tope_alcanzado')) or estado == 'alcanzado',
            'turnos': int(cuerpo.get('turnos') or sum(m['turnos'] for m in por_modelo)),
            'por_modelo': por_modelo, 'por_dia': por_dia,
            'hay_detalle_por_modelo': bool(por_modelo),
            'modelos_sin_precio': [str(m)[:80] for m in (ia.get('modelos_sin_precio') or [])],
            'ia': {'proveedor': ia.get('proveedor'), 'respaldo': ia.get('respaldo'),
                   'modelo_rapido': ia.get('modelo_rapido'), 'modelo_inteligente': ia.get('modelo_inteligente'),
                   'claves_faltantes': [str(c) for c in (ia.get('claves_faltantes') or [])]},
            'avisos': [str(a)[:300] for a in (informe.get('avisos') or [])][:8],
        }

    # ------------------------------------------------------------------
    # Conexiones
    # ------------------------------------------------------------------

    @api.model
    def _diagnostico_de_odoo(self):
        """Lo que Odoo sabe de su propia configuración (solo sí/no y direcciones públicas, nunca un valor secreto)."""
        ajustes = self.env['dcasa.juan.ajustes']
        base = (self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')
        return {
            'url_del_worker': bool(ajustes.url_worker()), 'token_del_worker': bool(ajustes.token_worker()),
            'token_de_odoo': bool(ajustes.token_odoo()),
            'direccion_de_odoo': base,
            'direccion_de_odoo_sirve_al_puente': C.url_descargable_por_el_puente(base),
            'dominios_del_puente': list(C.DOMINIOS_DEL_PUENTE),
        }

    @api.model
    def conexiones(self):
        """El estado en vivo de cada canal y de las claves del Worker. Solo Gerencia."""
        self._exigir_gerencia()
        odoo = self._diagnostico_de_odoo()
        Cliente = self.env['dcasa.juan.cliente']
        if not Cliente.configurado():
            return self._sin_conectar({'ok': False, 'odoo': odoo, 'canales': []})
        salud = Cliente.informe_de_salud()
        if not salud['conectado'] or salud['error']:
            return {'configurado': True, 'ok': False, 'mensaje': 'No pude hablar con el Worker',
                    'detalle': self._detalle_del_fallo(salud), 'odoo': odoo, 'canales': []}
        informe = salud['cuerpo']
        canales_worker = informe.get('canales') if isinstance(informe.get('canales'), dict) else {}
        canales = []
        for clave, nombre in CANALES:
            datos = canales_worker.get(clave) if isinstance(canales_worker.get(clave), dict) else {}
            canales.append({
                'id': clave, 'nombre': nombre, 'activo': bool(datos.get('activo')),
                'configurado': bool(datos.get('configurado')),
                'conectado': datos.get('conectado') if isinstance(datos.get('conectado'), bool) else None,
                'detalle': str(datos.get('detalle') or '')[:200] or None,
                'faltan': [str(f)[:60] for f in (datos.get('faltan') or []) if isinstance(f, str)],
            })
        ia = informe.get('ia') if isinstance(informe.get('ia'), dict) else {}
        return {
            'configurado': True, 'ok': True, 'todo_bien': bool(informe.get('ok')),
            'mensaje': str(informe.get('mensaje') or '')[:400], 'version': str(informe.get('version') or '')[:40],
            'entorno': str(informe.get('entorno') or '')[:20],
            'canales': canales, 'odoo': odoo,
            'secretos_faltantes': [str(s)[:60] for s in (informe.get('secretos_faltantes') or [])],
            'ia': {'proveedor': ia.get('proveedor'), 'respaldo': ia.get('respaldo'),
                   'claves_faltantes': [str(c)[:60] for c in (ia.get('claves_faltantes') or [])]},
            'problemas': [str(p)[:300] for p in (informe.get('problemas') or [])][:12],
            'avisos': [str(a)[:300] for a in (informe.get('avisos') or [])][:8],
        }

    @api.model
    def qr(self):
        """El código QR para vincular WhatsApp: ``{estado, qr, edad_s, mensaje}``. NUNCA se registra ni se guarda."""
        self._exigir_gerencia()
        respuesta = self.env['dcasa.juan.cliente'].qr()
        if respuesta['sin_configurar']:
            return {'ok': False, 'estado': 'sin_conectar', 'qr': None, 'mensaje': respuesta['error']}
        if respuesta['error'] or not respuesta['conectado']:
            return {'ok': False, 'estado': 'sin_respuesta', 'qr': None,
                    'mensaje': respuesta['error'] or 'El Worker no respondió.'}
        cuerpo = respuesta['cuerpo']
        qr = cuerpo.get('qr')
        # Solo una imagen PNG en base64: cualquier otra cosa no se pinta.
        if not (isinstance(qr, str) and qr.startswith(PREFIJO_QR) and len(qr) <= MAX_QR):
            qr = None
        edad = cuerpo.get('edad_s')
        return {'ok': True, 'estado': str(cuerpo.get('estado') or 'desconocido')[:30], 'qr': qr,
                'edad_s': edad if isinstance(edad, (int, float)) and not isinstance(edad, bool) else None,
                'mensaje': str(cuerpo.get('mensaje') or '')[:300] or None}

    @api.model
    def _accion_del_puente(self, nombre, llamar, texto_aviso):
        self._exigir_gerencia()
        respuesta = llamar()
        if respuesta['sin_configurar']:
            raise UserError(self.env._('Falta conectar el bot: no hay dirección o clave del Worker de Juan.'))
        if respuesta['error'] or not respuesta['conectado'] or respuesta['cuerpo'].get('ok') is False:
            raise UserError(self.env._('No se pudo %(accion)s: %(error)s', accion=nombre, error=(
                respuesta['error'] or str(respuesta['cuerpo'].get('error') or 'el puente no respondió'))[:300]))
        # Queda en el historial de los ajustes quién lo hizo y cuándo.
        self.env['dcasa.juan.ajustes'].obtener().sudo().message_post(
            body=escape(texto_aviso % self.env.user.name), subtype_xmlid='mail.mt_note')
        return {'ok': True, 'mensaje': str(respuesta['cuerpo'].get('mensaje') or '')[:300] or None}

    @api.model
    def reiniciar_puente(self):
        """Reinicia el puente de WhatsApp (la sesión se conserva: no pide QR)."""
        return self._accion_del_puente(
            self.env._('reiniciar el puente'), self.env['dcasa.juan.cliente'].reiniciar_puente,
            self.env._('%s reinició el puente de WhatsApp.'))

    @api.model
    def desvincular_puente(self):
        """Desvincula el número de WhatsApp: para volver a conectar hay que escanear un QR nuevo."""
        return self._accion_del_puente(
            self.env._('desvincular el número'), self.env['dcasa.juan.cliente'].desvincular_puente,
            self.env._('%s desvinculó el número de WhatsApp.'))
