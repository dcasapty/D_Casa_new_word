"""Camila, la asistente del mail marketing: el núcleo (quién puede, qué productos, qué precios, qué texto y el HTML).

Decisiones de la dueña (2026-11-06, docs/CAMILA.md): Camila trabaja por dentro para el equipo de marketing,
**propone y una persona aprueba** (rol «Marketing», Gerencia o administradores); los clientes reciben el correo de
«D'CASA Panamá», nunca de «Camila»; **una campaña cada 15 días como mucho**; **el precio real de Odoo** (el mismo
que ve el cliente en la tienda en línea, el día que se arma o se aprueba), nunca uno escrito por la IA ni a mano.

* **Los productos** (``_elegir``): hay en tienda, tienen foto, están publicados en la web y tienen precio. Las mismas
  cuentas de la app Marketing (lo más vendido y lo quieto de los últimos 30 días) más lo nuevo (lo que llegó de un
  proveedor o se creó en los últimos 30 días), repartidos por turnos; lo de la campaña anterior va al final.
* **El texto** (``_textos``): lo escribe la IA que ya usa Brian (``brian.proveedores``), con las reglas de marca, y
  pasa por una revisión fija (``reglas.problemas``). Lo que no pasa, o si la IA falla, queda con un texto fijo que el
  equipo edita. A la IA solo le llegan nombres y categorías de productos: ningún dato de clientes.
* **El HTML** (``views/correo_templates.xml``): la marca (azul #1340B1, el amarillo solo sobre azul, sin degradados ni
  sombras, fuentes con respaldo para correo), la foto pública de la tienda (``/dcasa/img``), el precio de hoy, un solo
  botón «Escríbenos por WhatsApp» con la marca de la campaña, los datos de la empresa y el enlace de baja de Resend.
"""
import hashlib
import json
import logging
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from babel.dates import format_date

from odoo import Command, api, fields, models
from odoo.addons.dcasa_marketing.models.marketing import GRUPOS
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain

from . import reglas as R
from .campana import ABIERTAS

_logger = logging.getLogger(__name__)

VARIABLE_CLAVE = 'RESEND_CAMPANAS_API_KEY'
ZONA = ZoneInfo('America/Panama')
# Quién ve el dinero de las ventas que trajo una campaña: lo mismo que la ganancia (el rol Marketing no ve dinero).
GRUPOS_DINERO = ('sales_team.group_sale_manager', 'base.group_system')
DIAS_NUEVOS = 30
LIMITE_CANDIDATOS = 200
ANCHO_FOTO = 1024
NOMBRE_GRUPO = dict(R.GRUPOS)
DESCRIPCION_GRUPO_IA = {'nuevo': 'recién llegado', 'vendido': 'de lo más vendido', 'quieto': 'en tienda',
                        'tienda': 'en tienda', 'elegido': 'en tienda'}

SISTEMA_IA = """Escribes el texto de un correo de novedades de D'CASA Panamá, una tienda de muebles en La Chorrera,
para clientes que pidieron recibirlo. La voz: el pana que sabe de casas; cercana, de tú (nunca de usted), español de
Panamá, sencilla y sin exagerar.

Reglas que no se rompen:
- Sin cifras ni números de ningún tipo: ni precios, ni porcentajes, ni medidas, ni fechas. Los precios los pone el
  sistema.
- Sin «remate», sin descuentos, ofertas, rebajas ni «gratis»: esta campaña no trae ninguno.
- Sin «¡¡» ni signos repetidos, sin palabras en mayúsculas, sin emojis.
- No inventes materiales, medidas, colores ni beneficios que no estén en el nombre del producto. Nada de «el mejor»,
  «el más vendido de Panamá» ni testimonios.
- El correo lo firma D'CASA Panamá: no te presentes ni digas que eres una inteligencia artificial.

Devuelve SOLO un objeto JSON, sin texto antes ni después:
{"asunto": "máximo 60 letras", "entrada": "una o dos frases, máximo 220 letras",
 "lineas": {"<id del producto>": "una frase corta por producto, máximo 100 letras"}}"""


