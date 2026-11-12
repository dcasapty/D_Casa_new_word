"""El envío dentro de una cotización: la línea del envío y, si aplica, la de la promoción (para Juan y, mañana, otros).

Cómo agregan hoy el envío las vendedoras: el botón «Agregar envío» de la cotización (Odoo, ``delivery``) abre el
asistente de transportistas, eligen «Entrega a domicilio: te cotizamos por WhatsApp» (el transportista que crea
website_dcasa, de precio fijo $0 y marcado «Costo por cotizar») y Odoo pone una línea de envío
(``set_delivery_line``: ``is_delivery``, el producto del transportista con SUS impuestos y el método de entrega del
pedido, que es lo que Bodega mira para saber si es envío o retiro). Aquí se hace lo mismo, por el mismo camino de Odoo,
con el precio de la calculadora:

* **La línea del envío** = ``set_delivery_line(transportista, precio normal)``. El ITBMS es el que tenga configurado el
  producto del transportista (Odoo lo pone, aquí no se elige ningún impuesto).
* **La línea de la promoción** (si aplica): el mismo producto y los mismos impuestos que la línea del envío, en
  negativo, también como línea de envío (así «Actualizar costo de envío» de Odoo quita las dos juntas). La paga la
  promoción, no la vendedora: no cuenta contra su tope de descuento mientras sea **coherente** (ver abajo). Solo el
  servidor (o Gerencia) la marca.
* Lo puesto por el sistema queda marcado (``dcasa_envio_lugar_id`` / ``dcasa_promocion_envio_id``). Si una persona le
  cambia el precio, la cantidad, el producto, los impuestos o la cotización, deja de ser del sistema en ese mismo
  cambio (y lo que rebaje pasa a contar contra su tope desde cero). Un envío que puso una persona nunca se reemplaza
  solo: se le deja a ella.

**La promoción se vuelve a revisar** (revisión adversarial del 2026-11-12, B1): la línea de la promoción se calcula al
sumar el envío, pero la cotización sigue cambiando. ``_dcasa_promocion_sincronizar`` corre cada vez que se crean,
cambian o quitan líneas (con la medición del tope de descuento, justo antes de medir) y antes de confirmar: si ya no
está el envío a domicilio que puso el sistema, o el motor dice que con la compra de ahora ya no aplica (bajó de $200,
lleva colchón, el envío quedó en $0…), la quita y deja una nota en la cotización con el porqué; si aplica, deja su monto
y sus impuestos al día con la línea del envío. La línea de la promoción está exenta del tope **solo** si es coherente
con eso (``_dcasa_promocion_coherente``): una venta ya confirmada no se toca, pero ahí una promoción que dejó de valer
cuenta como cualquier rebaja.

**Con qué fecha** (decisión de la dueña, 2026-11-12): la de creación de la cotización, en hora de Panamá. Una cotización
hecha el 30 de noviembre y confirmada el 2 de diciembre respeta lo prometido en su PDF. Se cambia en
``FECHA_QUE_DECIDE``.

**Al duplicar** una cotización (M4) la línea de la promoción no se copia: la copia trae el envío del sistema y la
promoción se vuelve a calcular con la fecha y la compra de la copia (o queda una nota con el porqué no).
"""
from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.addons.dcasa_base.models.sale_order_line import CAMPOS_TOTAL
from odoo.addons.dcasa_catalogo import reglas as reglas_catalogo
from odoo.addons.dcasa_invoice.models import lineas
from odoo.exceptions import AccessError

from ..motor import promocion as motor_promocion
from ..motor import tarjeta as motor_tarjeta
from ..motor.promocion import GRATIS
from ..motor.texto import dinero

ESTADOS_EDITABLES = ('draft', 'sent')
# Cambiar esto en una línea puesta por el sistema la vuelve de la persona que la cambió (en ese mismo cambio).
CAMPOS_DE_LA_PERSONA = {'price_unit', 'discount', 'product_id', 'product_uom_qty', 'product_uom_id', 'tax_ids',
                        'order_id'}
