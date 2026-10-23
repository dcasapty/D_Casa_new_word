"""La herramienta ``cotizar`` de Juan: arma la cotización del cliente y deja listo el PDF para mandárselo.

Es la versión sin vendedora de «Cotización» de la pantalla de Conversaciones (``conversacion_panel_catalogo.py``) y
sigue las mismas reglas, más estrictas porque aquí no hay una persona revisando antes:

* Solo productos PUBLICADOS en la tienda, a precio de lista + ITBMS. No hay argumento de precio ni de descuento: lo que
  Odoo calcula (subtotal, ITBMS, total) es lo único que Juan puede decir.
* Nunca confirma una venta, ni reserva existencias, ni cobra. Deja un borrador en Ventas que una vendedora revisa.
* Se enciende y se apaga en Ajustes de Juan (``cotizacion_automatica``). Apagada, Juan avisa que una vendedora se la
  prepara y pasa la conversación; el botón «Cotización» de la pantalla funciona igual con la opción encendida o apagada.
* Con tope: pocas cotizaciones nuevas por conversación y por día (un bucle o un mal uso no llena Ventas de borradores),
  y la misma cotización pedida otra vez se reutiliza en vez de duplicarse.

El PDF viaja como adjunto de un AVISO del hilo («Juan preparó la cotización…»): así las vendedoras lo ven en la
conversación y el Worker lo baja con la URL firmada de vida corta de siempre (``firma.py``). El Worker se la manda al
cliente junto con la respuesta; esta herramienta NO habla con el canal.
"""
import json
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.dcasa_base.models.codigo_publico import normalizar_codigo_publico
from odoo.addons.dcasa_base.nombres import nombre_para_cliente
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta

from . import adjuntos as A
from . import publico as P
from .conversacion_panel_catalogo import INFORME_DE_COTIZACION, MAX_CANTIDAD
from .herramientas_juan import GRUPOS, MAX_VARIANTES, PREFIJO
from .mensaje import CLAVE_SISTEMA

_logger = logging.getLogger(__name__)

MAX_LINEAS_AUTOMATICAS = 10
TOPE_NUEVAS_POR_DIA = 5
VIGENCIA_PARA_REUTILIZAR = timedelta(hours=2)
NOTA_DE_COTIZACION = ('Es una cotización: no es una venta ni reserva nada. Los precios son sin ITBMS y el 7 % se suma '
                      'en el total. La entrega, el flete, el financiamiento, el apartado o un descuento de esta compra '
                      'los confirma una vendedora. El PDF sale junto con tu respuesta: no lo anuncies como enviado, di '
                      'que va adjunto.')
A_VENDEDORA = 'Una vendedora se la prepara: llama a pasar_a_vendedora y dile al cliente lo que esa herramienta indique.'


def _no_creada(motivo, mensaje, **extra):
    """Un «no» de negocio (no un fallo): el modelo recibe el motivo y lo que debe hacer."""
    return {'creada': False, 'motivo': motivo, 'mensaje': mensaje, **extra}


def _no_cotizable_combo(plantilla):
    """Un combo (cama + colchón) lo arma una vendedora: sus piezas se escogen en Ventas, no aquí."""
    nombre = plantilla._dcasa_nombre_cliente()
    return _no_creada(
        'es_combo',
        f'«{nombre}» es un combo y los combos los arma una vendedora. Dile al cliente su precio de la ficha y '
        f'llama a pasar_a_vendedora para que se lo prepare. {A_VENDEDORA}')


def _dinero(valor):
    return P.precio_texto(valor, mas_itbms=False)


