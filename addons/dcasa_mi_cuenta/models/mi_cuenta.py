"""Lecturas de «Mi cuenta» (/mi-cuenta): lo que ve el cliente, en diccionarios listos para la plantilla.

Reglas de esta pantalla (no negociables):

* Solo lee. No escribe nada ni toca asientos, impuestos, cuentas ni pagos: los abonos se siguen registrando con
  «Pagar» en la factura, como siempre.
* Las cifras de pago (pagado, saldo, cada abono, desde cuándo y hasta cuándo) salen SOLO de
  ``account.move._dcasa_estado_abono()`` (dcasa_invoice): una sola fuente de cifras para el papel y para la pantalla.
  Si una compra no tiene factura publicada, no se inventa un saldo.
* Todo se busca con ``sudo()`` y SIEMPRE filtrando por la ficha comercial del cliente (``child_of``): quien llama ya
  comprobó la sesión. Un id de otra persona se trata igual que uno que no existe.
* La fecha prometida de Odoo (``scheduled_date``) nunca se enseña como promesa: solo lo que ya pasó.
* Métodos privados (``_mc_…``): nada de esto se puede llamar por RPC.
"""
from datetime import date, datetime, time
from urllib.parse import quote

import pytz

from odoo import models
from odoo.addons.dcasa_base.nombres import nombre_para_cliente
from odoo.addons.dcasa_invoice.models import lineas as L
from odoo.addons.dcasa_socios.models import reglas as R
from odoo.addons.dcasa_socios.models.dcasa_canje import ESTADOS_CANJE

TZ = pytz.timezone('America/Panama')
MESES = ('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic')
MESES_LARGOS = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
                'noviembre', 'diciembre')

# Lo que el cliente ve de sus pedidos. Nunca 'draft': los carritos de la web y los borradores son del equipo.
ESTADOS_VISIBLES = ('sent', 'sale', 'cancel')
LIMITE = 200

GRUPOS = (
    ('por_pagar', 'Por pagar'),
    ('por_entregar', 'Por entregar o retirar'),
    ('ya', 'Ya las tienes'),
    ('canceladas', 'Canceladas'),
)
CANCELADAS_A_LA_VISTA = 5

TEXTO_SIN_FACTURA = 'Tu factura y tus pagos aparecen aquí cuando se emita.'
TEXTO_COMO = 'Retiro en la tienda o entrega a domicilio: lo coordinamos por WhatsApp.'
# El mueble se entrega pagado completo (decisión de la dueña, 2026-10-17): con saldo, nunca «Listo».
TEXTO_AL_TERMINAR = 'Cuando termines de pagar, te escribimos para coordinar la entrega o el retiro.'


# ---------------------------------------------------------------------------
# Formatos (16 oct 2026, $1,070.50)
# ---------------------------------------------------------------------------

def _a_fecha(valor):
    """date de Panamá a partir de date, datetime de Odoo (UTC sin zona) o «dd/mm/aaaa» (_dcasa_abonos)."""
    if not valor:
        return None
    if isinstance(valor, str):
        try:
            return datetime.strptime(valor, '%d/%m/%Y').date()
        except ValueError:
            return None
    if isinstance(valor, datetime):
        aware = valor if valor.tzinfo else pytz.utc.localize(valor)
        return aware.astimezone(TZ).date()
    return valor


def fecha_corta(valor):
    """«16 oct 2026»."""
    dia = _a_fecha(valor)
    return f'{dia.day} {MESES[dia.month - 1]} {dia.year}' if dia else ''


def dia_mes(valor):
    """«16 oct»."""
    dia = _a_fecha(valor)
    return f'{dia.day} {MESES[dia.month - 1]}' if dia else ''


def fecha_hora(valor):
    """«19 oct 2026, 6:29 p. m.» (hora de Panamá)."""
    if not valor:
        return ''
    aware = valor if valor.tzinfo else pytz.utc.localize(valor)
    local = aware.astimezone(TZ)
    hora = local.hour % 12 or 12
    sufijo = 'a. m.' if local.hour < 12 else 'p. m.'
    return f'{fecha_corta(local.date())}, {hora}:{local.minute:02d} {sufijo}'