# Lo que cambia si la promoción sigue valiendo y no pasa ya por la medición del tope (``CAMPOS_TOTAL``).
CAMPOS_DE_LA_PROMOCION = {'tax_ids', 'is_delivery', 'display_type', 'dcasa_envio_lugar_id', 'dcasa_promocion_envio_id'}
# Con qué fecha se decide si la promoción aplica a una cotización: 'creacion' (la de creación de la cotización, en hora
# de Panamá; decisión de la dueña, 2026-11-12) u 'hoy' (el día en que se revisa).
FECHA_QUE_DECIDE = 'creacion'
SINCRONIZANDO = 'dcasa_envios_sincronizando_promocion'


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    dcasa_envio_lugar_id = fields.Many2one(
        'dcasa.envio.lugar', 'Lugar del envío', readonly=True, index='btree_not_null', ondelete='set null',
        help='El envío lo puso el sistema con el precio de la calculadora para este lugar.')
    dcasa_promocion_envio_id = fields.Many2one(
        'dcasa.envio.promocion', 'Promoción de envío', readonly=True, copy=False, index='btree_not_null',
        ondelete='restrict', help='Lo que la promoción de envío le rebaja al envío. La paga la promoción.')

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get('dcasa_promocion_envio_id') for vals in vals_list):
            self._dcasa_exigir_servidor_para_la_promocion()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('dcasa_promocion_envio_id'):
            self._dcasa_exigir_servidor_para_la_promocion()
        campos = set(vals)
        del_sistema = self.browse()
        if not self.env.su and CAMPOS_DE_LA_PERSONA & campos:
            del_sistema = self.filtered(lambda linea: linea._dcasa_envio_del_sistema())
        if del_sistema:
            # En el MISMO cambio: el tope mide «antes» con la marca (exenta) y «después» sin ella, así que lo que la
            # línea rebaje ahora cuenta contra el tope de la persona desde cero.
            resultado = super(SaleOrderLine, del_sistema).write(
                dict(vals, dcasa_envio_lugar_id=False, dcasa_promocion_envio_id=False))
            if self - del_sistema:
                super(SaleOrderLine, self - del_sistema).write(vals)
        else:
            resultado = super().write(vals)
        if CAMPOS_DE_LA_PROMOCION & campos and not CAMPOS_TOTAL & campos:
            self.order_id._dcasa_promocion_sincronizar()
        return resultado

    @api.model
    def _dcasa_exigir_servidor_para_la_promocion(self):
        """La marca «promoción de envío» exime a la línea del tope de descuento: solo la pone el servidor (al sumar el
        envío) o Gerencia. Si la vendedora pudiera escribirla, bastaría con marcar cualquier rebaja."""
        if self.env.su or self.env.user._dcasa_es_gerencia():
            return
        raise AccessError(self.env._('La promoción de envío la pone el sistema al sumar el envío, no se escribe a '
                                     'mano.'))

    def _dcasa_exenta_tope_descuento(self):
        return super()._dcasa_exenta_tope_descuento() or self._dcasa_promocion_coherente()

    def _dcasa_pagada_por_el_programa(self):
        return super()._dcasa_pagada_por_el_programa() or self._dcasa_promocion_coherente()

    def _dcasa_es_envio(self):
        """¿Es una línea de envío o flete (del transportista, el producto de flete, o la promoción del envío)?"""
        self.ensure_one()
        return bool(self.is_delivery or self.dcasa_envio_lugar_id or self.dcasa_promocion_envio_id
                    or lineas.es_flete(self.product_id))

    def _dcasa_envio_del_sistema(self):
        self.ensure_one()
        return bool(self.dcasa_envio_lugar_id or self.dcasa_promocion_envio_id)

    def _dcasa_es_retiro(self):
        """La línea de «Retiro en tienda» que pone «Agregar envío»: de envío (``is_delivery``), en $0 y con un método de
        entrega que no es el de domicilio. (El de retiro y el de domicilio usan el mismo producto, DCASA-ENTREGA.)"""
        self.ensure_one()
        transportista = self.order_id.carrier_id
        return bool(self.is_delivery and not self.price_unit and transportista
                    and not transportista.dcasa_por_cotizar)

    def _dcasa_envio_ajeno(self):
        """¿Es un envío o un flete que puso una persona? Esos no se reemplazan solos. Una línea de «Retiro en tienda» no
        es un envío: si el cliente pide que se lo lleven, se cambia por el envío (como hace «Agregar envío»)."""
        self.ensure_one()
        return bool(not self.display_type and self._dcasa_es_envio() and not self._dcasa_envio_del_sistema()
                    and not self._dcasa_es_retiro())

    def _dcasa_envio_a_domicilio_del_sistema(self):
        """La línea del envío que puso el sistema, tal como la puso: de envío, con el producto del transportista de
        domicilio, una unidad, sin descuento y con un precio mayor que cero."""
        self.ensure_one()
        transportista = self.order_id._dcasa_envio_transportista()
        return bool(self.dcasa_envio_lugar_id and self.is_delivery and not self.display_type and transportista
                    and self.product_id == transportista.product_id and self.product_uom_qty == 1
                    and not self.discount and self.price_unit > 0)

    def _dcasa_lleva_colchon(self):
        """Un colchón (``dcasa_tipo_combo == 'colchon'``) o un combo «… + COLCHÓN» (de los de antes o de Odoo)."""
        self.ensure_one()
        plantilla = self.product_id.product_tmpl_id
        if not plantilla:
            return False
        return bool(plantilla.dcasa_tipo_combo == 'colchon'
                    or reglas_catalogo.clase_de_fila_inventario(plantilla.name) == 'combo')

    # --- La promoción del envío, coherente con la cotización ------------------------------------------------------
    def _dcasa_promocion_cambios(self, envio, resultado, promocion):
        """Lo que le falta a esta línea de promoción para estar al día con el envío ``envio`` y el ``resultado`` del
        motor (``{}`` si está al día). El nombre no cuenta: se puede reescribir sin que cambie nada."""
        self.ensure_one()
        moneda = self.currency_id or self.order_id.company_id.currency_id
        cambios = {}
        if moneda.compare_amounts(self.price_unit, -resultado['ahorro']):
            cambios['price_unit'] = -resultado['ahorro']
        if self.product_uom_qty != 1:
            cambios['product_uom_qty'] = 1
        if self.discount:
            cambios['discount'] = 0.0
        if self.tax_ids != envio.tax_ids:
            cambios['tax_ids'] = [fields.Command.set(envio.tax_ids.ids)]
        if self.dcasa_promocion_envio_id != promocion:
            cambios['dcasa_promocion_envio_id'] = promocion.id
        if not self.is_delivery:
            cambios['is_delivery'] = True
        return cambios

    def _dcasa_promocion_coherente(self):
        """¿Esta línea es la promoción del envío y sigue valiendo tal cual? Es la única línea de promoción de la
        cotización, está el envío a domicilio que puso el sistema (con su mismo producto), el motor dice que aplica con
        la compra de ahora y la fecha de la cotización, y el monto y los impuestos son los que tocan. Solo así no cuenta
        contra el tope de descuento."""
        self.ensure_one()
        if not self.dcasa_promocion_envio_id or self.display_type:
            return False
        orden = self.order_id
        if orden.order_line.filtered('dcasa_promocion_envio_id') != self:
            return False
        envio, resultado, promocion, porque = orden._dcasa_promocion_revisar()
        if porque or self.product_id != envio.product_id:
            return False
        return not self._dcasa_promocion_cambios(envio, resultado, promocion)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _dcasa_envio_lineas(self):
        self.ensure_one()
        return self.order_line.filtered(lambda linea: not linea.display_type and linea._dcasa_es_envio())

    def _dcasa_envio_compra(self):
        """La compra de la cotización SIN el envío: ``{subtotal_sin_itbms, subtotal_con_itbms, colchon}``. Cuentan
        los productos y sus rebajas (las líneas que Odoo suma en el subtotal), no el envío ni la promoción del envío.

        Decisión de la dueña (2026-11-12, M6): los $200 se cuentan DESPUÉS de los descuentos y de los premios de Socios
        (una línea negativa baja la compra medida). Si un día cambia, es aquí: filtrar esas líneas de ``productos``."""
        self.ensure_one()
        productos = self.order_line.filtered(
            lambda linea: not linea.display_type and not linea.is_downpayment and not linea._dcasa_es_envio())
        moneda = self.currency_id or self.company_id.currency_id
        return {
            'subtotal_sin_itbms': moneda.round(sum(productos.mapped('price_subtotal'))),
            'subtotal_con_itbms': moneda.round(sum(productos.mapped('price_total'))),
            'colchon': any(linea._dcasa_lleva_colchon() for linea in productos),
        }

    @api.model
    def _dcasa_envio_transportista(self):
        """El de «Agregar envío» para un envío a domicilio: el transportista activo marcado «Costo por cotizar»
        (website_dcasa: «Entrega a domicilio: te cotizamos por WhatsApp»)."""
        return self.env['delivery.carrier'].sudo().search(
            [('dcasa_por_cotizar', '=', True), ('product_id', '!=', False)], order='sequence, id', limit=1)

    def _dcasa_envio_lleva_itbms(self):
        transportista = self._dcasa_envio_transportista()
        return bool(transportista and transportista.product_id.taxes_id._filter_taxes_by_company(
            self.company_id or self.env.company))

    def _dcasa_promocion_fecha(self):
        """La fecha (de Panamá) con la que se decide si la promoción de envío aplica a esta cotización: la de su
        creación (``FECHA_QUE_DECIDE``). Sin cotización guardada todavía, hoy."""
        Promocion = self.env['dcasa.envio.promocion']
        if FECHA_QUE_DECIDE == 'hoy' or not self.create_date:
            return Promocion._hoy()
        return Promocion._fecha_de_panama(self.create_date)

    def _dcasa_promocion_calcular(self, envio):
        """La promoción vigente en la fecha de la cotización, aplicada a la línea del envío ``envio`` (su precio y el
        lugar que marcó el sistema) con la compra de ahora: ``(resultado, promocion)``."""
        self.ensure_one()
        lugar = envio.dcasa_envio_lugar_id
        return self.env['dcasa.envio.promocion']._aplicar(
            envio.price_unit, lugar.prov, lugar.dist, self._dcasa_envio_compra(), fecha=self._dcasa_promocion_fecha())

    def _dcasa_promocion_revisar(self):
        """¿La promoción del envío vale para esta cotización tal como está ahora? ``(envio, resultado, promocion,
        porque)``: la línea del envío del sistema, lo que dice el motor y, si no vale, el porqué en palabras simples
        (para la nota de la cotización); ``porque`` es ``None`` si vale."""
        self.ensure_one()
        envios = self.order_line.filtered(lambda linea: linea.dcasa_envio_lugar_id and not linea.display_type)
        envio = envios[:1]
        if len(envios) != 1 or not envio._dcasa_envio_a_domicilio_del_sistema():
            return envio, None, self.env['dcasa.envio.promocion'], self.env._(
                'la cotización ya no tiene el envío a domicilio que sumó el sistema (o se cambió a mano)')
        resultado, promocion = self._dcasa_promocion_calcular(envio)
        if resultado['aplica'] and resultado['ahorro'] > 0:
            return envio, resultado, promocion, None
        return envio, resultado, promocion, self._dcasa_promocion_porque_no(resultado)

    def _dcasa_promocion_porque_no(self, resultado):
        motivo = resultado['motivo']
        if motivo == motor_promocion.MONTO:
            return self.env._('la compra ya no pasa de %(minimo)s %(mide)s (ahora suma %(compra)s)',
                              minimo=dinero(resultado['minimo']), mide=motor_promocion.MIDE[resultado['mide']],
                              compra=dinero(resultado['compra_medida']))
        if motivo == motor_promocion.COLCHON:
            return self.env._('la compra lleva colchón y la promoción no aplica con colchón')
        if motivo == motor_promocion.SIN_PRECIO:
            return self.env._('el envío quedó sin costo, así que no hay nada que rebajar')
        if motivo == motor_promocion.ZONA_SIN_BENEFICIO:
            return self.env._('ese lugar no está en una zona de la promoción')
        return self.env._('no hay una promoción de envío vigente en la fecha de la cotización (%s)',
                          self._dcasa_promocion_fecha().strftime('%d/%m/%Y'))

    def _dcasa_promocion_crear(self, envio, resultado, promocion):
        """Pone la línea de la promoción (con ``sudo``: la pone el servidor) junto a la línea del envío."""
        self.ensure_one()
        return self.env['sale.order.line'].sudo().create({
            'order_id': self.id, 'product_id': envio.product_id.id, 'product_uom_qty': 1,
            'name': self._dcasa_envio_nombre_promocion(resultado, promocion),
            'price_unit': -resultado['ahorro'], 'tax_ids': [fields.Command.set(envio.tax_ids.ids)],
            'is_delivery': True, 'sequence': envio.sequence + 1, 'dcasa_promocion_envio_id': promocion.id,
        })

    def _dcasa_promocion_quitar(self, lineas, porque):
        """Quita las líneas de promoción ``lineas`` y deja la nota con el porqué. Odoo borra el método de entrega del
        pedido al quitar una línea de envío: si el envío sigue, se le deja (Bodega lo mira para saber que es envío)."""
        self.ensure_one()
        transportista = self.carrier_id
        monto = -sum(lineas.mapped('price_subtotal'))
        lineas.sudo().with_context(**{SINCRONIZANDO: True}).unlink()
        if transportista and not self.carrier_id and self.order_line.filtered('is_delivery'):
            self.sudo().carrier_id = transportista
        self._dcasa_promocion_nota(self.env._('Se quitó la promoción de envío (−%(monto)s) porque %(porque)s.',
                                              monto=dinero(monto), porque=porque))

    def _dcasa_promocion_nota(self, texto):
        self.sudo().message_post(body=Markup('<p>%s</p>') % escape(texto), subtype_xmlid='mail.mt_note')

    def _dcasa_promocion_sincronizar(self):
        """Deja la promoción del envío de cada cotización abierta como dice el motor ahora (ver arriba): la quita con
        una nota si ya no vale, quita las repetidas y deja la que vale con su monto, sus impuestos y su promoción al
        día. Las ventas confirmadas no se tocan."""
        if self.env.context.get(SINCRONIZANDO):
            return
        for orden in self.exists():
            promociones = orden.order_line.filtered('dcasa_promocion_envio_id')
            if not promociones or orden.state not in ESTADOS_EDITABLES or orden.locked:
                continue
            envio, resultado, promocion, porque = orden._dcasa_promocion_revisar()
            linea, sobran = promociones[:1], promociones[1:]
            if not porque and linea.product_id != envio.product_id:
                porque = self.env._('la línea de la promoción quedó con otro producto que el envío')
            if porque:
                orden._dcasa_promocion_quitar(promociones, porque)
                continue
            if sobran:
                orden._dcasa_promocion_quitar(sobran, self.env._('estaba repetida'))
            cambios = linea._dcasa_promocion_cambios(envio, resultado, promocion)
            if cambios:
                antes = -linea.price_subtotal
                cambios['name'] = orden._dcasa_envio_nombre_promocion(resultado, promocion)
                linea.sudo().with_context(**{SINCRONIZANDO: True}).write(cambios)
                orden._dcasa_promocion_nota(self.env._(
                    'La promoción de envío se puso al día con el envío y la compra: −%(ahora)s (antes −%(antes)s).',
                    ahora=dinero(resultado['ahorro']), antes=dinero(antes)))

    def _dcasa_validar_tope_del_pedido(self, antes=None):
        # dcasa_base lo llama al crear, cambiar o quitar líneas. Antes de medir: los combos al día (dcasa_catalogo lo
        # vuelve a hacer, sin cambios) y la promoción del envío revisada con la compra que queda.
        if not self.env.context.get(SINCRONIZANDO):
            self._dcasa_recalcular_combos()
            self._dcasa_promocion_sincronizar()
        return super()._dcasa_validar_tope_del_pedido(antes)

    def action_confirm(self):
        # La revisión quita líneas con sudo: antes, que quien confirma pueda escribir en la venta.
        self.check_access('write')
        self._dcasa_promocion_sincronizar()
        return super().action_confirm()

    def _get_copiable_order_lines(self):
        """Al duplicar no se copia la línea de la promoción: se vuelve a calcular en la copia (``copy``)."""
        return super()._get_copiable_order_lines().filtered(lambda linea: not linea.dcasa_promocion_envio_id)

    def copy(self, default=None):
        copias = super().copy(default)
        for original, copia in zip(self, copias, strict=True):
            if original.order_line.filtered('dcasa_promocion_envio_id'):
                copia._dcasa_promocion_reponer()
        return copias

    def _dcasa_promocion_reponer(self):
        """En la copia de una cotización que tenía la promoción del envío: se vuelve a calcular con la fecha y la compra
        de la copia; si no aplica, queda la nota con el porqué."""
        self.ensure_one()
        if self.state not in ESTADOS_EDITABLES or self.order_line.filtered('dcasa_promocion_envio_id'):
            return
        envio, resultado, promocion, porque = self._dcasa_promocion_revisar()
        if porque:
            self._dcasa_promocion_nota(self.env._('La promoción de envío de la cotización original no se copió porque '
                                                  '%s.', porque))
            return
        self._dcasa_promocion_crear(envio, resultado, promocion)
        self._dcasa_promocion_nota(self.env._('La promoción de envío se volvió a calcular para esta cotización: −%s.',
                                              dinero(resultado['ahorro'])))

    # --- Sumar el envío (Juan) -------------------------------------------------------------------------------------
    def _dcasa_envio_poner(self, lugar, precio):
        """Pone (o reemplaza) el envío de esta cotización con el precio normal de la calculadora y, si la promoción
        aplica (con la fecha de la cotización y su compra), la línea de la promoción. Corre con ``sudo`` (lo llama el
        servidor).

        Devuelve ``{'puesto': True, 'linea_envio', 'linea_promocion', 'resultado', 'promocion'}`` (``resultado``: lo
        que dijo el motor, para la frase al cliente) o ``{'puesto': False, 'motivo'}`` con motivo ``confirmada`` (no es
        borrador ni enviada), ``ajeno`` (ya tiene un envío o un flete que puso una persona) o ``sin_transportista``."""
        self.ensure_one()
        if self.state not in ESTADOS_EDITABLES or self.locked:
            return {'puesto': False, 'motivo': 'confirmada'}
        if any(linea._dcasa_envio_ajeno() for linea in self.order_line):
            return {'puesto': False, 'motivo': 'ajeno'}
        transportista = self._dcasa_envio_transportista()
        if not transportista:
            return {'puesto': False, 'motivo': 'sin_transportista'}
        orden = self.sudo()
        # El mismo camino que «Agregar envío»: quita las líneas de envío de antes (las del sistema o la de «Retiro en
        # tienda») y pone la nueva con el método de entrega del pedido.
        orden.set_delivery_line(transportista, precio)
        envio = orden.order_line.filtered('is_delivery')[-1:]
        envio.write({'name': self.env._('Envío a domicilio: %s', motor_tarjeta.lugar_con_zona(lugar._como_motor())),
                     'dcasa_envio_lugar_id': lugar.id})
        resultado, promocion = orden._dcasa_promocion_calcular(envio)
        promocion_linea = orden.env['sale.order.line']
        if resultado['aplica'] and resultado['ahorro'] > 0:
            promocion_linea = orden._dcasa_promocion_crear(envio, resultado, promocion)
        orden.message_post(body=self._dcasa_envio_nota(lugar, envio.price_unit, resultado),
                           subtype_xmlid='mail.mt_note')
        return {'puesto': True, 'linea_envio': envio, 'linea_promocion': promocion_linea, 'resultado': resultado,
                'promocion': promocion}

    def _dcasa_envio_nombre_promocion(self, resultado, promocion):
        """«Promoción Envío Gratis Todo Noviembre: envío gratis» o «Promoción de envío: abono de $20» (en una zona con
        abono no se nombra una promoción que diga «gratis»; si el abono cubre todo el envío: «Promoción de envío: envío
        gratis»)."""
        if resultado['motivo'] == GRATIS:
            nombre = promocion.name if resultado['zona'] == GRATIS else self.env._('de envío')
            return self.env._('Promoción %s: envío gratis', nombre)
        return self.env._('Promoción de envío: abono de %s', dinero(resultado['ahorro']))

    def _dcasa_envio_nota(self, lugar, precio, resultado):
        texto = self.env._('Envío a %(lugar)s sumado con el precio de la calculadora (%(precio)s).',
                           lugar=motor_tarjeta.lugar_con_zona(lugar._como_motor()), precio=dinero(precio))
        if resultado.get('aplica'):
            texto += ' ' + self.env._('Promoción de envío: −%s.', dinero(resultado['ahorro']))
        elif resultado.get('frase'):
            texto += ' ' + resultado['frase']
        return Markup('<p>%s</p>') % escape(texto)
