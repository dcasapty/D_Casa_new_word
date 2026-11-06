"""La pantalla «Camila» de la app Marketing: lo que pide y lo que hace (API por RPC).

Cada método exige en el servidor el grupo de marketing (rol «Marketing», Gerencia o administradores) ANTES de tocar
nada, valida cada argumento y escribe con ``sudo`` solo después (el ACL de las campañas es de solo lectura). Lo que
la persona ve del dinero de las ventas que trajo una campaña depende de que vea la ganancia (Gerencia y
administradores): el rol Marketing ve cuántas, no cuánto. Gerencia y administradores también prenden o apagan la línea
«Sí, quiero» del pie y descartan una campaña aprobada que quedó trabada.

Etapa 2 (decisiones de la dueña, 2026-11-06): varias campañas abiertas a la vez («Nueva campaña» desde una idea, desde
lo nuevo, lo más vendido, lo quieto, lo que más hay o en blanco, y «Crear campaña con estos» desde el tablero de
Marketing), el público con chips del CRM, el redactor con IA (por producto y desde la idea) y el buscador de productos
con filtros. A la IA solo le llegan datos de productos y la idea.
"""
from datetime import timedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from . import reglas as R
from .camila import ErrorIA

MAX_HISTORIAL = 8
MAX_BUSQUEDA = 24
MAX_CATEGORIAS = 30
# Los interruptores del correo que se editan en la pantalla (al menos un botón, decisión de la dueña, 2026-11-06).
CAMPOS_BOTONES = {'whatsapp': 'boton_whatsapp', 'web': 'boton_web', 'productos': 'enlaces_productos',
                  'redes': 'redes'}


def _id_valido(valor):
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


