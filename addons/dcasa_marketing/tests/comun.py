"""Datos de prueba de Marketing y de las fotos: usuarios por rol, productos de una categoría propia, fotos generadas,
facturas y entregas. Nombres inventados obvios (ZZMK…, CLIENTE DE PRUEBA)."""
import base64
import io
from datetime import timedelta

from PIL import Image

from odoo import Command, fields
from odoo.tests import TransactionCase


def foto(ancho=300, alto=200, color=(19, 64, 177), formato='JPEG'):
    """Una foto de prueba en base64 (texto), de un color liso y con una franja blanca arriba a la izquierda."""
    imagen = Image.new('RGB', (ancho, alto), color)
    for x in range(min(40, ancho)):
        for y in range(min(20, alto)):
            imagen.putpixel((x, y), (255, 255, 255))
    salida = io.BytesIO()
    imagen.save(salida, format=formato)
    return base64.b64encode(salida.getvalue()).decode()


def tamano(datos_b64):
    with Image.open(io.BytesIO(base64.b64decode(datos_b64))) as imagen:
        return imagen.size


def color_al_centro(datos_b64):
    with Image.open(io.BytesIO(base64.b64decode(datos_b64))) as imagen:
        ancho, alto = imagen.size
        return imagen.convert('RGB').getpixel((ancho // 2, alto // 2))


def crear_usuario(env, login, grupos):
    return env['res.users'].with_context(no_reset_password=True).create({
        'name': login.replace('_', ' ').upper(), 'login': login, 'password': login, 'tz': 'America/Panama',
        'group_ids': [Command.set([env.ref('base.group_user').id] + [env.ref(g).id for g in grupos])],
    })


class MarketingCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia = crear_usuario(cls.env, 'zzmk_gerencia', ['dcasa_base.group_gerencia'])
        cls.vendedora = crear_usuario(cls.env, 'zzmk_vendedora', ['dcasa_base.group_vendedora'])
        cls.bodega = crear_usuario(cls.env, 'zzmk_bodega', ['stock.group_stock_user'])
        cls.categoria = cls.env['product.category'].create({'name': 'ZZMK Categoría de prueba'})
        cls.otra_categoria = cls.env['product.category'].create({'name': 'ZZMK Otra categoría'})
        cls.cliente = cls.env['res.partner'].create({'name': 'CLIENTE DE PRUEBA ZZMK'})
        cls.bodega_principal = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.hoy = fields.Date.context_today(cls.env['dcasa.marketing'])

    @classmethod
    def producto(cls, nombre, codigo=None, stock=0, categoria=None, con_foto=False, precio=100.0, extras=0):
        plantilla = cls.env['product.template'].create({
            'name': nombre, 'default_code': codigo, 'list_price': precio, 'is_storable': True, 'sale_ok': True,
            'categ_id': (categoria or cls.categoria).id, 'taxes_id': [Command.clear()],
            'image_1920': foto() if con_foto else False,
        })
        if extras:
            cls.env['product.image'].create([{
                'product_tmpl_id': plantilla.id, 'name': f'{nombre} ({i + 2})', 'sequence': i + 1,
                'image_1920': foto(color=(10 * i, 100, 50)),
            } for i in range(extras)])
        if stock:
            cls.env['stock.quant']._update_available_quantity(
                plantilla.product_variant_id, cls.bodega_principal.lot_stock_id, stock)
        return plantilla

    def facturar(self, plantilla, cantidad, dias_atras=0, nota=False):
        """Una factura de cliente publicada (o, con ``nota``, una nota de crédito) con ese producto, hace N días."""
        dia = self.hoy - timedelta(days=dias_atras)
        factura = self.env['account.move'].create({
            'move_type': 'out_refund' if nota else 'out_invoice', 'partner_id': self.cliente.id,
            'invoice_date': dia, 'date': dia,
            'invoice_line_ids': [Command.create({
                'product_id': plantilla.product_variant_id.id, 'quantity': cantidad, 'price_unit': 10.0,
                'tax_ids': [Command.clear()]})],
        })
        factura.action_post()
        return factura

    def entregar(self, plantilla, cantidad, dias_atras=0, devolver=False):
        """Una salida hecha de la bodega al cliente (o, con ``devolver``, la vuelta) hace N días."""
        interna = self.bodega_principal.lot_stock_id
        cliente = self.env.ref('stock.stock_location_customers')
        origen, destino = (cliente, interna) if devolver else (interna, cliente)
        movimiento = self.env['stock.move'].create({
            'product_id': plantilla.product_variant_id.id, 'product_uom_qty': cantidad,
            'product_uom': plantilla.uom_id.id, 'location_id': origen.id, 'location_dest_id': destino.id,
        })
        movimiento._action_confirm()
        movimiento._action_assign()
        movimiento.quantity = cantidad
        movimiento.picked = True
        movimiento._action_done()
        dia = self.hoy - timedelta(days=dias_atras)
        movimiento.date = fields.Datetime.to_datetime(dia) + timedelta(hours=17)
        return movimiento

    def marketing(self, usuario=None):
        return self.env['dcasa.marketing'].with_user(usuario or self.gerencia)