def monto(valor):
    """«$1,070.50» (y «-$5.00»)."""
    valor = round(float(valor or 0.0), 2)
    signo = '-' if valor < 0 else ''
    return f'{signo}${abs(valor):,.2f}'


def cantidad(valor):
    """«2» en vez de «2.0»; «1.5» si de verdad es fracción."""
    valor = float(valor or 0.0)
    return f'{valor:g}' if valor != int(valor) else str(int(valor))


def hoy_en_panama():
    return datetime.now(TZ).date()


def _orden(valor):
    """Clave de orden común a pedidos (datetime) y facturas (date)."""
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime.combine(valor, time.min)
    return datetime.min


def cosas_mas(n):
    if n <= 0:
        return ''
    return 'y 1 cosa más' if n == 1 else f'y {n} cosas más'


def correo_tapado(correo):
    """«lu•••@gmail.com»: quien entra con PIN reconoce su correo sin que se lea entero."""
    if not correo or '@' not in correo:
        return correo or ''
    usuario, _arroba, dominio = correo.partition('@')
    return f'{usuario[:2]}•••@{dominio}'


def cumple_texto(valor):
    """'02-14' → «14 de febrero»."""
    try:
        mes, dia = (int(parte) for parte in (valor or '').split('-'))
        return f'{dia} de {MESES_LARGOS[mes - 1]}'
    except (ValueError, IndexError):
        return ''


