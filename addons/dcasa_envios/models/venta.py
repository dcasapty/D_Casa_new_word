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
  promoción, no la vendedora: no cuenta contra su tope de descuento mientras sea **coherente** (ver abajo).
* Lo puesto por el sistema queda marcado (``dcasa_envio_lugar_id`` / ``dcasa_promocion_envio_id`` y los términos de la
  promoción): esas marcas **solo las escribe el servidor** (revisión adversarial, segunda vuelta, I-3). Si una persona
  le cambia a una línea del sistema el precio, la cantidad, el producto, los impuestos, la cotización o el lugar, deja
  de ser del sistema en ese mismo cambio (y lo que rebaje pasa a contar contra su tope desde cero). Un envío que puso
  una persona nunca se reemplaza solo: se le deja a ella.

**Con qué fecha y con qué términos** (revisión adversarial, segunda vuelta, I-1 e I-2; lo que decidió la dueña es
respetar lo YA PROMETIDO, no dar promesas nuevas después): la promoción se suma con la promoción vigente HOY (hora de
Panamá). Al sumarla se guardan en su línea los términos con que se sumó y el día (``dcasa_promocion_terminos``: la
promoción, el mínimo y cómo se mide, si es gratis o un abono y de cuánto, la regla del colchón) y hasta cuándo vale lo
prometido: el «Vence el» que tenía la cotización en ese momento, nunca más de 30 días después de sumada (sin «Vence el»,
30 días); cambiar «Vence el» después no lo alarga ni lo revive (tercera vuelta, I-B). Hasta ese día se respeta eso
aunque Gerencia cambie o archive la promoción: solo se mira si la COMPRA sigue cumpliendo esos términos y si el envío
sigue ahí con su precio. Pasado ese día, se vuelve a mirar con la promoción de hoy. Una venta confirmada no vence.

**La promoción se vuelve a revisar** (revisión adversarial, B1): ``_dcasa_promocion_sincronizar`` corre cada vez que
se crean, cambian o quitan líneas (con la medición del tope de descuento, justo antes de medir; si se guarda la venta
entera, UNA vez al final del guardado) y antes de confirmar: si ya no está el envío a domicilio que puso el sistema, o
la compra ya no cumple los términos (bajó del mínimo, lleva colchón, el envío quedó en $0…), la quita y deja una nota
en la cotización con el porqué; si vale, deja su monto y sus impuestos al día con la línea del envío. La línea de la
promoción está exenta del tope **solo** si es coherente con eso (``_dcasa_promocion_coherente``): una venta ya
confirmada no se toca (y un cambio de la promoción no la vuelve incoherente), pero ahí una promoción que dejó de valer
porque cambió la compra cuenta como cualquier rebaja.

**Al duplicar** una cotización (M4) la línea de la promoción no se copia: la copia trae el envío del sistema y la
promoción se vuelve a calcular con la promoción de hoy y la compra de la copia (o queda una nota con el porqué no).
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
                        'order_id', 'dcasa_envio_lugar_id'}