class DcasaCamila(models.AbstractModel):
    _inherit = 'dcasa.camila'

    # ------------------------------------------------------------------
    # Lo que se ve
    # ------------------------------------------------------------------

    @api.model
    def panel(self, campana_id=False):
        """Las campañas abiertas, la elegida (con su público, su vista previa y sus productos), la última que salió,
        el historial y los ajustes. Sin ``campana_id`` (o si ya no está abierta), la más reciente."""
        self._exigir()
        if campana_id not in (False, None) and not _id_valido(campana_id):
            raise UserError(self.env._('Esa campaña no es válida.'))
        abiertas = self._abiertas()
        campana = abiertas.filtered(lambda c: c.id == campana_id)[:1] if campana_id else abiertas[:1]
        if not campana:
            campana = abiertas[:1]
        con_permiso = len(self.env['res.partner'].sudo()._dcasa_promos_con_permiso())
        publico = self._publico_para_pantalla(campana) if campana else None
        ultima = self._ultima_enviada()
        enviadas = self.env['dcasa.camila.campana'].sudo().search([('estado', '=', 'enviada')],
                                                                 order='enviada_en desc, id desc', limit=MAX_HISTORIAL)
        dia_ultima = self._dia_panama(ultima.enviada_en) if ultima else None
        return {
            've_dinero': self._ve_dinero(),
            'hay_clave': bool(self._clave()),
            'entorno': self._entorno() or '',
            'con_permiso': con_permiso,
            'bloqueos': self._bloqueos(campana or None, con_permiso=con_permiso, publico=publico),
            'ultima': {'nombre': ultima.name, 'asunto': ultima.asunto, 'fecha': self._fecha_texto(dia_ultima),
                       'hace': self._hace(dia_ultima)} if ultima else None,
            'abiertas': [{'id': c.id, 'nombre': c.name, 'asunto': c.asunto or '', 'estado': c.estado,
                          'estado_nombre': dict(c._fields['estado'].selection).get(c.estado),
                          'productos': len(c.linea_ids)} for c in abiertas],
            'campana': dict(self._campana_para_pantalla(campana), publico=publico) if campana else None,
            'historial': [dict(self._resultados(c), id=c.id, nombre=c.name, asunto=c.asunto,
                               fecha=self._fecha_texto(self._dia_panama(c.enviada_en)))
                          for c in enviadas],
            'limites': {'asunto': R.MAX_ASUNTO, 'entrada': R.MAX_ENTRADA, 'linea': R.MAX_LINEA,
                        'productos': R.MAX_PRODUCTOS, 'idea': R.MAX_IDEA},
            'dias': R.DIAS_ENTRE_CAMPANAS,
            'temas': [{'clave': clave, 'nombre': nombre} for clave, nombre in R.TEMAS if clave != 'mezcla'],
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
            'idea': campana.idea or '',
            'tema': campana.tema or 'mezcla',
            'tema_nombre': dict(R.TEMAS).get(campana.tema or 'mezcla', ''),
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
            'botones': {'whatsapp': campana.boton_whatsapp, 'web': campana.boton_web,
                        'productos': campana.enlaces_productos, 'redes': campana.redes},
            'redes_del_sitio': [red['nombre'] for red in self._redes()],
            'lineas': [{
                'producto_id': linea.producto_id.id, 'nombre': linea.nombre, 'texto': linea.texto or '',
                'grupo': linea.grupo, 'grupo_nombre': dict(R.GRUPOS).get(linea.grupo, ''),
                'precio': linea.precio_texto, 'mas_itbms': linea.mas_itbms,
                'existencias': linea.producto_id.sudo().dcasa_stock if linea.producto_id else 0,
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

    @api.model
    def _tarjeta(self, dato, moneda):
        plantilla = dato['plantilla']
        return {'id': plantilla.id, 'nombre': plantilla._dcasa_nombre_cliente(),
                'categoria': plantilla.categ_id.name or '', 'existencias': plantilla.dcasa_stock,
                'precio': self.env['dcasa.correo']._monto(dato['precio'], moneda), 'mas_itbms': dato['mas_itbms'],
                'miniatura': f'/web/image/product.template/{plantilla.id}/image_256', 'elegible': True, 'motivo': ''}

    # ------------------------------------------------------------------
    # Campañas nuevas y volver a armar
    # ------------------------------------------------------------------

    @api.model
    def nueva(self, opciones=None):
        """«Nueva campaña» (y «Crear campaña con estos» del tablero de Marketing): ``{tema, idea?, productos?}``.

        * ``tema``: de dónde salen los productos (``reglas.TEMAS``): una idea, lo nuevo, los más vendidos, los quietos,
          lo que más hay, lo de mayor movimiento o en blanco.
        * ``idea``: lo que el equipo quiere decir (obligatoria con «Desde una idea»: la IA sugiere los productos y
          escribe el texto con ella; si la IA no puede sugerir, quedan los de siempre y la pantalla lo dice).
        * ``productos``: una lista de ids (el tablero de Marketing): solo van los que se pueden ofrecer.
        Nunca envía: deja un borrador nuevo y devuelve la pantalla con él."""
        self._exigir()
        opciones = opciones if isinstance(opciones, dict) else {}
        tema = opciones.get('tema') or 'mezcla'
        if tema not in dict(R.TEMAS):
            raise UserError(self.env._('No entendí de dónde armar la campaña.'))
        idea = R.limpiar(opciones['idea'], R.MAX_IDEA) if isinstance(opciones.get('idea'), str) else ''
        productos = opciones.get('productos')
        if productos is not None and (not isinstance(productos, list) or not all(_id_valido(p) for p in productos)):
            raise UserError(self.env._('La lista de productos no es válida.'))
        aviso = ''
        if tema == 'idea':
            if not idea:
                raise UserError(self.env._('Escribe la idea de la campaña.'))
            if productos is None:
                try:
                    productos = [dato['plantilla'].id for dato in self._sugerir(idea)]
                except ErrorIA as error:
                    aviso = self.env._('%s Quedaron lo nuevo, lo más vendido y lo quieto: cámbialos si quieres.',
                                       str(error))
        campana = self._armar(tema=tema, productos=productos, idea=idea)
        if aviso:
            campana.sudo().write({'nota': ' '.join(filter(None, [aviso, campana.nota or '']))[:250]})
        return self.panel(campana.id)

    @api.model
    def armar(self, campana_id=False):
        """«Volver a armar» una campaña (sus productos según su tema y el texto con su idea) o, sin ``campana_id``,
        armar una nueva con lo nuevo, lo más vendido y lo quieto. Nunca envía."""
        self._exigir()
        if not campana_id:
            return self.panel(self._armar().id)
        campana = self._editable(campana_id)
        self._armar(campana=campana, tema='mezcla' if campana.tema == 'blanco' else campana.tema)
        return self.panel(campana.id)

    # ------------------------------------------------------------------
    # Editar
    # ------------------------------------------------------------------

    @api.model
    def guardar(self, campana_id, cambios):
        """Guarda lo que editó la persona: el asunto, la entrada, los productos (en orden, con su línea), la idea, el
        público y los botones del correo. Los precios y las fotos los pone Odoo; el texto pasa por la misma revisión de
        marca que el de la IA."""
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
        valores.update(self._ajustes_editados(campana, cambios, errores))
        if errores:
            raise UserError('\n'.join(errores))
        if valores:
            valores['editada_por'] = self.env.uid
            if any(campo in cambios for campo in ('asunto', 'entrada', 'lineas')):
                valores.update(fuente='persona', nota=False)   # ya lo revisó y lo cambió una persona
            campana.write(valores)
            self._guardar_html(campana)
        return self.panel(campana.id)

    @api.model
    def _ajustes_editados(self, campana, cambios, errores):
        """La idea, el público (chips) y los botones del correo (al menos uno), validados."""
        valores = {}
        if 'idea' in cambios:
            if not isinstance(cambios['idea'], str):
                errores.append(self.env._('La idea tiene que ser texto.'))
            else:
                valores['idea'] = R.limpiar(cambios['idea'], R.MAX_IDEA) or False
        if 'publico' in cambios:
            if not isinstance(cambios['publico'], list) or not all(isinstance(c, str) for c in cambios['publico']):
                errores.append(self.env._('No entendí a quién va.'))
            else:
                valores['publico'] = ','.join(R.leer_chips(cambios['publico']))
        if 'botones' in cambios:
            botones = cambios['botones']
            if not isinstance(botones, dict) or any(k not in CAMPOS_BOTONES or not isinstance(v, bool)
                                                    for k, v in botones.items()):
                errores.append(self.env._('No entendí los botones del correo.'))
            elif not (botones.get('whatsapp', campana.boton_whatsapp) or botones.get('web', campana.boton_web)):
                errores.append(self.env._('El correo necesita al menos un botón: «Escríbenos por WhatsApp», '
                                          '«Visita nuestra tienda en línea» o los dos.'))
            else:
                valores.update({CAMPOS_BOTONES[k]: v for k, v in botones.items()})
        return valores

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
            if not isinstance(fila, dict) or not _id_valido(fila.get('producto_id')):
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

    # ------------------------------------------------------------------
    # El redactor con IA
    # ------------------------------------------------------------------

    @api.model
    def escribir(self, campana_id, que, producto_id=False):
        """«Escribir con IA»: ``que`` = ``linea`` (de ``producto_id``, con sus datos reales), ``asunto``, ``entrada`` o
        ``todo`` (con la idea y los productos elegidos). Lo deja en la campaña. Si la IA falla o lo que escribe no
        pasa la revisión de marca, ``{ok: False, mensaje}`` para que la pantalla lo diga y ofrezca «Reintentar»."""
        self._exigir()
        if que not in ('linea', 'asunto', 'entrada', 'todo'):
            raise UserError(self.env._('No entendí qué escribir.'))
        if que == 'linea' and not _id_valido(producto_id):
            raise UserError(self.env._('Ese producto no es válido.'))
        campana = self._editable(campana_id)
        try:
            escrito = self._escribir(campana, que, producto_id if que == 'linea' else None)
        except ErrorIA as error:
            return {'ok': False, 'mensaje': str(error)}
        return {'ok': True, 'escrito': {str(k): v for k, v in escrito.items()}, 'panel': self.panel(campana.id)}

    @api.model
    def sugerir_productos(self, campana_id, idea=False):
        """«Sugerir productos para esta idea»: la IA escoge de lo que se puede ofrecer (sin los que ya están). Devuelve
        las tarjetas para el buscador, o ``{ok: False, mensaje}``."""
        self._exigir()
        campana = self._editable(campana_id)
        idea = idea if isinstance(idea, str) and idea.strip() else campana.idea
        try:
            datos = self._sugerir(idea, excluir=set(campana.linea_ids.producto_id.ids))
        except ErrorIA as error:
            return {'ok': False, 'mensaje': str(error)}
        moneda = self._sitio().currency_id
        return {'ok': True, 'productos': [self._tarjeta(dato, moneda) for dato in datos]}

    # ------------------------------------------------------------------
    # El buscador de productos (el diálogo de «Cambiar» y «Agregar»)
    # ------------------------------------------------------------------

    @api.model
    def buscar_productos(self, texto='', filtros=None):
        """Productos por nombre o código con filtros (categoría, en tienda, con foto, publicado). Cada tarjeta dice si
        se puede ofrecer y, si no, por qué (solo se agregan los que están en tienda, con foto, con precio y
        publicados). Devuelve ``{productos, categorias}``; precios y existencias de Odoo."""
        self._exigir()
        texto = R.limpiar(texto, 80) if isinstance(texto, str) else ''
        filtros = filtros if isinstance(filtros, dict) else {}
        website = self._sitio()
        Plantilla = self.env['product.template'].sudo()
        dominio = Domain([('sale_ok', '=', True), ('active', '=', True), ('type', '!=', 'service')])
        if filtros.get('en_tienda', True):
            dominio = Domain.AND([dominio, [('is_storable', '=', True), ('dcasa_stock', '>', 0)]])
        if filtros.get('con_foto', True):
            dominio = Domain.AND([dominio, [('image_1920', '!=', False)]])
        if filtros.get('publicado', True):
            dominio = Domain.AND([dominio, website.with_user(website.user_id)._dcasa_dominio_publicado()])
        if _id_valido(filtros.get('categoria_id')):
            dominio = Domain.AND([dominio, [('categ_id', 'child_of', filtros['categoria_id'])]])
        if texto:
            dominio = Domain.AND([dominio, Domain.OR([[('name', 'ilike', texto)], [('default_code', 'ilike', texto)],
                                                      [('dcasa_codigo_publico', 'ilike', texto)]])])
        plantillas = Plantilla.search(dominio, order='website_sequence, id', limit=MAX_BUSQUEDA)
        elegibles = self._elegibles(website, ids=plantillas.ids)
        precios = self._precios(plantillas, website)
        publicados = set(Plantilla.search(Domain.AND([
            [('id', 'in', plantillas.ids)], website.with_user(website.user_id)._dcasa_dominio_publicado()])).ids)
        moneda = website.currency_id
        productos = []
        for plantilla in plantillas:
            if plantilla.id in elegibles:
                productos.append(self._tarjeta(elegibles[plantilla.id], moneda))
                continue
            precio, mas_itbms = precios.get(plantilla.id, (0.0, False))
            if not (plantilla.is_storable and plantilla.dcasa_stock > 0):
                motivo = self.env._('Agotado')
            elif not plantilla.image_1920:
                motivo = self.env._('Sin foto')
            elif plantilla.id not in publicados:
                motivo = self.env._('No está publicado en la tienda en línea')
            else:
                motivo = self.env._('Sin precio')
            productos.append({
                'id': plantilla.id, 'nombre': plantilla._dcasa_nombre_cliente(),
                'categoria': plantilla.categ_id.name or '', 'existencias': plantilla.dcasa_stock,
                'precio': self.env['dcasa.correo']._monto(precio, moneda) if precio else '', 'mas_itbms': mas_itbms,
                'miniatura': f'/web/image/product.template/{plantilla.id}/image_256', 'elegible': False,
                'motivo': motivo})
        categorias = [{'id': categoria.id, 'nombre': categoria.display_name, 'n': cuantos}
                      for categoria, cuantos in Plantilla._read_group(
                          self._dominio_elegible(website), ['categ_id'], ['__count'], order='__count desc',
                          limit=MAX_CATEGORIAS) if categoria]
        return {'productos': productos, 'categorias': categorias}

    # ------------------------------------------------------------------
    # Probar, enviar, descartar y lo demás
    # ------------------------------------------------------------------

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
        return dict(resultado, panel=self.panel(campana_id))

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
        if not _id_valido(campana_id):
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
