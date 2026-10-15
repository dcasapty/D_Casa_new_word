"""«Imprimir documentos»: un cuadro pequeño que junta en UN solo PDF lo que se imprime de una venta.

Es una facilidad, no un sistema nuevo: reutiliza los informes que ya existen (la factura que imprime el botón
«Imprimir» de siempre y la «Nota de entrega» de Inventario) y nada de lo de antes cambia.
Por cada factura, en este orden: factura del cliente → copia de la empresa → nota de entrega / retiro de bodega.
"""
import logging
import time

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError

from ..models import paquete

_logger = logging.getLogger(__name__)

# (clave, nombre que ve la usuaria). El orden de esta lista es el orden del PDF.
DOCUMENTOS = [
    ('cliente', 'Factura del cliente'),
    ('copia', 'Copia de la empresa'),
    ('entrega', 'Nota de entrega / retiro de bodega'),
]
CLAVES = [clave for clave, _nombre in DOCUMENTOS]
# El informe de Inventario que se imprime como nota de entrega (el mismo de «Imprimir» en la entrega).
INFORME_ENTREGA = 'stock.action_report_delivery'


class DcasaImpresionPaquete(models.TransientModel):
    _name = 'dcasa.impresion.paquete'
    _description = 'Imprimir documentos de una venta'

    move_ids = fields.Many2many(
        'account.move', 'dcasa_impresion_paquete_move_rel', 'paquete_id', 'move_id', string='Facturas')
    pago_ids = fields.Many2many(
        'account.payment', 'dcasa_impresion_paquete_pago_rel', 'paquete_id', 'pago_id', string='Pagos',
        help='Solo cuando el cuadro sale al completar un pago: al cerrarlo se muestra el pago como siempre.')
    tras_pago = fields.Boolean(help='El cuadro salió al completar un pago: se ofrece y se puede cerrar sin imprimir.')
    omitidas = fields.Integer(
        help='Cuántos de lo elegido se dejó fuera por no ser una factura de cliente ya publicada.')
    incluir_cliente = fields.Boolean('Factura del cliente', default=True)
    incluir_copia = fields.Boolean('Copia de la empresa', default=True)
    incluir_entrega = fields.Boolean('Nota de entrega / retiro de bodega', default=True)
    resumen = fields.Char(compute='_compute_informacion')
    entregas_texto = fields.Char(compute='_compute_informacion')
    aviso = fields.Char(compute='_compute_informacion')
    excede = fields.Boolean(compute='_compute_informacion')

    # ------------------------------------------------------------------
    # Lo que muestra el cuadro
    # ------------------------------------------------------------------

    @api.depends('move_ids', 'omitidas')
    def _compute_informacion(self):
        for paquete_ in self:
            facturas = paquete_.move_ids
            cuantas = len(facturas)
            paquete_.excede = cuantas > paquete.MAX_FACTURAS
            if cuantas == 1:
                paquete_.resumen = f'{facturas.name} · {facturas.partner_id.display_name}'
            else:
                paquete_.resumen = f'{cuantas} facturas'
            entregas = facturas._dcasa_entregas()
            if not entregas:
                paquete_.entregas_texto = ('Esta factura no tiene una entrega ligada: no se agrega nada.'
                                           if cuantas == 1 else
                                           'Estas facturas no tienen una entrega ligada: no se agrega nada.')
            else:
                nombres = entregas.sorted('id').mapped('name')
                resto = f' y {len(nombres) - 4} más' if len(nombres) > 4 else ''
                paquete_.entregas_texto = 'Entrega: ' + ', '.join(nombres[:4]) + resto
            aviso = ''
            if paquete_.excede:
                aviso = (f'Elegiste {cuantas} facturas y el máximo por paquete es {paquete.MAX_FACTURAS}. '
                         'Elige menos y vuelve a intentar.')
            elif paquete_.omitidas:
                aviso = (f'Se dejaron fuera {paquete_.omitidas} de lo que elegiste: '
                         'solo van las facturas de clientes ya publicadas.')
            paquete_.aviso = aviso

    # ------------------------------------------------------------------
    # Cómo se abre
    # ------------------------------------------------------------------

    @api.model
    def _separar_validas(self, facturas):
        """(las que van en el paquete, las que no). Solo facturas de clientes ya publicadas."""
        validas = facturas.filtered(lambda f: f.move_type == 'out_invoice' and f.state == 'posted')
        return validas, facturas - validas

    @api.model
    def _accion_dialogo(self, facturas, pagos=None, sin_factura=0, tras_pago=False):
        """La acción que abre el cuadro para estas facturas.

        ``tras_pago``: sale al completar un pago (``pagos``: los que se acaban de registrar, para mostrarlos al cerrar).
        ``sin_factura``: cuántos pedidos elegidos no tenían factura.
        """
        validas, omitidas = self._separar_validas(facturas)
        if not validas:
            raise UserError(self.env._(
                'No hay facturas de clientes publicadas para imprimir aquí. '
                'Publica la factura y vuelve a intentar.'))
        cuadro = self.create({
            'move_ids': [Command.set(validas.ids)],
            'pago_ids': [Command.set(pagos.ids)] if pagos else [],
            'tras_pago': tras_pago,
            'omitidas': len(omitidas) + sin_factura,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Imprimir documentos'),
            'res_model': self._name,
            'res_id': cuadro.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------

    def _claves_marcadas(self):
        self.ensure_one()
        return [clave for clave in CLAVES if self[f'incluir_{clave}']]

    def _accion_siguiente(self):
        """Qué pasa al terminar o al cerrar el cuadro: si salió al completar un pago, el pago, como siempre."""
        self.ensure_one()
        if not self.pago_ids:
            return {'type': 'ir.actions.act_window_close'}
        accion = {
            'name': self.env._('Pagos'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'context': {'create': False},
        }
        if len(self.pago_ids) == 1:
            accion.update({'view_mode': 'form', 'res_id': self.pago_ids.id})
        else:
            accion.update({'view_mode': 'list,form', 'domain': [('id', 'in', self.pago_ids.ids)]})
        return accion

    def _accion_pdf(self, modo):
        """El navegador pide el PDF al servidor y lo imprime (o lo guarda) sin dejar archivos sueltos."""
        self.ensure_one()
        facturas, claves = self._preparar(self.move_ids, self._claves_marcadas())
        return {
            'type': 'ir.actions.client',
            'tag': 'dcasa_paquete_pdf',
            'params': {
                'url': f"/dcasa/paquete.pdf?facturas={','.join(map(str, facturas.ids))}&docs={','.join(claves)}",
                'modo': modo,
                'nombre': self._nombre_archivo(facturas),
                'next': self._accion_siguiente(),
            },
        }

    def action_imprimir(self):
        return self._accion_pdf('imprimir')

    def action_descargar(self):
        return self._accion_pdf('descargar')

    def action_cerrar(self):
        self.ensure_one()
        return self._accion_siguiente()

    # ------------------------------------------------------------------
    # El PDF
    # ------------------------------------------------------------------

    @api.model
    def _preparar(self, facturas, claves):
        """(facturas válidas, claves en orden de impresión) o un error que la usuaria entiende."""
        validas, _omitidas = self._separar_validas(facturas)
        if not validas:
            raise UserError(self.env._('No hay facturas de clientes publicadas para imprimir.'))
        if len(validas) > paquete.MAX_FACTURAS:
            raise UserError(self.env._(
                'Elegiste %(cuantas)s facturas y el máximo por paquete es %(maximo)s. '
                'Elige menos y vuelve a intentar.', cuantas=len(validas), maximo=paquete.MAX_FACTURAS))
        elegidas = [clave for clave in CLAVES if clave in set(claves)]
        if not elegidas:
            raise UserError(self.env._('Marca al menos un documento para imprimir.'))
        return validas, elegidas

    @api.model
    def _nombre_archivo(self, facturas):
        if len(facturas) == 1:
            nombre = (facturas.name or 'factura').replace('/', '-').replace(' ', '-')
            return f'Documentos-{nombre}.pdf'
        return f'Documentos-{len(facturas)}-facturas.pdf'

    @api.model
    def _pdfs_por_registro(self, informe, registros):
        """{id: PDF} de cada registro, como los imprime ese informe.

        Con varios registros se pide un solo PDF a wkhtmltopdf y se parte por registro (lo mismo que hace Odoo al
        enviar varias facturas): mucho más rápido que uno por uno. Si no se puede partir, se hace uno por uno.
        """
        informe_modelo = self.env['ir.actions.report']
        if len(registros) > 1:
            try:
                flujos, tipo = informe_modelo._pre_render_qweb_pdf(informe, res_ids=registros.ids)
            except UserError:
                raise
            except Exception:  # noqa: BLE001 - p. ej. una versión de PyPDF2 que no sabe partir: se hace uno por uno
                _logger.warning('DCASA_PAQUETE no se pudo partir el PDF; se arma uno por uno', exc_info=True)
            else:
                if tipo == 'pdf' and all(flujos.get(r.id) and flujos[r.id].get('stream') for r in registros):
                    return {r.id: flujos[r.id]['stream'].getvalue() for r in registros}
        resultado = {}
        for registro in registros:
            contenido, tipo = informe_modelo._render_qweb_pdf(informe, [registro.id])
            if tipo != 'pdf':
                raise UserError(self.env._('No se pudo armar el PDF. Avísale a quien administra el sistema.'))
            resultado[registro.id] = contenido
        return resultado

    @api.model
    def _armar_pdf(self, facturas, claves):
        """(contenido del PDF, nombre del archivo) con los documentos de las facturas, factura por factura."""
        inicio = time.monotonic()
        # Igual que los botones: Facturación o lector contable (un usuario del portal ve sus facturas, pero no esto).
        usuario = self.env.user
        if not (usuario.has_group('account.group_account_invoice')
                or usuario.has_group('account.group_account_readonly')):
            raise AccessError(self.env._('No tienes permiso para imprimir estos documentos.'))
        facturas, claves = self._preparar(facturas, claves)
        enviar = self.env['account.move.send']

        # Factura del cliente: el mismo informe que usa el botón «Imprimir» de cada factura.
        facturas_pdf = {}
        if 'cliente' in claves or 'copia' in claves:
            por_informe = {}
            for factura in facturas:
                informe = enviar._get_default_pdf_report_id(factura)
                por_informe.setdefault(informe, self.env['account.move'])
                por_informe[informe] |= factura
            for informe, grupo in por_informe.items():
                facturas_pdf.update(self._pdfs_por_registro(informe, grupo))

        # Nota de entrega: las entregas de salida de la venta; si dos facturas comparten entrega, sale una vez.
        entregas_por_factura, entregas_pdf = {}, {}
        if 'entrega' in claves:
            vistas = self.env['stock.picking']
            for factura in facturas:
                nuevas = factura._dcasa_entregas() - vistas
                entregas_por_factura[factura.id] = nuevas.sorted('id')
                vistas |= nuevas
            if vistas:
                entregas_pdf = self._pdfs_por_registro(self.env.ref(INFORME_ENTREGA), vistas)

        partes = []
        for factura in facturas:
            if 'cliente' in claves:
                partes.append(facturas_pdf[factura.id])
            if 'copia' in claves:
                partes.append(paquete.sellar_copia(facturas_pdf[factura.id]))
            for entrega in entregas_por_factura.get(factura.id, ()):
                partes.append(entregas_pdf[entrega.id])
        if not partes:
            raise UserError(self.env._('Las facturas elegidas no tienen una entrega ligada: no hay nada que imprimir.'))
        contenido = paquete.unir(partes)
        # Solo cifras (nada de nombres ni montos): sirve para saber cuánto tarda un lote en producción.
        _logger.info('DCASA_PAQUETE facturas=%s documentos=%s paginas=%s segundos=%.1f',
                     len(facturas), len(partes), paquete.paginas(contenido), time.monotonic() - inicio)
        return contenido, self._nombre_archivo(facturas)