def _sha(texto):
    return hashlib.sha256((texto or '').encode('utf-8')).hexdigest()


class DcasaCamila(models.AbstractModel):
    _name = 'dcasa.camila'
    _description = "Camila, la asistente del mail marketing de D'CASA"

    # ------------------------------------------------------------------
    # Quién puede
    # ------------------------------------------------------------------

    @api.model
    def _es_de_marketing(self):
        return self.env.su or any(self.env.user.has_group(grupo) for grupo in GRUPOS)

    @api.model
    def _exigir(self):
        if not self._es_de_marketing():
            raise AccessError(self.env._('Camila es del equipo de marketing: el rol Marketing, Gerencia y los '
                                         'administradores.'))

    @api.model
    def _ve_dinero(self):
        return self.env.su or any(self.env.user.has_group(grupo) for grupo in GRUPOS_DINERO)

    # ------------------------------------------------------------------
    # Configuración y fechas
    # ------------------------------------------------------------------

    @api.model
    def _clave(self):
        """La clave de campañas de Resend (solo del entorno: secreto del panel de Cloudflare). Nunca se guarda."""
        return (os.environ.get(VARIABLE_CLAVE) or '').strip()

    @api.model
    def _entorno(self):
        return self.env['dcasa.correo']._entorno()

    @api.model
    def _ahora_panama(self):
        return fields.Datetime.now().replace(tzinfo=ZoneInfo('UTC')).astimezone(ZONA)

    @api.model
    def _dia_panama(self, momento):
        if not momento:
            return None
        return fields.Datetime.to_datetime(momento).replace(tzinfo=ZoneInfo('UTC')).astimezone(ZONA).date()

    @api.model
    def _fecha_texto(self, dia):
        return format_date(dia, 'd MMM yyyy', locale='es') if dia else ''

    @api.model
    def _hace(self, dia):
        if not dia:
            return ''
        dias = (self._ahora_panama().date() - dia).days
        if dias <= 0:
            return self.env._('hoy')
        if dias == 1:
            return self.env._('ayer')
        return self.env._('hace %s días', dias)

    @api.model
    def _abierta(self):
        return self.env['dcasa.camila.campana'].sudo().search([('estado', 'in', ABIERTAS)], order='id desc', limit=1)

    @api.model
    def _ultima_enviada(self, excepto=None):
        dominio = [('estado', '=', 'enviada')]
        if excepto:
            dominio.append(('id', '!=', excepto.id))
        return self.env['dcasa.camila.campana'].sudo().search(dominio, order='enviada_en desc, id desc', limit=1)

    @api.model
    def _proxima(self, excepto=None):
        """``(última enviada, primer día en que puede salir otra, ¿ya puede salir?)`` en días de Panamá."""
        ultima = self._ultima_enviada(excepto)
        dia = self._dia_panama(ultima.enviada_en) if ultima else None
        proxima = R.proxima_fecha(dia)
        return ultima, proxima, R.puede_salir_hoy(self._ahora_panama().date(), dia)

    @api.model
    def _bloqueos(self, campana=None, con_permiso=None):
        """Por qué no puede salir una campaña ahora mismo, en palabras sencillas (lista vacía si sí puede)."""
        salida = []
        entorno = self._entorno()
        if entorno == 'staging':
            salida.append(self.env._('En staging nunca salen campañas: aquí solo se arma y se manda la prueba.'))
        elif entorno != 'produccion':
            salida.append(self.env._('Este servidor no dice que es producción: de aquí no sale ninguna campaña.'))
        if not self._clave():
            salida.append(self.env._(
                'Todavía no está la clave de campañas de Resend, así que no se puede enviar. Quien administra el '
                'sistema la crea en Resend y la pega como secreto en Cloudflare (docs/CAMILA.md, paso a paso).'))
        ultima, proxima, puede = self._proxima(excepto=campana)
        if not puede:
            salida.append(self.env._(
                'La última campaña salió el %(ultima)s: la próxima puede salir desde el %(proxima)s (una cada '
                '%(dias)s días como mucho).', ultima=self._fecha_texto(self._dia_panama(ultima.enviada_en)),
                proxima=self._fecha_texto(proxima), dias=R.DIAS_ENTRE_CAMPANAS))
        if con_permiso is not None and not con_permiso:
            salida.append(self.env._('Todavía ningún cliente dijo que sí a las novedades: no hay a quién enviarla.'))
        return salida

    # ------------------------------------------------------------------
    # Productos y precios (los de la tienda en línea)
    # ------------------------------------------------------------------

    @api.model
    def _sitio(self):
        Website = self.env['website'].sudo()
        return (Website.search([('company_id', '=', self.env.company.id)], order='sequence, id', limit=1)
                or Website.search([], order='sequence, id', limit=1))

    @api.model
    def _dominio_elegible(self, website):
        """En tienda, con foto y publicado en la web para un visitante anónimo (el mismo dominio de la tienda)."""
        publicado = website.with_user(website.user_id)._dcasa_dominio_publicado()
        return Domain.AND([publicado, [
            ('sale_ok', '=', True), ('active', '=', True), ('type', '!=', 'service'), ('is_storable', '=', True),
            ('dcasa_stock', '>', 0), ('image_1920', '!=', False)]])

    @api.model
    def _tarifa_publica(self, website):
        """La tarifa que ve un visitante anónimo de la tienda (la misma regla de website_sale sin carrito)."""
        Pricelist = self.env['product.pricelist'].sudo()
        if not self.env['res.groups']._is_feature_enabled('product.group_product_pricelist'):
            return Pricelist
        publico = website.user_id.sudo()
        tarifa = publico.partner_id.property_product_pricelist
        disponibles = website.with_user(publico).sudo().get_pricelist_available()
        if disponibles and tarifa not in disponibles:
            tarifa = disponibles[0]
        return tarifa.sudo()

    @api.model
    def _precios(self, plantillas, website):
        """``{id: (precio, mas_itbms)}``: lo que un visitante anónimo ve hoy en la tienda en línea (la tarifa del sitio
        y los impuestos como los muestra la tienda: sin ITBMS y con «+ ITBMS» al lado)."""
        if not plantillas:
            return {}
        website = website.sudo()
        tarifa = self._tarifa_publica(website)
        moneda = tarifa.currency_id or website.currency_id
        reglas = tarifa._compute_price_rule(plantillas.sudo(), 1.0, currency=moneda)
        try:
            posicion = self.env['account.fiscal.position'].sudo()._get_fiscal_position(website.user_id.partner_id)
        except Exception:  # sin posición fiscal: los impuestos del producto tal cual
            posicion = self.env['account.fiscal.position']
        salida = {}
        for plantilla in plantillas.sudo():
            precio = reglas.get(plantilla.id, (plantilla.list_price, False))[0]
            impuestos = plantilla.taxes_id._filter_taxes_by_company(website.company_id)
            mapeados = posicion.map_tax(impuestos) if posicion else impuestos
            precio = plantilla._apply_taxes_to_price(precio, moneda, impuestos, mapeados, plantilla, website=website)
            salida[plantilla.id] = (moneda.round(precio), website._dcasa_mas_itbms(plantilla))
        return salida

    @api.model
    def _imagen(self, website, plantilla):
        """La foto pública del producto que sirve la tienda (``/dcasa/img``, JPEG para que se vea en todo correo)."""
        ruta = website._dcasa_img_url(plantilla, ANCHO_FOTO, 'jpg')
        return f"{self.env['dcasa.correo']._base()}{ruta}" if ruta else ''

    @api.model
    def _elegibles(self, website, ids=None, limite=None):
        """``{id: {plantilla, precio, mas_itbms, imagen}}`` de lo que puede ir en la campaña (con precio > 0)."""
        dominio = self._dominio_elegible(website)
        if ids is not None:
            dominio = Domain.AND([dominio, [('id', 'in', list(ids))]])
        plantillas = self.env['product.template'].sudo().search(dominio, order='website_sequence, id', limit=limite)
        precios = self._precios(plantillas, website)
        salida = {}
        for plantilla in plantillas:
            precio, mas_itbms = precios.get(plantilla.id, (0.0, False))
            imagen = self._imagen(website, plantilla)
            if precio > 0 and imagen:
                salida[plantilla.id] = {'plantilla': plantilla, 'precio': precio, 'mas_itbms': mas_itbms,
                                        'imagen': imagen}
        return salida

    @api.model
    def _nuevos(self, ids):
        """Lo nuevo de los últimos 30 días, de lo más reciente a lo más viejo: lo que llegó de un proveedor (una
        recepción hecha) o el producto que se creó."""
        if not ids:
            return []
        desde = fields.Datetime.now() - timedelta(days=DIAS_NUEVOS)
        ultima = {}
        for producto, fecha in self.env['stock.move'].sudo()._read_group([
                ('state', '=', 'done'), ('date', '>=', desde), ('location_id.usage', '=', 'supplier'),
                ('location_dest_id.usage', '=', 'internal'), ('product_id.product_tmpl_id', 'in', list(ids))],
                ['product_id'], ['date:max']):
            plantilla = producto.product_tmpl_id.id
            ultima[plantilla] = max(fecha, ultima.get(plantilla, fecha))
        for plantilla in self.env['product.template'].sudo().search_fetch(
                [('id', 'in', list(ids)), ('create_date', '>=', desde)], ['create_date']):
            ultima[plantilla.id] = max(plantilla.create_date, ultima.get(plantilla.id, plantilla.create_date))
        return [pid for pid, _fecha in sorted(ultima.items(), key=lambda par: (par[1], par[0]), reverse=True)]

    @api.model
    def _elegir(self, website, excluir=(), cuantos=R.PRODUCTOS_POR_CAMPANA):
        """``[(dato, grupo)]``: lo nuevo, lo más vendido y lo quieto, por turnos; lo de la campaña anterior al final."""
        elegibles = self._elegibles(website)
        if not elegibles:
            return []
        Marketing = self.env['dcasa.marketing'].sudo()
        # Las cuentas de Marketing, solo entre lo que se puede ofrecer (si no, lo quieto de la bodega lo tapa).
        movimiento = Marketing._movimiento(Marketing._rango('mes'), [('id', 'in', list(elegibles))],
                                           limite=LIMITE_CANDIDATOS)
        colas = [
            ('nuevo', self._nuevos(set(elegibles))),
            ('vendido', [fila['id'] for fila in movimiento['mas_vendidos']]),
            ('quieto', [fila['id'] for fila in movimiento['quietos']]),
        ]
        elegidos, vistos = [], set()
        for con_la_anterior in (False, True):
            posiciones = [0] * len(colas)
            while len(elegidos) < cuantos:
                avanzo = False
                for i, (grupo, cola) in enumerate(colas):
                    while posiciones[i] < len(cola):
                        pid = cola[posiciones[i]]
                        posiciones[i] += 1
                        if pid in elegibles and pid not in vistos and (con_la_anterior or pid not in excluir):
                            elegidos.append((elegibles[pid], grupo))
                            vistos.add(pid)
                            avanzo = True
                            break
                    if len(elegidos) >= cuantos:
                        break
                if not avanzo:
                    break
        for con_la_anterior in (False, True):
            for pid, dato in elegibles.items():
                if len(elegidos) >= cuantos:
                    break
                if pid not in vistos and (con_la_anterior or pid not in excluir):
                    elegidos.append((dato, 'tienda'))
                    vistos.add(pid)
        return elegidos

    # ------------------------------------------------------------------
    # El texto (la IA de Brian, con revisión de marca; si falla, el texto fijo)
    # ------------------------------------------------------------------

    @api.model
    def _textos(self, filas):
        """``{asunto, entrada, lineas: {id: texto}, fuente, nota}``. Nunca falla: sin IA queda el texto fijo."""
        fijos = {'asunto': R.ASUNTO_FIJO, 'entrada': R.ENTRADA_FIJA,
                 'lineas': {dato['plantilla'].id: R.linea_fija(grupo) for dato, grupo in filas}}
        datos, nota = {}, ''
        try:
            Uso = self.env['brian.uso'].sudo()
            tope_total, _tope_persona = Uso.topes()
            if tope_total and Uso.gasto_del_mes() >= tope_total:
                raise UserError(self.env._('la IA llegó al tope de gasto del mes (Ajustes › Brian)'))
            proveedor = self.env['brian.proveedores'].sudo().obtener()
            pedido = {'productos': [
                {'id': dato['plantilla'].id, 'nombre': dato['plantilla']._dcasa_nombre_cliente(),
                 'categoria': dato['plantilla'].categ_id.name or '', 'como_va': DESCRIPCION_GRUPO_IA.get(grupo, '')}
                for dato, grupo in filas]}
            mensajes = [{'rol': 'user', 'texto': json.dumps(pedido, ensure_ascii=False)}]
            respuesta = proveedor.chatear(SISTEMA_IA, mensajes, [])
            try:
                Uso.anotar(proveedor, respuesta.get('uso'))
            except Exception:  # el consumo es informativo: nunca tumba la campaña
                _logger.warning('Camila: no se pudo anotar el consumo de la IA', exc_info=True)
            datos = R.leer_json(respuesta.get('texto'))
            if not datos:
                nota = self.env._('La IA no devolvió un texto que se pudiera leer: quedó el texto fijo para que lo '
                                  'edites.')
        except Exception as error:   # la IA nunca tumba el armado: queda el texto fijo
            detalle = getattr(error, 'args', [''])[0] if getattr(error, 'args', None) else type(error).__name__
            _logger.warning('Camila: la IA no respondió (%s); queda el texto fijo', type(error).__name__)
            nota = self.env._('La IA no respondió (%s): quedó el texto fijo para que lo edites.', str(detalle)[:160])
        asunto, ia_asunto = R.elegir_texto(datos.get('asunto'), fijos['asunto'], R.MAX_ASUNTO)
        entrada, ia_entrada = R.elegir_texto(datos.get('entrada'), fijos['entrada'], R.MAX_ENTRADA)
        propuestas = datos.get('lineas') if isinstance(datos.get('lineas'), dict) else {}
        lineas, de_la_ia = {}, [ia_asunto, ia_entrada]
        for pid, fijo in fijos['lineas'].items():
            texto, ia = R.elegir_texto(propuestas.get(str(pid)) or propuestas.get(pid), fijo, R.MAX_LINEA)
            lineas[pid] = texto
            de_la_ia.append(ia)
        if all(de_la_ia):
            fuente = 'ia'
        elif any(de_la_ia):
            fuente = 'mixta'
            nota = nota or self.env._('Parte del texto de la IA no pasó la revisión de marca (cifras, «remate», '
                                      'usted…): ahí quedó el texto fijo.')
        else:
            fuente = 'fija'
            nota = nota or self.env._('El texto de la IA no pasó la revisión de marca: quedó el texto fijo para que '
                                      'lo edites.')
        return {'asunto': asunto, 'entrada': entrada, 'lineas': lineas, 'fuente': fuente, 'nota': nota}

    # ------------------------------------------------------------------
    # Armar, poner al día y dibujar el correo
    # ------------------------------------------------------------------

    @api.model
    def _valores_linea(self, dato, grupo, texto, secuencia):
        plantilla = dato['plantilla']
        moneda = self._sitio().currency_id
        return {
            'secuencia': secuencia, 'producto_id': plantilla.id, 'nombre': plantilla._dcasa_nombre_cliente(),
            'texto': texto, 'grupo': grupo, 'precio': dato['precio'], 'mas_itbms': dato['mas_itbms'],
            'precio_texto': self.env['dcasa.correo']._monto(dato['precio'], moneda), 'imagen': dato['imagen'],
        }

    @api.model
    def _armar(self, campana=None, automatica=False):
        """Arma (o vuelve a armar) el borrador con lo de hoy. Nunca envía."""
        website = self._sitio()
        anterior = self._ultima_enviada()
        filas = self._elegir(website, excluir=set(anterior.linea_ids.producto_id.ids))
        if not filas:
            raise UserError(self.env._(
                'No hay productos para la campaña: hacen falta productos en tienda, con foto, con precio y publicados '
                'en la tienda en línea.'))
        textos = self._textos(filas)
        lineas = [Command.create(self._valores_linea(dato, grupo, textos['lineas'][dato['plantilla'].id], i))
                  for i, (dato, grupo) in enumerate(filas, start=1)]
        hoy = self._ahora_panama().date()
        valores = {
            'name': self.env._('Novedades del %s', self._fecha_texto(hoy)),
            'asunto': textos['asunto'], 'entrada': textos['entrada'], 'fuente': textos['fuente'],
            'nota': textos['nota'] or False, 'precios_del': fields.Datetime.now(), 'automatica': automatica,
            'armada_por': False if automatica else self.env.uid, 'editada_por': False, 'error': False,
        }
        if campana:
            campana.sudo().write(dict(valores, linea_ids=[Command.clear()] + lineas))
        else:
            campana = self.env['dcasa.camila.campana'].sudo().create(dict(valores, linea_ids=lineas))
        self._guardar_html(campana)
        return campana

    @api.model
    def _poner_al_dia(self, campana):
        """Precios, fotos y existencias de ahora: lo que ya no se puede ofrecer sale (agotado, sin foto, sin publicar o
        sin precio). Devuelve los nombres de lo que salió."""
        campana = campana.sudo()
        website = self._sitio()
        elegibles = self._elegibles(website, ids=campana.linea_ids.producto_id.ids)
        quitados, comandos = [], []
        for linea in campana.linea_ids:
            dato = elegibles.get(linea.producto_id.id)
            if not dato:
                quitados.append(linea.nombre or '')
                comandos.append(Command.delete(linea.id))
                continue
            nuevos = self._valores_linea(dato, linea.grupo, linea.texto, linea.secuencia)
            cambios = {k: v for k, v in nuevos.items() if k != 'producto_id' and linea[k] != v}
            if cambios:
                comandos.append(Command.update(linea.id, cambios))
        campana.write({'linea_ids': comandos, 'precios_del': fields.Datetime.now()} if comandos
                      else {'precios_del': fields.Datetime.now()})
        return quitados

    @api.model
    def _valores_correo(self, campana, para_resend=False, prueba=False):
        correo = self.env['dcasa.correo'].sudo()
        enlaces = correo._enlaces()
        return {
            'asunto': R.limpiar(campana.asunto),
            'entrada': R.limpiar(campana.entrada),
            'productos': [{'nombre': R.limpiar(linea.nombre), 'texto': R.limpiar(linea.texto),
                           'precio': linea.precio_texto or '', 'mas_itbms': linea.mas_itbms, 'imagen': linea.imagen}
                          for linea in campana.linea_ids],
            'whatsapp': correo._whatsapp(R.texto_whatsapp(campana.id)),
            'logo': enlaces['logo'],
            'base': enlaces['base'],
            'pie': correo._pie(self.env.company),
            'correo_empresa': correo._config()['responder_a'],
            'baja': '{{{RESEND_UNSUBSCRIBE_URL}}}' if para_resend else '#',
            'fecha_precios': correo._fecha(self._dia_panama(campana.precios_del)),
            'prueba': prueba,
        }

    @api.model
    def _html(self, campana, para_resend=False, prueba=False):
        return str(self.env['ir.qweb'].sudo()._render(
            'dcasa_camila.correo_campana', self._valores_correo(campana, para_resend, prueba), minimal_qcontext=True))

    @api.model
    def _guardar_html(self, campana):
        html = self._html(campana)
        campana.sudo().write({'html': html, 'huella': _sha(html)})
        return html

    @api.model
    def _hoy_inicio_utc(self):
        """El comienzo del día de hoy en Panamá, en UTC sin zona (para buscar en la base)."""
        inicio = datetime.combine(self._ahora_panama().date(), time.min, tzinfo=ZONA)
        return inicio.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
