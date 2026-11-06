"""La pantalla «Camila» de la app Marketing: lo que pide y lo que hace (API por RPC).

Cada método exige en el servidor el grupo de marketing (rol «Marketing», Gerencia o administradores) ANTES de tocar
nada, valida cada argumento y escribe con ``sudo`` solo después (el ACL de las campañas es de solo lectura). Lo que
la persona ve del dinero de las ventas que trajo una campaña depende de que vea la ganancia (Gerencia y
administradores): el rol Marketing ve cuántas, no cuánto. Gerencia y administradores también prenden o apagan la línea
«Sí, quiero» del pie y descartan una campaña aprobada que quedó trabada.
"""
from datetime import timedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from . import reglas as R

MAX_HISTORIAL = 8
MAX_BUSQUEDA = 12


class DcasaCamila(models.AbstractModel):
    _inherit = 'dcasa.camila'

    # ------------------------------------------------------------------
    # Lo que se ve
    # ------------------------------------------------------------------

    @api.model
    def panel(self):
        """El borrador abierto (con su vista previa), a cuántos les llegaría, la última campaña y el historial."""
        self._exigir()
        con_permiso = len(self.env['res.partner'].sudo()._dcasa_promos_con_permiso())
        campana = self._abierta()
        ultima, proxima, puede = self._proxima(excepto=campana or None)
        enviadas = self.env['dcasa.camila.campana'].sudo().search([('estado', '=', 'enviada')],
                                                                 order='enviada_en desc, id desc', limit=MAX_HISTORIAL)
        dia_ultima = self._dia_panama(ultima.enviada_en) if ultima else None
        return {
            've_dinero': self._ve_dinero(),
            'hay_clave': bool(self._clave()),
            'entorno': self._entorno() or '',
            'con_permiso': con_permiso,
            'bloqueos': self._bloqueos(campana or None, con_permiso=con_permiso),
            'ultima': {'nombre': ultima.name, 'asunto': ultima.asunto, 'fecha': self._fecha_texto(dia_ultima),
                       'hace': self._hace(dia_ultima)} if ultima else None,
            'proxima': {'fecha': self._fecha_texto(proxima), 'ya': puede},
            'campana': self._campana_para_pantalla(campana) if campana else None,
            'historial': [dict(self._resultados(c), id=c.id, nombre=c.name, asunto=c.asunto,
                               fecha=self._fecha_texto(self._dia_panama(c.enviada_en)))
                          for c in enviadas],
            'limites': {'asunto': R.MAX_ASUNTO, 'entrada': R.MAX_ENTRADA, 'linea': R.MAX_LINEA,
                        'productos': R.MAX_PRODUCTOS},
            'dias': R.DIAS_ENTRE_CAMPANAS,
            'enlace_pie': {'encendido': self._enlace_pie_encendido(), 'puede_cambiar': self._ve_dinero()},
        }

    @api.model
    def _campana_para_pantalla(self, campana):
        campana = campana.sudo()
        return {
            'id': campana.id,
            'nombre': campana.name,
            'estado': campana.estado,
            'estado_nombre': dict(campana._fields['estado'].selection).get(campana.estado),
            'asunto': campana.asunto or '',
            'entrada': campana.entrada or '',
            'fuente': dict(campana._fields['fuente'].selection).get(campana.fuente, ''),
            'nota': campana.nota or '',
            'error': campana.error or '',
            'html': campana.html or '',
            'huella': campana.huella or '',
            'marca': campana.marca,
            'automatica': campana.automatica,
            'precios_del': self._fecha_texto(self._dia_panama(campana.precios_del)),
            'prueba': {'a': campana.prueba_a, 'fecha': self._fecha_texto(self._dia_panama(campana.prueba_en))}
            if campana.prueba_a else None,
            'editable': campana.estado == 'borrador',
            'puede_descartar': self._puede_intentar_descartar(campana),
            'lineas': [{
                'producto_id': linea.producto_id.id, 'nombre': linea.nombre, 'texto': linea.texto or '',
                'grupo': linea.grupo, 'grupo_nombre': dict(R.GRUPOS).get(linea.grupo, ''),
                'precio': linea.precio_texto, 'mas_itbms': linea.mas_itbms,
                'miniatura': f'/web/image/product.template/{linea.producto_id.id}/image_128'
                if linea.producto_id else '',
            } for linea in campana.linea_ids],
        }

    @api.model
    def _puede_intentar_descartar(self, campana):
        """Si la pantalla ofrece «Descartar»: el borrador siempre; una aprobada, solo a Gerencia o un administrador
        cuando ya no se está enviando (el servidor revisa lo demás en Resend al tocarlo)."""
        if campana.estado == 'borrador':
            return True
        if campana.estado != 'aprobada' or not self._ve_dinero():
            return False
        from .envio import MINUTOS_ENVIANDO

        return bool(campana.resend_broadcast_id or not campana.enviando_desde
                    or fields.Datetime.now() - campana.enviando_desde >= timedelta(minutes=MINUTOS_ENVIANDO))

    # ------------------------------------------------------------------
    # Lo que se hace
    # ------------------------------------------------------------------

    @api.model
    def armar(self):
        """«Armar la campaña» / «Volver a armar»: productos, precios y texto de hoy. Nunca envía."""
        self._exigir()
        campana = self._abierta()
        if campana:
            campana = self._bloquear(campana.id)
            if campana.estado != 'borrador':
                raise UserError(self.env._('Esta campaña ya se está enviando: no se puede volver a armar.'))
        self._armar(campana=campana or None)
        return self.panel()

    @api.model
    def guardar(self, campana_id, cambios):
        """Guarda lo que editó la persona: el asunto, la entrada y los productos (en orden, con su línea). Los precios
        y las fotos los pone Odoo; el texto pasa por la misma revisión de marca que el de la IA."""
        self._exigir()
        if not isinstance(cambios, dict):
            raise UserError(self.env._('No entendí los cambios.'))
        campana = self._editable(campana_id)
        errores = []
        valores = {}
        for campo, maximo, nombre in (('asunto', R.MAX_ASUNTO, self.env._('El asunto')),
                                      ('entrada', R.MAX_ENTRADA, self.env._('La entrada'))):
            if campo in cambios:
                texto = R.limpiar(cambios[campo]) if isinstance(cambios[campo], str) else ''
                errores += [f'{nombre}: {p}' for p in R.problemas(texto, maximo)]
                valores[campo] = texto
        if 'lineas' in cambios:
            valores['linea_ids'] = self._lineas_editadas(campana, cambios['lineas'], errores)
        if errores:
            raise UserError('\n'.join(errores))
        if valores:
            valores['editada_por'] = self.env.uid
            if any(campo in cambios for campo in ('asunto', 'entrada', 'lineas')):
                valores.update(fuente='persona', nota=False)   # ya lo revisó y lo cambió una persona
            campana.write(valores)
            self._guardar_html(campana)
        return self.panel()

    @api.model
    def _editable(self, campana_id):
        campana = self._bloquear(campana_id)
        if campana.estado != 'borrador':
            raise UserError(self.env._('Esta campaña ya no se puede cambiar (%s).',
                                       dict(campana._fields['estado'].selection).get(campana.estado)))
        return campana

    @api.model
    def _lineas_editadas(self, campana, lineas, errores):
        """Los comandos para dejar los productos como los pidió la persona (validando cada uno)."""
        if not isinstance(lineas, list) or not lineas:
            errores.append(self.env._('La campaña necesita al menos un producto.'))
            return []
        if len(lineas) > R.MAX_PRODUCTOS:
            errores.append(self.env._('Como mucho %s productos por campaña.', R.MAX_PRODUCTOS))
            return []
        pedidos = []
        for fila in lineas:
            if not isinstance(fila, dict) or isinstance(fila.get('producto_id'), bool) \
                    or not isinstance(fila.get('producto_id'), int):
                errores.append(self.env._('Un producto de la lista no es válido.'))
                return []
            pedidos.append((fila['producto_id'], fila.get('texto')))
        ids = [pid for pid, _texto in pedidos]
        if len(set(ids)) != len(ids):
            errores.append(self.env._('Un producto está repetido.'))
            return []
        elegibles = self._elegibles(self._sitio(), ids=ids)
        actuales = {linea.producto_id.id: linea for linea in campana.linea_ids}
        comandos = [Command.clear()]
        for secuencia, (pid, pedido) in enumerate(pedidos, start=1):
            dato = elegibles.get(pid)
            if not dato:
                nombre = self.env['product.template'].sudo().browse(pid).exists().display_name or str(pid)
                errores.append(self.env._('«%s» no se puede ofrecer: tiene que estar en tienda, con foto, con precio y '
                                          'publicado en la tienda en línea.', nombre))
                continue
            anterior = actuales.get(pid)
            grupo = anterior.grupo if anterior else 'elegido'
            texto = R.limpiar(pedido) if isinstance(pedido, str) else (anterior.texto if anterior else '')
            texto = texto or R.linea_fija(grupo)
            nombre = dato['plantilla']._dcasa_nombre_cliente()
            errores.extend(f'{nombre}: {problema}' for problema in R.problemas(texto, R.MAX_LINEA))
            comandos.append(Command.create(self._valores_linea(dato, grupo, texto, secuencia)))
        return comandos

    @api.model
    def buscar_productos(self, texto=''):
        """Productos que sí pueden ir en la campaña (en tienda, con foto, con precio y publicados), por nombre o
        código, para agregar o cambiar uno."""
        self._exigir()
        texto = R.limpiar(texto, 80) if isinstance(texto, str) else ''
        website = self._sitio()
        dominio = self._dominio_elegible(website)
        if texto:
            dominio = Domain.AND([dominio, Domain.OR([[('name', 'ilike', texto)], [('default_code', 'ilike', texto)],
                                                      [('dcasa_codigo_publico', 'ilike', texto)]])])
        plantillas = self.env['product.template'].sudo().search(dominio, order='website_sequence, id',
                                                                 limit=MAX_BUSQUEDA * 2)
        elegibles = self._elegibles(website, ids=plantillas.ids)
        moneda = website.currency_id
        return [{'id': pid, 'nombre': dato['plantilla']._dcasa_nombre_cliente(),
                 'precio': self.env['dcasa.correo']._monto(dato['precio'], moneda), 'mas_itbms': dato['mas_itbms'],
                 'miniatura': f'/web/image/product.template/{pid}/image_128'}
                for pid, dato in list(elegibles.items())[:MAX_BUSQUEDA]]

    @api.model
    def enviar_prueba(self, campana_id):
        """«Enviarme una prueba»: solo al correo de quien la pide (por los correos de siempre, clase «prueba»)."""
        self._exigir()
        destino = self._enviar_prueba(campana_id)
        return {'mensaje': self.env._('Te mandé la prueba a %s. Ábrela en el celular.', destino)}

    @api.model
    def enviar(self, campana_id, huella=''):
        """«Enviar a N clientes»: el servidor revisa todo otra vez (ver ``_enviar``)."""
        self._exigir()
        if not isinstance(huella, str):
            raise UserError(self.env._('No entendí qué versión de la campaña viste.'))
        resultado = self._enviar(campana_id, huella)
        return dict(resultado, panel=self.panel())

    @api.model
    def descartar(self, campana_id):
        """Descarta el borrador (queda en el historial como cancelado). Una aprobada que quedó trabada solo la
        descartan Gerencia o un administrador, y solo si en Resend no salió ni va a salir (ver ``_descartar``)."""
        self._exigir()
        self._descartar(self._bloquear(campana_id))
        return self.panel()

    @api.model
    def ajustar_enlace_pie(self, encendido):
        """Prende o apaga la línea «¿Te avisamos de lo nuevo? Sí, quiero» del pie de la factura y la bienvenida (y si
        sus enlaces anotan). Gerencia o administradores; de fábrica, encendida."""
        self._exigir()
        if not isinstance(encendido, bool):
            raise UserError(self.env._('No entendí si prenderla o apagarla.'))
        self._enlace_ajustar(encendido)
        return self.panel()

    @api.model
    def actualizar_resultados(self, campana_id):
        """Trae otra vez de Resend las entregas, aperturas, clics y bajas de una campaña enviada."""
        self._exigir()
        if isinstance(campana_id, bool) or not isinstance(campana_id, int):
            raise UserError(self.env._('Esa campaña no es válida.'))
        campana = self.env['dcasa.camila.campana'].sudo().browse(campana_id).exists()
        if not campana or campana.estado != 'enviada':
            raise UserError(self.env._('Esa campaña no se ha enviado.'))
        from .resend_campanas import ErrorResend

        try:
            hubo = self._actualizar_resultados(campana)
        except ErrorResend as error:
            raise UserError(self.env._('Resend no dio los resultados: %s', error.mensaje)) from None
        if not hubo:
            raise UserError(self.env._('Los resultados de Resend solo se leen en producción y con la clave de '
                                       'campañas.'))
        return self.panel()