class DcasaMiCuenta(models.AbstractModel):
    _name = 'dcasa.mi.cuenta'
    _description = 'Mi cuenta del cliente (solo lecturas para el sitio)'

    # ------------------------------------------------------------------------
    # Qué es de quién (siempre por la ficha comercial)
    # ------------------------------------------------------------------------

    @staticmethod
    def _mc_dominio(ficha):
        return [('partner_id', 'child_of', ficha.commercial_partner_id.id)]

    @staticmethod
    def _mc_cancelada_visible(pedido):
        """Una cancelación que el cliente conoce: fue apartado, se confirmó (tuvo entrega) o tuvo factura. Una
        cotización que el equipo descartó por dentro no le dice nada."""
        return bool(pedido.dcasa_apartado_vence or pedido.picking_ids or pedido.invoice_ids)

    def _mc_pedidos(self, ficha):
        Pedido = self.env['sale.order'].sudo()
        if not ficha:
            return Pedido
        pedidos = Pedido.search(self._mc_dominio(ficha) + [('state', 'in', ESTADOS_VISIBLES)],
                                order='date_order desc, id desc', limit=LIMITE)
        return pedidos.filtered(lambda p: p.state != 'cancel' or self._mc_cancelada_visible(p))

    @staticmethod
    def _mc_es_suelta(factura):
        """Factura que no viene de ningún pedido (se hizo directo en Facturación)."""
        return not factura.invoice_line_ids.sale_line_ids

    def _mc_facturas_sueltas(self, ficha):
        Factura = self.env['account.move'].sudo()
        if not ficha:
            return Factura
        facturas = Factura.search(
            self._mc_dominio(ficha) + [('move_type', '=', 'out_invoice'), ('state', '=', 'posted')],
            order='invoice_date desc, id desc', limit=LIMITE)
        return facturas.filtered(self._mc_es_suelta)

    @staticmethod
    def _mc_id_valido(valor):
        return isinstance(valor, int) and 0 < valor < 2**31

    def _mc_pedido(self, ficha, pedido_id):
        """El pedido si es de esta ficha y se le enseña; si no, vacío (la ruta responde 404)."""
        Pedido = self.env['sale.order'].sudo()
        if not ficha or not self._mc_id_valido(pedido_id):
            return Pedido
        pedido = Pedido.search(self._mc_dominio(ficha) + [('id', '=', pedido_id), ('state', 'in', ESTADOS_VISIBLES)],
                               limit=1)
        if pedido.state == 'cancel' and not self._mc_cancelada_visible(pedido):
            return Pedido
        return pedido

    def _mc_factura(self, ficha, factura_id):
        """La factura de cliente publicada si es de esta ficha; si no, vacío."""
        Factura = self.env['account.move'].sudo()
        if not ficha or not self._mc_id_valido(factura_id):
            return Factura
        return Factura.search(self._mc_dominio(ficha) + [
            ('id', '=', factura_id), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted')], limit=1)

    # ------------------------------------------------------------------------
    # Las cosas que compró
    # ------------------------------------------------------------------------

    @staticmethod
    def _mc_nombre(producto, texto=''):
        """El nombre en formato título, como lo lee el cliente (F5: por dentro va en MAYÚSCULAS)."""
        if producto:
            return nombre_para_cliente(producto.with_context(display_default_code=False).display_name)
        return nombre_para_cliente((texto or '').split('\n')[0].strip())

    def _mc_items_pedido(self, pedido):
        """Las líneas que ve el cliente: sin secciones, notas ni anticipos; las piezas de un combo van dentro."""
        items = []
        lineas = pedido.order_line.filtered(
            lambda li: not li.display_type and li.product_id and not li.is_downpayment and not li.combo_item_id)
        for linea in lineas:
            producto = linea.product_id
            piezas = linea.linked_line_ids.filtered('combo_item_id')
            importe = linea.price_total + sum(piezas.mapped('price_total'))
            flete = bool(linea.is_delivery) or L.es_flete(producto)
            items.append({
                'producto': producto,
                'nombre': self._mc_nombre(producto, linea.name),
                'cantidad': cantidad(linea.product_uom_qty),
                'importe': importe,
                'importe_fmt': monto(importe),
                'flete': flete,
                'por_cotizar': flete and not importe,
                'mueble': producto.type != 'service' and not flete and not linea.dcasa_canje_id,
                'piezas': [self._mc_nombre(pieza.product_id, pieza.name) for pieza in piezas],
            })
        return items

    def _mc_items_factura(self, factura):
        items = []
        for linea in factura.invoice_line_ids.filtered(lambda li: li.display_type == 'product'):
            producto = linea.product_id
            flete = L.es_flete(producto)
            items.append({
                'producto': producto,
                'nombre': self._mc_nombre(producto, linea.name),
                'cantidad': cantidad(linea.quantity),
                'importe': linea.price_total,
                'importe_fmt': monto(linea.price_total),
                'flete': flete,
                'por_cotizar': flete and not linea.price_total,
                'mueble': bool(producto) and producto.type != 'service' and not flete,
                'piezas': [],
            })
        return items

    def _mc_foto(self, website, producto):
        """La foto del mueble (256 px) si está publicado en la tienda; si no, False (la plantilla pone un icono)."""
        if not website or not producto:
            return False
        plantilla = producto.product_tmpl_id.sudo()
        if not plantilla.filtered_domain(website._dcasa_dominio_publicado()):
            return False
        return website._dcasa_img_url(producto, 256) or False

    def _mc_principal(self, items, website):
        """(nombre, foto, cuántas cosas más): el mueble de mayor importe y el resto."""
        muebles = [item for item in items if item['mueble']] or [item for item in items if not item['flete']]
        if not muebles:
            return '', False, 0
        principal = max(muebles, key=lambda item: item['importe'])
        return principal['nombre'], self._mc_foto(website, principal['producto']), len(muebles) - 1

    # ------------------------------------------------------------------------
    # Pagos: solo lo que dice _dcasa_estado_abono() de cada factura publicada
    # ------------------------------------------------------------------------

    def _mc_pago(self, facturas):
        """Lo pagado y lo que falta de las facturas publicadas de una compra, o None si no hay ninguna."""
        facturas = facturas.filtered(lambda f: f.move_type == 'out_invoice' and f.state == 'posted')
        if not facturas:
            return None
        moneda = facturas[0].currency_id
        estados = [(factura, factura.with_context(tz=TZ.zone)._dcasa_estado_abono())
                   for factura in facturas.sorted(lambda f: (f.invoice_date or date.min, f.id))]
        total = moneda.round(sum(estado['total'] for _f, estado in estados))
        pagado = moneda.round(sum(estado['pagado'] for _f, estado in estados))
        saldo = moneda.round(sum(estado['saldo'] for _f, estado in estados))
        abonos = []
        for factura, estado in estados:
            for abono in estado['abonos']:
                abonos.append({
                    'fecha': fecha_corta(abono['fecha']),
                    'orden': _a_fecha(abono['fecha']) or date.min,
                    'medio': 'Nota de crédito' if abono['es_reverso'] else (abono['medio'] or 'Pago'),
                    'monto': monto(abono['monto']),
                    'es_reverso': abono['es_reverso'],
                    'factura': factura.name,
                })
        abonos.sort(key=lambda abono: abono['orden'])
        vences = [estado['vence'] for _f, estado in estados if estado['vence']]
        inicios = [estado['inicio'] for _f, estado in estados if estado['inicio']]
        vence = min(vences) if vences else False
        porcentaje = 100 if total <= 0 else max(0, min(100, int(pagado * 100 // total)))
        return {
            'total': total, 'pagado': pagado, 'saldo': saldo,
            'total_fmt': monto(total), 'pagado_fmt': monto(pagado), 'saldo_fmt': monto(saldo),
            'por_pagar': saldo > 0,
            'es_abono': any(estado['es_abono'] for _f, estado in estados),
            'abonos': abonos,
            'inicio': fecha_corta(min(inicios)) if inicios else '',
            'vence': fecha_corta(vence),
            'vence_orden': vence or date.max,
            'vencido': any(estado['vencido'] for _f, estado in estados),
            'porcentaje': porcentaje,
            'facturas': facturas.mapped('name'),
        }

    def _mc_puntos_de(self, ficha, facturas):
        """Puntos que sumaron estas facturas (compras activas del libro), o 0."""
        if not facturas:
            return 0
        compras = self.env['dcasa.compra'].sudo().search([
            ('partner_id', '=', ficha.commercial_partner_id.id), ('move_id', 'in', facturas.ids),
            ('anulada_en', '=', False)])
        return sum(compras.mapped('puntos'))

    # ------------------------------------------------------------------------
    # Entrega: solo hechos, nunca la fecha prevista de Odoo como promesa
    # ------------------------------------------------------------------------

    @staticmethod
    def _mc_entrega(pedido, por_pagar=False):
        """``por_pagar``: la compra todavía tiene saldo. El mueble no se entrega hasta pagarlo completo, así que aunque
        ya esté apartado en la bodega no se anuncia como listo."""
        transportista = pedido.carrier_id.name if pedido.carrier_id else ''
        salidas = pedido.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing' and p.state != 'cancel')
        entrega = {'estado': None, 'texto': '', 'como': transportista or TEXTO_COMO, 'transportista': transportista}
        if pedido.state != 'sale' or not salidas:
            return entrega
        if all(p.state == 'done' for p in salidas):
            fechas = [p.date_done for p in salidas if p.date_done]
            entrega.update(estado='entregado', fecha=fecha_corta(max(fechas)) if fechas else '',
                           texto=f'Entregado el {fecha_corta(max(fechas))}' if fechas else 'Entregado')
        elif por_pagar:
            entrega.update(estado='al_pagar', texto=TEXTO_AL_TERMINAR)
        elif any(p.state == 'assigned' for p in salidas):
            entrega.update(estado='listo', texto='Listo: te escribimos para coordinar la entrega o el retiro.')
        else:
            entrega.update(estado='preparando', texto='Lo estamos preparando.')
        return entrega

    @staticmethod
    def _mc_pasos(pago, entrega):
        """Compra hecha · Pagada (o «Pagando: te falta $X») · Lista · Entregada. Cada paso: hecho, actual o
        pendiente."""
        pagando = bool(pago and pago['por_pagar'])
        pasos = [
            {'nombre': 'Compra hecha', 'estado': 'hecho'},
            {'nombre': f"Pagando: te falta {pago['saldo_fmt']}" if pagando else 'Pagada',
             'estado': 'hecho' if pago and not pagando else ('actual' if pagando else 'pendiente')},
        ]
        if entrega and entrega['estado']:
            listo = entrega['estado'] in ('listo', 'entregado')
            entregado = entrega['estado'] == 'entregado'
            pasos += [
                {'nombre': 'Lista', 'estado': 'hecho' if listo else 'pendiente'},
                {'nombre': f"Entregada el {entrega['fecha']}" if entregado and entrega.get('fecha') else 'Entregada',
                 'estado': 'hecho' if entregado else 'pendiente'},
            ]
        if not any(paso['estado'] == 'actual' for paso in pasos):
            siguiente = next((paso for paso in pasos if paso['estado'] == 'pendiente'), None)
            if siguiente:
                siguiente['estado'] = 'actual'
        return pasos

    # ------------------------------------------------------------------------
    # Resumen de una compra (tarjeta de la lista y detalle)
    # ------------------------------------------------------------------------

    def _mc_whatsapp(self, website, texto):
        return website._dcasa_whatsapp_url(texto) if website else '/whatsapp'

    def _mc_resumen_pedido(self, pedido, website, tienda=False):
        """Todo lo que la pantalla dice de un pedido. ``tienda``: entró con la cuenta de la tienda (puede bajar PDF)."""
        hoy = hoy_en_panama()
        items = self._mc_items_pedido(pedido)
        mueble, foto, mas = self._mc_principal(items, website)
        facturas = pedido.invoice_ids.filtered(lambda f: f.move_type == 'out_invoice' and f.state == 'posted')
        pago = self._mc_pago(facturas)
        entrega = self._mc_entrega(pedido, por_pagar=bool(pago and pago['por_pagar']))
        apartado = pedido.dcasa_apartado_vence if pedido.state in ('sent', 'sale') and not facturas else False
        mensaje = ''
        tono = 'neutro'
        if pedido.state == 'cancel':
            grupo, etiqueta, tono = 'canceladas', 'Cancelada', 'cancelada'
            vence = pedido.dcasa_apartado_vence
            mensaje = (f'Se anuló porque venció el apartado el {dia_mes(vence)}.' if vence and vence < hoy
                       else 'Esta compra se canceló.')
        elif apartado:
            tipo = 'Apartado por página web' if pedido.website_id else 'Apartado'
            grupo, etiqueta, tono = 'por_pagar', f'{tipo} hasta el {dia_mes(apartado)}', 'alerta'
            mensaje = (f'{tipo} hasta el {dia_mes(apartado)}: pasa a pagarlo antes de esa fecha.' if apartado >= hoy
                       else f'Tu apartado venció el {dia_mes(apartado)}. Escríbenos por WhatsApp.')
        elif pedido.state == 'sent':
            grupo, etiqueta = 'por_pagar', 'Cotización'
            mensaje = 'Es una cotización: todavía no es una compra. Para confirmarla, escríbenos por WhatsApp.'
        elif pago and pago['por_pagar']:
            grupo, etiqueta, tono = 'por_pagar', f"Te falta {pago['saldo_fmt']}", 'alerta'
        elif entrega['estado'] == 'entregado':
            grupo, etiqueta, tono = 'ya', entrega['texto'], 'ok'
        elif entrega['estado'] == 'listo':
            grupo, etiqueta, tono = 'por_entregar', 'Lista para entregar o retirar', 'ok'
        elif entrega['estado'] == 'preparando':
            grupo, etiqueta = 'por_entregar', 'La estamos preparando'
        elif pago:
            grupo, etiqueta, tono = 'ya', 'Pagada', 'ok'
        else:
            grupo, etiqueta = 'por_entregar', 'Confirmada'
        pasos = self._mc_pasos(pago, entrega) if pedido.state == 'sale' else []
        facturado = pago['total'] if pago else 0.0
        resumen = {
            'tipo': 'pedido',
            'id': pedido.id,
            'nombre': pedido.name,
            'url': f'/mi-cuenta/compras/{pedido.id}',
            'fecha': fecha_corta(pedido.date_order),
            'orden': _orden(pedido.date_order),
            'estado': pedido.state,
            'mueble': mueble or 'Tu compra',
            'foto': foto,
            'mas': cosas_mas(mas),
            'items': items,
            'total_fmt': monto(pedido.amount_total),
            'subtotal_fmt': monto(pedido.amount_untaxed),
            'itbms_fmt': monto(pedido.amount_tax),
            'pago': pago,
            'sin_factura': pedido.state == 'sale' and not pago,
            'texto_sin_factura': TEXTO_SIN_FACTURA,
            'parcial': bool(pago) and pedido.state == 'sale'
                       and pedido.currency_id.compare_amounts(pedido.amount_total, facturado) > 0,
            'entrega': entrega,
            'pasos': pasos,
            'grupo': grupo,
            'etiqueta': etiqueta,
            'tono': tono,
            'mensaje': mensaje,
            'apartado': apartado,
            'puntos': R.como_puntos(self._mc_puntos_de(pedido.partner_id, facturas)),
            'whatsapp': self._mc_whatsapp(website, f"Hola D'CASA, tengo una pregunta sobre mi compra {pedido.name}"),
            'whatsapp_factura': self._mc_whatsapp(
                website, f"Hola D'CASA, necesito la factura de mi compra {pedido.name}"),
            'pdf': '',
            'pdf_facturas': [],
        }
        if tienda:
            self._mc_pdf_tienda(resumen, pedido, facturas)
        return resumen

    @staticmethod
    def _mc_pdf_tienda(resumen, pedido, facturas):
        """Enlaces al PDF de Odoo del portal (el usuario de la tienda ya tiene acceso por las reglas del portal). Nunca
        se crean access_token: solo rutas /my que exigen su sesión."""
        if pedido.state in ('sent', 'sale'):
            resumen['pdf'] = f'/my/orders/{pedido.id}?report_type=pdf&download=true'
        comercial = pedido.partner_id.commercial_partner_id
        resumen['pdf_facturas'] = [
            {'nombre': factura.name, 'url': f'/my/invoices/{factura.id}?report_type=pdf&download=true'}
            for factura in facturas if factura.partner_id.commercial_partner_id == comercial]

    def _mc_resumen_factura(self, factura, website, tienda=False):
        """Una factura publicada que no viene de ningún pedido (se hizo directo en Facturación)."""
        items = self._mc_items_factura(factura)
        mueble, foto, mas = self._mc_principal(items, website)
        pago = self._mc_pago(factura)
        if pago and pago['por_pagar']:
            grupo, etiqueta, tono = 'por_pagar', f"Te falta {pago['saldo_fmt']}", 'alerta'
        else:
            grupo, etiqueta, tono = 'ya', 'Pagada', 'ok'
        return {
            'tipo': 'factura',
            'id': factura.id,
            'nombre': factura.name,
            'url': f'/mi-cuenta/facturas/{factura.id}',
            'fecha': fecha_corta(factura.invoice_date),
            'orden': _orden(factura.invoice_date),
            'estado': 'sale',
            'mueble': mueble or 'Tu compra',
            'foto': foto,
            'mas': cosas_mas(mas),
            'items': items,
            'total_fmt': monto(factura.amount_total),
            'subtotal_fmt': monto(factura.amount_untaxed),
            'itbms_fmt': monto(factura.amount_tax),
            'pago': pago,
            'sin_factura': False,
            'texto_sin_factura': TEXTO_SIN_FACTURA,
            'parcial': False,
            'entrega': None,
            'pasos': self._mc_pasos(pago, None),
            'grupo': grupo,
            'etiqueta': etiqueta,
            'tono': tono,
            'mensaje': '',
            'apartado': False,
            'puntos': R.como_puntos(self._mc_puntos_de(factura.partner_id, factura)),
            'whatsapp': self._mc_whatsapp(website, f"Hola D'CASA, tengo una pregunta sobre mi factura {factura.name}"),
            'whatsapp_factura': self._mc_whatsapp(website, f"Hola D'CASA, necesito mi factura {factura.name}"),
            'pdf': '',
            'pdf_facturas': [{'nombre': factura.name,
                              'url': f'/my/invoices/{factura.id}?report_type=pdf&download=true'}] if tienda else [],
        }

    # ------------------------------------------------------------------------
    # Pantallas
    # ------------------------------------------------------------------------

    def _mc_compras(self, ficha, website, tienda=False):
        """{'compras': todas, de la más nueva a la más vieja; 'grupos': [{'clave', 'titulo', 'compras', 'ocultas'}]}.

        Cada compra es un pedido (no borrador) o una factura suelta; las canceladas van al final y solo unas pocas.
        """
        compras = [self._mc_resumen_pedido(pedido, website, tienda) for pedido in self._mc_pedidos(ficha)]
        compras += [self._mc_resumen_factura(factura, website, tienda) for factura in self._mc_facturas_sueltas(ficha)]
        compras.sort(key=lambda compra: (compra['orden'], compra['id']), reverse=True)
        grupos = []
        for clave, titulo in GRUPOS:
            del_grupo = [compra for compra in compras if compra['grupo'] == clave]
            ocultas = 0
            if clave == 'canceladas' and len(del_grupo) > CANCELADAS_A_LA_VISTA:
                ocultas = len(del_grupo) - CANCELADAS_A_LA_VISTA
                del_grupo = del_grupo[:CANCELADAS_A_LA_VISTA]
            if del_grupo:
                grupos.append({'clave': clave, 'titulo': titulo, 'compras': del_grupo, 'ocultas': ocultas})
        return {'compras': compras, 'grupos': grupos}

    def _mc_pendiente(self, compras, puntos):
        """Lo primero que ve en el Inicio: la compra con saldo (la que vence antes), un apartado, una entrega lista o
        los premios por recoger. None si no hay nada pendiente."""
        con_saldo = sorted((c for c in compras if c['pago'] and c['pago']['por_pagar']),
                           key=lambda c: (not c['pago']['vencido'], c['pago']['vence_orden'], c['orden']))
        if con_saldo:
            return {'tipo': 'saldo', 'compra': con_saldo[0], 'otras': len(con_saldo) - 1}
        apartados = sorted((c for c in compras if c['apartado']), key=lambda c: c['apartado'])
        if apartados:
            return {'tipo': 'apartado', 'compra': apartados[0], 'otras': len(apartados) - 1}
        listas = [c for c in compras if c['entrega'] and c['entrega']['estado'] == 'listo']
        if listas:
            return {'tipo': 'entrega', 'compra': listas[0], 'otras': len(listas) - 1}
        if puntos['por_recoger']:
            return {'tipo': 'premios', 'canjes': puntos['por_recoger']}
        return None

    def _mc_inicio(self, ficha, website, base_url, tienda=False):
        compras = self._mc_compras(ficha, website, tienda)['compras']
        puntos = self._mc_puntos(ficha, base_url)
        return {
            'pendiente': self._mc_pendiente(compras, puntos),
            'ultima': next((c for c in compras if c['grupo'] != 'canceladas'), None),
            'puntos': puntos,
            'hay_compras': bool(compras),
        }

    def _mc_puntos(self, ficha, base_url=''):
        """Lo que antes enseñaba /socios/cuenta, para el mostrador. Cifras de reglas solo de puntos.json; el saldo es
        la suma del libro (dcasa_saldo)."""
        reglas = R.cargar_reglas()
        ficha = ficha.commercial_partner_id.sudo()
        saldo = ficha.dcasa_saldo
        es_socio = bool(ficha.active and ficha.dcasa_reclamada and ficha.dcasa_socio_estado == 'activo')
        try:
            equivale = R.como_dolares(R.centavos_de_puntos(saldo, reglas)) if saldo > 0 else ''
        except R.FaltaConfigurar:
            equivale = ''   # sin canje.puntosPorDolar no se dice cuánto valen
        Canje = self.env['dcasa.canje'].sudo()
        estados = dict(ESTADOS_CANJE)
        por_recoger = [{
            'codigo': canje.codigo,
            'premio': canje.premio_nombre,
            'web': canje.origen == 'web',
            'producto': canje.premio_tipo == 'producto',
            'vence': fecha_hora(canje.expira_en),
        } for canje in Canje.search([('partner_id', '=', ficha.id), ('estado', '=', 'solicitado')],
                                    order='expira_en asc, id asc')]
        historial = [{
            'premio': canje.premio_nombre,
            'codigo': canje.codigo,
            'fecha': fecha_corta(canje.solicitado_en),
            'estado': estados.get(canje.estado, canje.estado),
            'entregado': canje.estado == 'entregado',
        } for canje in Canje.search([('partner_id', '=', ficha.id), ('estado', '!=', 'solicitado')], limit=10)]
        premios = self.env['dcasa.premio']._catalogo().sorted(lambda p: (p.puntos, p.id))
        alcanzables = premios.filtered(lambda p: p.puntos <= saldo)
        siguiente = premios.filtered(lambda p: p.puntos > saldo)[:1]
        tipos = dict(self.env['dcasa.movimiento']._fields['tipo'].selection)
        movimientos = [{
            'motivo': movimiento.motivo or tipos.get(movimiento.tipo, ''),
            'fecha': fecha_corta(movimiento.ocurrido_en),
            'puntos': ('+' if movimiento.puntos > 0 else '') + R.como_puntos(movimiento.puntos),
            'positivo': movimiento.puntos > 0,
        } for movimiento in self.env['dcasa.movimiento'].sudo().search([('partner_id', '=', ficha.id)], limit=30)]
        codigo = ficha.dcasa_socio_codigo or ''
        link = f'{(base_url or "").rstrip("/")}/r/{codigo}' if codigo and es_socio else ''
        texto = (f"Te invito a D'CASA Panamá: muebles, colchones y todo para tu casa. Regístrate con mi código "
                 f"{codigo} y con tu primera compra ganamos los dos: {link}")
        return {
            'es_socio': es_socio,
            'suspendido': ficha.dcasa_socio_estado != 'activo',
            'saldo': saldo,
            'saldo_fmt': R.como_puntos(saldo),
            'equivale': equivale,
            'codigo': codigo,
            'por_recoger': por_recoger,
            'historial': historial,
            'premios': len(premios),
            'alcanza': alcanzables[-1:].name or '',
            'siguiente': {'premio': siguiente.name, 'faltan': R.como_puntos(siguiente.puntos - saldo),
                          'porcentaje': max(0, min(100, saldo * 100 // siguiente.puntos)) if siguiente.puntos else 0}
                         if siguiente else None,
            'ahijados': [{'nombre': ahijado._dcasa_nombre_publico(), 'compro': bool(ahijado.dcasa_referido_pagado_en)}
                         for ahijado in ficha.dcasa_ahijado_ids.sudo().filtered('active')],
            'movimientos': movimientos,
            'link': link,
            'invitar': f'https://wa.me/?text={quote(texto)}' if link else '',
            'qr': f'/report/barcode/?barcode_type=QR&value={quote(link, safe="")}&width=220&height=220' if link else '',
            'al_padrino': R.como_puntos(reglas['referido']['puntosAlPadrino']),
            'horas': reglas['canje']['vigenciaDelCodigoHoras'],
            'vendedor': bool(ficha.dcasa_vendedor_codigo),
        }

    def _mc_datos(self, ficha, persona=None, tienda=False):
        """Mis datos, solo lectura. A quien entra con PIN no se le enseña el correo entero, ni cédula, dirección o
        teléfonos: solo el celular con el que entra."""
        ficha = ficha.commercial_partner_id.sudo()
        persona = (persona or ficha).sudo()
        celular = R.celular_fmt(ficha.dcasa_celular) if ficha.dcasa_celular else ''
        if tienda and not celular:
            celular = persona.phone or ficha.phone or ''
        correo = persona.email or ficha.email or ''
        return {
            'nombre': persona.name or ficha.name or '',
            'celular': celular,
            'correo': correo if tienda else correo_tapado(correo),
            'codigo': ficha.dcasa_socio_codigo or '',
            'cumple': cumple_texto(ficha.dcasa_cumple),
            'es_socio': bool(ficha.active and ficha.dcasa_reclamada and ficha.dcasa_socio_estado == 'activo'),
            'tienda': tienda,
        }

    @staticmethod
    def _mc_primer_nombre(persona):
        partes = (persona.name or '').split()
        return partes[0].capitalize() if partes and partes[0].isupper() else (partes[0] if partes else '')