# Las marcas del sistema: solo las escribe el servidor.
MARCAS = ('dcasa_envio_lugar_id', 'dcasa_promocion_envio_id', 'dcasa_promocion_terminos')
SIN_MARCAS = dict.fromkeys(MARCAS, False)
# Lo que cambia si la promoción sigue valiendo y no pasa ya por la medición del tope (``CAMPOS_TOTAL``).
CAMPOS_DE_LA_PROMOCION = {'tax_ids', 'is_delivery', 'display_type', *MARCAS}
SINCRONIZANDO = 'dcasa_envios_sincronizando_promocion'
# Los valores de estas claves son objetos, no «True»: un contexto que llega por RPC es JSON y nunca los puede traer.
MARCA_DEL_SERVIDOR = 'dcasa_envios_marca_del_servidor'
SERVIDOR = object()
SINCRONIZACION = 'dcasa_envios_sincronizacion'
DIFERIDA = object()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    dcasa_envio_lugar_id = fields.Many2one(
        'dcasa.envio.lugar', 'Lugar del envío', readonly=True, index='btree_not_null', ondelete='set null',
        help='El envío lo puso el sistema con el precio de la calculadora para este lugar.')
    dcasa_promocion_envio_id = fields.Many2one(
        'dcasa.envio.promocion', 'Promoción de envío', readonly=True, copy=False, index='btree_not_null',
        ondelete='restrict', help='Lo que la promoción de envío le rebaja al envío. La paga la promoción.')
    dcasa_promocion_terminos = fields.Json(
        'Términos de la promoción', readonly=True, copy=False,
        help='Con qué se sumó la promoción (cuál, el mínimo, si es gratis o un abono y de cuánto, la regla del colchón '
             'y el día): mientras la cotización no venza, se respeta eso aunque la promoción cambie después.')

    @api.model
    def _dcasa_es_el_servidor(self):
        return self.env.su or self.env.context.get(MARCA_DEL_SERVIDOR) is SERVIDOR

    @api.model_create_multi
    def create(self, vals_list):
        if not self._dcasa_es_el_servidor():
            if any(vals.get('dcasa_promocion_envio_id') or vals.get('dcasa_promocion_terminos') for vals in vals_list):
                self._dcasa_exigir_servidor_para_la_promocion()
            # El lugar del envío lo marca solo el servidor: una línea creada a mano es de quien la crea.
            vals_list = [dict(vals, dcasa_envio_lugar_id=False) if vals.get('dcasa_envio_lugar_id') else vals
                         for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        servidor = self._dcasa_es_el_servidor()
        if not servidor and (vals.get('dcasa_promocion_envio_id') or vals.get('dcasa_promocion_terminos')):
            self._dcasa_exigir_servidor_para_la_promocion()
        campos = set(vals)
        del_sistema = self.browse()
        if not servidor and CAMPOS_DE_LA_PERSONA & campos:
            if 'dcasa_envio_lugar_id' in vals:
                vals = dict(vals, dcasa_envio_lugar_id=False)
            del_sistema = self.filtered(lambda linea: linea._dcasa_envio_del_sistema())
        if del_sistema:
            # En el MISMO cambio: el tope mide «antes» con la marca (exenta) y «después» sin ella, así que lo que la
            # línea rebaje ahora cuenta contra el tope de la persona desde cero.
            resultado = super(SaleOrderLine, del_sistema).write(dict(vals, **SIN_MARCAS))
            if self - del_sistema:
                super(SaleOrderLine, self - del_sistema).write(vals)
        else:
            resultado = super().write(vals)
        if CAMPOS_DE_LA_PROMOCION & campos and not CAMPOS_TOTAL & campos and not self._dcasa_sincronizacion_diferida():
            self.order_id._dcasa_promocion_sincronizar()
        return resultado

    @api.model
    def _dcasa_sincronizacion_diferida(self):
        return self.env.context.get(SINCRONIZACION) is DIFERIDA

    @api.model
    def _dcasa_exigir_servidor_para_la_promocion(self):
        """La marca «promoción de envío» (y sus términos) exime a la línea del tope de descuento: solo la pone el
        servidor al sumar el envío. Si alguien pudiera escribirla, bastaría con marcar cualquier rebaja."""
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
    def _dcasa_promocion_cambios(self, envio, resultado, terminos):
        """Lo que le falta a esta línea de promoción para estar al día con el envío ``envio``, el ``resultado`` del
        motor y los ``terminos`` (``{}`` si está al día). El nombre no cuenta: se puede reescribir sin que cambie
        nada."""
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
        if self.dcasa_promocion_terminos != terminos:
            cambios.update(dcasa_promocion_terminos=terminos, dcasa_promocion_envio_id=terminos['promocion_id'])
        if not self.is_delivery:
            cambios['is_delivery'] = True
        return cambios

    def _dcasa_promocion_coherente(self):
        """¿Esta línea es la promoción del envío y sigue valiendo tal cual? Es la única línea de promoción de la
        cotización, con sus términos, está el envío a domicilio que puso el sistema (con su mismo producto), la compra
        de ahora cumple los términos con que se sumó (o, si la cotización venció, la promoción de hoy) y el monto y los
        impuestos son los que tocan. Solo así no cuenta contra el tope de descuento. Mientras se guarda la venta entera,
        la que tiene sus términos se tiene por coherente: la revisión corre una vez al final del guardado."""
        self.ensure_one()
        if not self.dcasa_promocion_envio_id or not self.dcasa_promocion_terminos or self.display_type:
            return False
        orden = self.order_id
        if self._dcasa_sincronizacion_diferida() and orden.state in ESTADOS_EDITABLES:
            return True
        if orden.order_line.filtered('dcasa_promocion_envio_id') != self:
            return False
        envio, resultado, terminos, porque = orden._dcasa_promocion_revisar()
        if porque or self.product_id != envio.product_id:
            return False
        return not self._dcasa_promocion_cambios(envio, resultado, terminos)


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
        lineas_ = self.order_line.filtered(lambda linea: not linea.display_type and not linea.is_downpayment)
        fletes = lineas.productos_de_flete(lineas_.product_id)         # de una vez, no línea por línea (M-2)
        productos = lineas_.filtered(lambda linea: not (
            linea.is_delivery or linea.dcasa_envio_lugar_id or linea.dcasa_promocion_envio_id
            or linea.product_id in fletes))
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
        """¿Al envío a domicilio se le suma ITBMS? Los impuestos del producto del transportista, pasados por la
        posición fiscal de esta venta si es una (revisión adversarial M2), como los pone Odoo en la línea."""
        transportista = self._dcasa_envio_transportista()
        if not transportista:
            return False
        orden = self[:1]
        impuestos = transportista.product_id.taxes_id._filter_taxes_by_company(orden.company_id or self.env.company)
        if orden.fiscal_position_id:
            impuestos = orden.fiscal_position_id.map_tax(impuestos)
        # Un impuesto de 0 % (exento) no le suma nada al envío.
        return bool(impuestos.flatten_taxes_hierarchy().filtered('amount'))

    def _dcasa_promocion_vencida(self, terminos):
        """¿Ya pasó el día hasta el que vale lo prometido con esos ``terminos`` (guardados al sumarse; hora de Panamá)?
        No mira el «Vence el» de hoy: cambiarlo después no alarga ni revive lo prometido. Una venta confirmada no
        vence."""
        self.ensure_one()
        return bool(self.state in ESTADOS_EDITABLES
                    and self.env['dcasa.envio.promocion']._hoy() > motor_promocion.prometido_hasta(terminos))

    def _dcasa_promocion_calcular(self, envio, compra=None):
        """La promoción vigente HOY aplicada a la línea del envío ``envio`` (su precio y el lugar que marcó el sistema)
        con la compra de ahora: ``(resultado, terminos)`` (``terminos``: los que se guardan si se suma, o ``None``)."""
        self.ensure_one()
        lugar = envio.dcasa_envio_lugar_id
        Promocion = self.env['dcasa.envio.promocion']
        hoy = Promocion._hoy()
        resultado, promocion = Promocion._aplicar(
            envio.price_unit, lugar.prov, lugar.dist, compra or self._dcasa_envio_compra(), fecha=hoy)
        if not (resultado['aplica'] and resultado['ahorro'] > 0):
            return resultado, None
        return resultado, motor_promocion.terminos(promocion._como_motor(), resultado, hoy, promocion.id,
                                                   vence=self.validity_date)

    def _dcasa_promocion_revisar(self):
        """¿La promoción del envío vale para esta cotización tal como está ahora? ``(envio, resultado, terminos,
        porque)``: la línea del envío del sistema, lo que dice el motor, los términos que valen (los guardados; si la
        cotización venció o la línea no los tiene, los de la promoción de hoy) y, si no vale, el porqué en palabras
        simples (para la nota de la cotización); ``porque`` es ``None`` si vale."""
        self.ensure_one()
        envios = self.order_line.filtered(lambda linea: linea.dcasa_envio_lugar_id and not linea.display_type)
        envio = envios[:1]
        if len(envios) != 1 or not envio._dcasa_envio_a_domicilio_del_sistema():
            return envio, None, None, self.env._(
                'la cotización ya no tiene el envío a domicilio que sumó el sistema (o se cambió a mano)')
        compra = self._dcasa_envio_compra()
        guardados = self.order_line.filtered('dcasa_promocion_terminos')[:1].dcasa_promocion_terminos
        if guardados and not self._dcasa_promocion_vencida(guardados):
            # Lo prometido: los términos con que se sumó, con la compra y el envío de ahora.
            resultado = motor_promocion.con_lo_prometido(guardados, envio.price_unit, compra)
            if resultado['aplica'] and resultado['ahorro'] > 0:
                return envio, resultado, guardados, None
            return envio, resultado, guardados, self._dcasa_promocion_porque_no(resultado)
        # Vencida (o sin términos): con la promoción de hoy.
        resultado, terminos = self._dcasa_promocion_calcular(envio, compra)
        if terminos:
            return envio, resultado, terminos, None
        porque = self._dcasa_promocion_porque_no(resultado)
        if guardados:
            porque = self.env._('lo prometido valía hasta el %(dia)s y %(porque)s',
                                dia=motor_promocion.prometido_hasta(guardados).strftime('%d/%m/%Y'), porque=porque)
        return envio, resultado, None, porque

    def _dcasa_promocion_si_la_compra_cambia(self, delta):
        """La promoción del envío de esta cotización si la compra subiera o bajara ``delta`` (dinero, no centavos;
        negativo = baja): ``(resultado, ahorro)``. ``resultado`` es ``None`` si la cotización no tiene un envío a
        domicilio del sistema que pueda llevar promoción; ``ahorro`` es lo que D'CASA le regala o le abona del envío
        (``0.0`` si no aplica).

        Mide igual que ``_dcasa_promocion_revisar`` (lo prometido si los términos guardados siguen valiendo, la
        promoción de hoy si no), pero sin tocar nada: sirve para preguntar «¿y si la compra fuera otra?» antes de
        cambiarla. Lo usa Socios para saber qué le costaría al socio un premio de puntos en el envío."""
        self.ensure_one()
        envios = self.order_line.filtered(lambda linea: linea.dcasa_envio_lugar_id and not linea.display_type)
        envio = envios[:1]
        if len(envios) != 1 or not envio._dcasa_envio_a_domicilio_del_sistema():
            return None, 0.0
        moneda = self.currency_id or self.company_id.currency_id
        compra = self._dcasa_envio_compra()
        if delta:
            compra = dict(compra,
                          subtotal_sin_itbms=moneda.round(compra['subtotal_sin_itbms'] + delta),
                          subtotal_con_itbms=moneda.round(compra['subtotal_con_itbms'] + delta))
        guardados = self.order_line.filtered('dcasa_promocion_terminos')[:1].dcasa_promocion_terminos
        if guardados and not self._dcasa_promocion_vencida(guardados):
            resultado = motor_promocion.con_lo_prometido(guardados, envio.price_unit, compra)
        else:
            resultado = self._dcasa_promocion_calcular(envio, compra)[0]
        ahorro = moneda.round(resultado['ahorro']) if resultado.get('aplica') else 0.0
        return resultado, (ahorro if ahorro > 0 else 0.0)

    def _dcasa_promocion_porque_no(self, resultado):
        motivo = resultado['motivo']
        if motivo == motor_promocion.MONTO:
            minimo = self.env._('la compra ya no pasa de %(minimo)s %(mide)s',
                                minimo=dinero(resultado['minimo']), mide=motor_promocion.MIDE[resultado['mide']])
            if resultado['compra_medida']:           # nunca «(ahora suma $0)» ni una cifra negativa
                minimo += self.env._(' (ahora suma %s)', dinero(resultado['compra_medida']))
            return minimo
        if motivo == motor_promocion.COLCHON:
            return self.env._('la compra lleva colchón y la promoción no aplica con colchón')
        if motivo == motor_promocion.SIN_PRECIO:
            return self.env._('el envío quedó sin costo, así que no hay nada que rebajar')
        if motivo == motor_promocion.ZONA_SIN_BENEFICIO:
            return self.env._('ese lugar no está en una zona de la promoción')
        return self.env._('hoy (%s) no hay una promoción de envío vigente',
                          self.env['dcasa.envio.promocion']._hoy().strftime('%d/%m/%Y'))

    def _dcasa_promocion_crear(self, envio, resultado, terminos):
        """Pone la línea de la promoción (con ``sudo``: la pone el servidor) junto a la línea del envío, con los
        términos con que se suma."""
        self.ensure_one()
        return self.env['sale.order.line'].sudo().create({
            'order_id': self.id, 'product_id': envio.product_id.id, 'product_uom_qty': 1,
            'name': self._dcasa_envio_nombre_promocion(resultado, terminos),
            'price_unit': -resultado['ahorro'], 'tax_ids': [fields.Command.set(envio.tax_ids.ids)],
            'is_delivery': True, 'sequence': envio.sequence + 1, 'dcasa_promocion_envio_id': terminos['promocion_id'],
            'dcasa_promocion_terminos': terminos,
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
        """Deja la promoción del envío de cada cotización abierta como corresponde ahora (ver arriba): la quita con una
        nota si ya no vale, quita las repetidas y deja la que vale con su monto y sus impuestos al día (y, si la
        cotización venció, con los términos de la promoción de hoy). Las ventas confirmadas no se tocan."""
        if self.env.context.get(SINCRONIZANDO) or self.env['sale.order.line']._dcasa_sincronizacion_diferida():
            return
        for orden in self.exists():
            promociones = orden.order_line.filtered('dcasa_promocion_envio_id')
            if not promociones or orden.state not in ESTADOS_EDITABLES or orden.locked:
                continue
            envio, resultado, terminos, porque = orden._dcasa_promocion_revisar()
            linea = promociones.filtered('dcasa_promocion_terminos')[:1] or promociones[:1]
            sobran = promociones - linea
            if not porque and linea.product_id != envio.product_id:
                porque = self.env._('la línea de la promoción quedó con otro producto que el envío')
            if porque:
                orden._dcasa_promocion_quitar(promociones, porque)
                continue
            if sobran:
                orden._dcasa_promocion_quitar(sobran, self.env._('estaba repetida'))
            cambios = linea._dcasa_promocion_cambios(envio, resultado, terminos)
            if cambios:
                antes = -linea.price_subtotal
                otra_vez = 'dcasa_promocion_terminos' in cambios
                vencidos = linea.dcasa_promocion_terminos       # los de antes: hasta cuándo valían
                cambios['name'] = orden._dcasa_envio_nombre_promocion(resultado, terminos)
                linea.sudo().with_context(**{SINCRONIZANDO: True}).write(cambios)
                if otra_vez and vencidos:
                    texto = self.env._('Lo prometido valía hasta el %(dia)s: la promoción de envío se volvió a revisar '
                                       'con la de hoy: −%(ahora)s (antes −%(antes)s).',
                                       dia=motor_promocion.prometido_hasta(vencidos).strftime('%d/%m/%Y'),
                                       ahora=dinero(resultado['ahorro']), antes=dinero(antes))
                elif otra_vez:
                    texto = self.env._('La promoción de envío se volvió a revisar con la de hoy: −%(ahora)s (antes '
                                       '−%(antes)s).', ahora=dinero(resultado['ahorro']), antes=dinero(antes))
                else:
                    texto = self.env._('La promoción de envío se puso al día con el envío: −%(ahora)s (antes '
                                       '−%(antes)s).', ahora=dinero(resultado['ahorro']), antes=dinero(antes))
                orden._dcasa_promocion_nota(texto)

    def _dcasa_validar_tope_del_pedido(self, antes=None):
        # dcasa_base lo llama al crear, cambiar o quitar líneas. Antes de medir: los combos al día (dcasa_catalogo lo
        # vuelve a hacer, sin cambios) y la promoción del envío revisada con la compra que queda (si se guarda la venta
        # entera, eso corre una vez al final del guardado: ``write``).
        if not self.env.context.get(SINCRONIZANDO) and not self.env['sale.order.line']._dcasa_sincronizacion_diferida():
            self._dcasa_recalcular_combos()
            self._dcasa_promocion_sincronizar()
        return super()._dcasa_validar_tope_del_pedido(antes)

    def write(self, vals):
        """Al guardar la venta con varias líneas a la vez (la ficha manda los comandos juntos), la promoción se revisa
        UNA vez al final: si se quitara a mitad del guardado, el comando siguiente sobre su línea fallaría (M-1)."""
        if 'order_line' not in vals or self.env['sale.order.line']._dcasa_sincronizacion_diferida() \
                or any(orden.state not in ESTADOS_EDITABLES for orden in self):
            return super().write(vals)
        resultado = super(SaleOrder, self.with_context(**{SINCRONIZACION: DIFERIDA})).write(vals)
        self._dcasa_promocion_sincronizar()
        return resultado

    def action_confirm(self):
        # La revisión quita líneas con sudo: antes, que quien confirma pueda escribir en la venta.
        self.check_access('write')
        self._dcasa_promocion_sincronizar()
        return super().action_confirm()

    def _get_copiable_order_lines(self):
        """Al duplicar no se copia la línea de la promoción: se vuelve a calcular en la copia (``copy``)."""
        return super()._get_copiable_order_lines().filtered(lambda linea: not linea.dcasa_promocion_envio_id)

    def copy(self, default=None):
        # La copia trae el envío del sistema con su marca (la escribe el servidor) y la promoción se vuelve a calcular.
        # Si quien copia manda las líneas (``default`` por RPC), son suyas: sin la marca del servidor, así que las
        # marcas «solo del servidor» no pasan (tercera vuelta, M-a).
        if default and 'order_line' in default:
            return super().copy(default)
        copias = super(SaleOrder, self.with_context(**{MARCA_DEL_SERVIDOR: SERVIDOR})).copy(default)
        copias = copias.with_env(self.env)
        for original, copia in zip(self, copias, strict=True):
            if original.order_line.filtered('dcasa_promocion_envio_id'):
                copia._dcasa_promocion_reponer()
        return copias

    def _dcasa_promocion_reponer(self):
        """En la copia de una cotización que tenía la promoción del envío: se vuelve a calcular con la promoción de hoy
        y la compra de la copia; si no aplica, queda la nota con el porqué."""
        self.ensure_one()
        if self.state not in ESTADOS_EDITABLES or self.order_line.filtered('dcasa_promocion_envio_id'):
            return
        envios = self.order_line.filtered(lambda linea: linea.dcasa_envio_lugar_id and not linea.display_type)
        if len(envios) != 1 or not envios._dcasa_envio_a_domicilio_del_sistema():
            self._dcasa_promocion_nota(self.env._('La promoción de envío de la cotización original no se copió porque '
                                                  'la copia no tiene el envío a domicilio que sumó el sistema.'))
            return
        resultado, terminos = self._dcasa_promocion_calcular(envios)
        if not terminos:
            self._dcasa_promocion_nota(self.env._('La promoción de envío de la cotización original no se copió porque '
                                                  '%s.', self._dcasa_promocion_porque_no(resultado)))
            return
        self._dcasa_promocion_crear(envios, resultado, terminos)
        self._dcasa_promocion_nota(self.env._('La promoción de envío se volvió a calcular para esta cotización: −%s.',
                                              dinero(resultado['ahorro'])))

    # --- Sumar el envío (Juan) -------------------------------------------------------------------------------------
    def _dcasa_envio_poner(self, lugar, precio):
        """Pone (o reemplaza) el envío de esta cotización con el precio normal de la calculadora y, si la promoción
        vigente HOY aplica con su compra, la línea de la promoción (con los términos con que se suma). Si ya tiene ese
        mismo envío con su promoción prometida y vigente, no se toca: lo prometido no se pierde por volver a sumarlo.
        Corre con ``sudo`` (lo llama el servidor).

        Devuelve ``{'puesto': True, 'linea_envio', 'linea_promocion', 'resultado', 'terminos', 'ya_estaba'}``
        (``resultado``: lo que dijo el motor, para la frase al cliente) o ``{'puesto': False, 'motivo'}`` con motivo
        ``confirmada`` (no es borrador ni enviada), ``ajeno`` (ya tiene un envío o un flete que puso una persona) o
        ``sin_transportista``."""
        self.ensure_one()
        if self.state not in ESTADOS_EDITABLES or self.locked:
            return {'puesto': False, 'motivo': 'confirmada'}
        if any(linea._dcasa_envio_ajeno() for linea in self.order_line):
            return {'puesto': False, 'motivo': 'ajeno'}
        transportista = self._dcasa_envio_transportista()
        if not transportista:
            return {'puesto': False, 'motivo': 'sin_transportista'}
        orden = self.sudo()
        promocion_actual = orden.order_line.filtered('dcasa_promocion_envio_id')
        envio_actual = orden.order_line.filtered(lambda linea: linea.dcasa_envio_lugar_id == lugar)
        if promocion_actual and envio_actual and len(promocion_actual) == 1 \
                and promocion_actual._dcasa_promocion_coherente():
            envio, resultado, terminos, _porque = orden._dcasa_promocion_revisar()
            return {'puesto': True, 'ya_estaba': True, 'linea_envio': envio, 'linea_promocion': promocion_actual,
                    'resultado': resultado, 'terminos': terminos}
        # El mismo camino que «Agregar envío»: quita las líneas de envío de antes (las del sistema o la de «Retiro en
        # tienda») y pone la nueva con el método de entrega del pedido.
        orden.set_delivery_line(transportista, precio)
        envio = orden.order_line.filtered('is_delivery')[-1:]
        envio.write({'name': self.env._('Envío a domicilio: %s', motor_tarjeta.lugar_con_zona(lugar._como_motor())),
                     'dcasa_envio_lugar_id': lugar.id})
        resultado, terminos = orden._dcasa_promocion_calcular(envio)
        promocion_linea = orden.env['sale.order.line']
        if terminos:
            promocion_linea = orden._dcasa_promocion_crear(envio, resultado, terminos)
        orden.message_post(body=self._dcasa_envio_nota(lugar, envio.price_unit, resultado),
                           subtype_xmlid='mail.mt_note')
        return {'puesto': True, 'ya_estaba': False, 'linea_envio': envio, 'linea_promocion': promocion_linea,
                'resultado': resultado, 'terminos': terminos}

    def _dcasa_envio_nombre_promocion(self, resultado, terminos):
        """«Promoción Envío Gratis Todo Noviembre: envío gratis» o «Promoción de envío: abono de $20» (en una zona con
        abono no se nombra una promoción que diga «gratis»; si el abono cubre todo el envío: «Promoción de envío: envío
        gratis»)."""
        if resultado['motivo'] == GRATIS:
            nombre = terminos['nombre'] if resultado['zona'] == GRATIS else self.env._('de envío')
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