class BrianHerramientasJuanCotizacion(models.AbstractModel):
    _inherit = 'brian.herramientas'

    # ------------------------------------------------------------------
    # Entender lo que pidió el modelo
    # ------------------------------------------------------------------

    @api.model
    def _j_cantidad_de_linea(self, valor, codigo):
        if valor is None:
            return 1
        if isinstance(valor, str) and valor.strip().isdigit():
            valor = int(valor.strip())
        if isinstance(valor, float) and valor.is_integer():
            valor = int(valor)
        if isinstance(valor, bool) or not isinstance(valor, int) or not 1 <= valor <= MAX_CANTIDAD:
            raise BrianError(f'La cantidad de «{codigo}» tiene que ser un número entero de 1 a {MAX_CANTIDAD}.')
        return valor

    @api.model
    def _j_variante_para_cotizar(self, codigo, opcion, publicadas):
        """``(variante, None)`` o ``(None, rechazo)``: el producto exacto que se cotiza, o por qué todavía no."""
        codigo = ' '.join(str(codigo or '').split())[:60]
        if not codigo:
            raise BrianError('A cada línea le hace falta el «codigo» del producto (el que devolvió buscar_productos).')
        Variante = self.env['product.product'].sudo()
        # El código que conoce el cliente es el público (DC-K7M4PX), del producto; la medida o el color va en «opcion».
        publico = normalizar_codigo_publico(codigo)
        plantilla = publicadas.filtered(lambda p: p.dcasa_codigo_publico == publico)[:1] if publico \
            else publicadas.browse()
        if not plantilla:
            # Por si trae la referencia del proveedor (de una foto o una conversación vieja).
            # ``ilike`` solo acota; el código se compara exacto (los «%» y «_» que escriba un cliente no son comodines).
            de_codigo = Variante.search([('product_tmpl_id', 'in', publicadas.ids), ('default_code', 'ilike', codigo)])
            exacta = de_codigo.filtered(lambda v: (v.default_code or '').lower() == codigo.lower())[:1]
            if exacta:
                return (None, _no_cotizable_combo(exacta.product_tmpl_id)) if exacta.type == 'combo' \
                    else (exacta, None)
            plantilla = publicadas.filtered(lambda p: (p.default_code or '').lower() == codigo.lower())[:1]
        if not plantilla:
            return None, _no_creada(
                'producto_no_encontrado',
                f'No encuentro el código «{codigo}» entre los productos de la tienda. Búscalo por nombre con '
                'buscar_productos; si no aparece, no lo manejamos: no lo cotices.')
        if plantilla.type == 'combo':
            return None, _no_cotizable_combo(plantilla)
        variantes = plantilla.sudo().product_variant_ids
        opcion = ' '.join(str(opcion or '').split())[:80]
        if len(variantes) > 1 and opcion:
            nombres = {v.id: v.with_context(display_default_code=False).display_name for v in variantes}
            variantes = variantes.filtered(lambda v: P.puntuar(opcion, nombres[v.id], '', ''))
        if len(variantes) == 1:
            return variantes, None
        todas = plantilla.sudo().product_variant_ids[:MAX_VARIANTES]
        nombre = plantilla._dcasa_nombre_cliente()
        return None, _no_creada(
            'elegir_opcion',
            f'«{nombre}» tiene varias opciones. Pregúntale al cliente cuál quiere y vuelve a llamar a cotizar '
            'con el campo «opcion» (por ejemplo el tamaño o el color).',
            opciones=[v._dcasa_nombre_cliente() for v in todas])

    @api.model
    def _j_lineas_para_cotizar(self, lineas):
        """``([(variante, cantidad)], None)`` o ``(None, rechazo)``. Lo mal escrito es ``BrianError``."""
        if isinstance(lineas, str):      # los modelos chicos a veces mandan la lista como texto JSON
            try:
                lineas = json.loads(lineas)
            except ValueError:
                pass
        if not isinstance(lineas, (list, tuple)) or not 0 < len(lineas) <= MAX_LINEAS_AUTOMATICAS:
            raise BrianError(f'«lineas» es una lista de 1 a {MAX_LINEAS_AUTOMATICAS} productos, cada uno con su '
                             '«codigo» y su «cantidad».')
        publicadas = self._j_plantillas_publicadas()
        cantidades = {}
        for linea in lineas:
            if not isinstance(linea, dict):
                raise BrianError('Cada línea lleva el «codigo» del producto y su «cantidad».')
            variante, rechazo = self._j_variante_para_cotizar(linea.get('codigo'), linea.get('opcion'), publicadas)
            if rechazo:
                return None, rechazo
            cantidad = self._j_cantidad_de_linea(linea.get('cantidad'), linea.get('codigo'))
            cantidades[variante] = cantidades.get(variante, 0) + cantidad
        if any(c > MAX_CANTIDAD for c in cantidades.values()):
            raise BrianError(f'Son demasiadas unidades de un mismo producto (máximo {MAX_CANTIDAD}).')
        return list(cantidades.items()), None

    # ------------------------------------------------------------------
    # La cotización en Ventas
    # ------------------------------------------------------------------

    @api.model
    def _j_cotizacion_igual(self, conv, pares):
        """Una cotización que Juan armó hace poco, todavía abierta y con exactamente estas líneas (o vacía)."""
        Orden = self.env['sale.order'].sudo()
        desde = fields.Datetime.now() - VIGENCIA_PARA_REUTILIZAR
        quiero = sorted((v.id, float(c)) for v, c in pares)
        for orden in Orden.search([
                ('partner_id', '=', conv.partner_id.id), ('state', 'in', ('draft', 'sent')),
                ('create_uid', '=', self.env.uid), ('create_date', '>=', desde)], order='id desc', limit=5):
            hay = sorted((linea.product_id.id, float(linea.product_uom_qty))
                         for linea in orden.order_line if not linea.display_type)
            if hay == quiero:
                return orden
        return Orden

    @api.model
    def _j_cotizaciones_nuevas_hoy(self, conv):
        return self.env['sale.order'].sudo().search_count([
            ('partner_id', '=', conv.partner_id.id), ('create_uid', '=', self.env.uid),
            ('create_date', '>=', fields.Datetime.now() - timedelta(days=1))])

    @api.model
    def _j_crear_cotizacion(self, conv, pares):
        origen = self.env._('Conversación %s', conv.name or conv.id_externo)
        orden = self.env['sale.order'].sudo().with_context(mail_create_nosubscribe=True).create({
            'partner_id': conv.partner_id.id,
            # Sin vendedora fija: si alguien ya atiende la conversación, es suya; si no, queda sin asignar
            # (el usuario del asistente no debe figurar como vendedor en los reportes).
            'user_id': conv.asignada_a.id or False,
            'origin': origen,
            'order_line': [(0, 0, {'product_id': v.id, 'product_uom_qty': c}) for v, c in pares]})
        orden.message_post(
            body=self.env._('Cotización armada por Juan (automática) desde la conversación de %s. '
                            'Sin confirmar: una vendedora la revisa.', dict(conv._fields['canal'].selection).get(
                                conv.canal, conv.canal)),
            subtype_xmlid='mail.mt_note')
        # Queda en borrador: pasa a «Enviada» solo cuando el PDF de verdad salió (ver ``_juan_cotizar``).
        return orden

    @api.model
    def _j_cotizacion_como_dict(self, orden):
        lineas = []
        for linea in orden.order_line.filtered(lambda linea: not linea.display_type):
            plantilla = linea.product_id.product_tmpl_id
            mas_itbms = self._j_mas_itbms(plantilla)
            fila = {
                'codigo': plantilla.dcasa_codigo_publico or '',   # el del cliente, no la referencia del proveedor
                'producto': nombre_para_cliente(
                    linea.product_id.with_context(display_default_code=False).display_name or linea.name),
                'cantidad': int(linea.product_uom_qty) if float(linea.product_uom_qty).is_integer()
                else linea.product_uom_qty,
                'precio_unitario_texto': P.precio_texto(linea.price_unit, mas_itbms),
                'subtotal_texto': _dinero(linea.price_subtotal),
                'disponibilidad': self._j_existencias(plantilla, linea.product_id),
            }
            papel = linea._dcasa_combo_en_papel()
            if papel:
                # Combo cama + colchón (dcasa_catalogo): Juan dice lo mismo que el PDF que manda (decisión de la dueña,
                # 2026-10-23): el colchón a su precio normal y el descuento del combo aparte. No calcula nada.
                fila['precio_unitario_texto'] = P.precio_texto(papel['precio'], mas_itbms)
                fila['subtotal_texto'] = _dinero(papel['importe'])
                fila['combo'] = f'Descuento combo cama + colchón: −{_dinero(papel["descuento"])}'
            elif linea.dcasa_combo_con_precio and linea.dcasa_combo_ahorro > 0:
                fila['combo'] = 'Combo cama + colchón'
            lineas.append(fila)
        return {
            'numero': orden.name, 'lineas': lineas,
            'subtotal': round(orden.amount_untaxed, 2), 'subtotal_texto': _dinero(orden.amount_untaxed),
            'itbms': round(orden.amount_tax, 2), 'itbms_texto': _dinero(orden.amount_tax),
            'total': round(orden.amount_total, 2), 'total_texto': _dinero(orden.amount_total),
            'valida_hasta': fields.Date.to_string(orden.validity_date) if orden.validity_date else None,
        }

    @api.model
    def _j_pdf_de_cotizacion(self, orden):
        informe = self.env['ir.actions.report'].sudo().with_context(force_report_rendering=True)
        try:
            pdf, tipo = informe._render_qweb_pdf(INFORME_DE_COTIZACION, [orden.id])
        except Exception:   # noqa: BLE001 — wkhtmltopdf ausente o roto: se avisa a una vendedora, no se cae el chat
            _logger.exception('Juan: no se pudo armar el PDF de la cotización %s', orden.name)
            return None
        return pdf if tipo == 'pdf' and pdf and pdf.startswith(b'%PDF') else None

    @api.model
    def _j_dejar_pdf_en_el_hilo(self, conv, orden, pdf, total_texto):
        """El PDF queda en un aviso del hilo y se devuelve como lo espera el Worker: ``{tipo, url, nombre, mime}``."""
        aviso = conv._aviso(self.env._(
            'Juan armó la cotización %(n)s (total %(total)s) y se la manda al cliente en PDF. Está en Ventas como '
            'borrador, sin confirmar.', n=orden.name, total=total_texto))
        adjunto = self.env['ir.attachment'].sudo().create({
            'name': A.nombre_seguro(f'Cotizacion-{orden.name}.pdf'), 'raw': pdf, 'mimetype': 'application/pdf',
            'res_model': 'dcasa.mensaje', 'res_id': aviso.id, 'public': False})
        aviso.with_context(**{CLAVE_SISTEMA: True}).sudo().write({'adjunto_ids': [(4, adjunto.id)]})
        conv._notificar_panel('mensaje', aviso)
        return aviso._datos_adjuntos_para_worker()[0]

    # ------------------------------------------------------------------
    # La herramienta
    # ------------------------------------------------------------------

    @herramienta(
        nombre=PREFIJO + 'cotizar',
        descripcion='Arma la cotización de ESTA conversación con productos de la tienda y deja listo el PDF, que sale '
                    'junto con tu respuesta. Devuelve subtotal, ITBMS y total (esas cifras sí puedes decirlas). Solo '
                    'precios de lista, sin descuentos. No confirma ninguna venta.',
        parametros={
            'lineas': {
                'type': 'array', 'minItems': 1, 'maxItems': MAX_LINEAS_AUTOMATICAS,
                'description': 'Los productos que pidió el cliente, con el código que devolvieron buscar_productos '
                               'o ver_producto.',
                'items': {
                    'type': 'object', 'additionalProperties': False, 'required': ['codigo'],
                    'properties': {
                        'codigo': {'type': 'string', 'description': 'Código del producto, p. ej. «SOF-001».'},
                        'cantidad': {'type': 'integer', 'description': 'Cuántas unidades. Por defecto 1.'},
                        'opcion': {'type': 'string', 'description': 'Solo si el producto tiene varias opciones: el '
                                                                    'tamaño o el color que eligió el cliente.'},
                    }},
            },
        },
        requeridos=['lineas'], nivel='construccion', categoria='ventas', grupos=GRUPOS,
        ejemplos=['«mándame la cotización del sofá y la cama» → cotizar(lineas=[{codigo: …}, {codigo: …}])'],
    )
    def _juan_cotizar(self, lineas):
        conv = self._j_conversacion()
        if not self.env['dcasa.juan.ajustes'].obtener().cotizacion_automatica:
            return _no_creada('apagada', 'Las cotizaciones las prepara una vendedora. ' + A_VENDEDORA)
        if not conv.partner_id:
            return _no_creada('sin_cliente', 'Todavía no tengo la ficha de este cliente. ' + A_VENDEDORA)
        pares, rechazo = self._j_lineas_para_cotizar(lineas)
        if rechazo:
            return rechazo
        orden = self._j_cotizacion_igual(conv, pares)
        reutilizada = bool(orden)
        if not orden:
            if self._j_cotizaciones_nuevas_hoy(conv) >= TOPE_NUEVAS_POR_DIA:
                return _no_creada('tope_diario', 'Ya armé varias cotizaciones para este cliente hoy. ' + A_VENDEDORA)
            orden = self._j_crear_cotizacion(conv, pares)
        lead = conv._ligar_cotizacion(orden)   # pedir una cotización es interés concreto: oportunidad y temperatura
        datos = self._j_cotizacion_como_dict(orden)
        pdf = self._j_pdf_de_cotizacion(orden)
        if not pdf:
            conv._aviso(self.env._(
                'Juan armó la cotización %s pero no pudo generar el PDF. Ábrela en Ventas y mándala a mano.',
                orden.name))
            return {**_no_creada('sin_pdf', 'Armé la cotización pero no pude generar el PDF. Dile al cliente el '
                                            'total tal cual aparece abajo y que una vendedora le manda el '
                                            'documento. ' + A_VENDEDORA), 'cotizacion': datos}
        documento = self._j_dejar_pdf_en_el_hilo(conv, orden, pdf, datos['total_texto'])
        if orden.state == 'draft':
            orden.sudo().action_quotation_sent()   # recién ahora es cierto que se envió
        if lead:
            lead._dcasa_al_cotizar(orden)   # «Propuesta» y temperatura: solo con una cotización que sí salió
        return {'creada': True, 'reutilizada': reutilizada, 'cotizacion': datos, 'documento': documento,
                'nota': NOTA_DE_COTIZACION}
