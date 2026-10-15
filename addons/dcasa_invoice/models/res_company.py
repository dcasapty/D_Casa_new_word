from markupsafe import Markup

from odoo import api, fields, models

from . import formato

# (campo, título impreso). Vacío no se imprime. Textos iniciales propuestos (la dueña autorizó, 2026-10-03,
# que se redactaran y el administrador los cambie en Ajustes → Empresas → Documentos D'CASA).
BLOQUES_LEGALES = [
    ('dcasa_factura_garantia', 'Garantía'),
    ('dcasa_factura_cambios', 'Cambios y devoluciones'),
    ('dcasa_factura_terminos', 'Términos'),
]


# Se escriben UNA vez (parámetro TEXTOS_PUESTOS) y solo en campos vacíos: lo que el administrador
# cambie o borre después no se vuelve a pisar al actualizar el módulo. Revisarlos con un abogado.
TEXTOS_INICIALES = {
    'dcasa_factura_garantia': (
        "Tus muebles tienen garantía de 30 días desde la entrega contra defectos de fabricación. "
        "No cubre golpes, humedad, mal uso ni armado hecho por terceros. Escríbenos por WhatsApp "
        "con tu factura y fotos del detalle y lo resolvemos."),
    'dcasa_factura_cambios': (
        "Puedes cambiar tu compra dentro de los 7 días siguientes a la entrega, con la factura, "
        "el producto sin uso y en su empaque original. Los colchones no tienen cambio por "
        "higiene, salvo defecto de fábrica."),
    'dcasa_factura_terminos': (
        "Precios en dólares; el ITBMS se suma al precio. Un apartado se confirma con un abono y "
        "el mueble queda reservado hasta completar el pago en el plazo acordado. El flete se "
        "cotiza según la zona y se paga aparte; la entrega se coordina por WhatsApp."),
}
TEXTOS_PUESTOS = 'dcasa_invoice.textos_iniciales_puestos'


class ResCompany(models.Model):
    _inherit = 'res.company'

    dcasa_factura_garantia = fields.Text(
        string='Garantía (factura)',
        help='Texto corto que se imprime en facturas, cotizaciones y pedidos. Vacío: no se imprime.')
    dcasa_factura_cambios = fields.Text(
        string='Cambios y devoluciones (factura)',
        help='Texto corto que se imprime en facturas, cotizaciones y pedidos. Vacío: no se imprime.')
    dcasa_factura_terminos = fields.Text(
        string='Términos (factura)',
        help='Texto corto que se imprime en facturas, cotizaciones y pedidos. Vacío: no se imprime.')

    dcasa_ofrecer_impresion_pago = fields.Boolean(
        string='Ofrecer imprimir los documentos al completar el pago', default=True,
        help='Al registrar el pago que deja una factura de cliente pagada por completo, sale un cuadro pequeño '
             'para imprimir (o descargar) la factura, la copia de la empresa y la nota de entrega. Se cierra con '
             'un clic. Apagado, el pago se registra exactamente como antes.')

    dcasa_mostrar_qr_documentos = fields.Boolean(
        string='Mostrar el código QR en la factura y la cotización', default=False,
        help='Pone un cuadro QR pequeño al final de la factura, la nota de crédito, la cotización y la nota de '
             'entrega. Es de uso interno: tu equipo lo escanea (con el Escáner o con la cámara del teléfono) y se '
             'abre ese mismo documento en el sistema, pidiendo la clave si hace falta. No lleva datos del cliente y '
             'no se ofrece al cliente. Apagado, esos documentos salen exactamente como siempre. El pedido de compra '
             'siempre lleva su QR.')
    dcasa_mostrar_codigo_publico = fields.Boolean(
        string='Mostrar el código público de los productos en la factura y la cotización, en lugar del código '
               'del proveedor', default=False,
        help='En la columna «Código» de la factura, la nota de crédito, la cotización y la nota de entrega sale el '
             'código público del producto (DC-K7M4PX, el mismo que ve el cliente en la tienda) en lugar de la '
             'referencia del proveedor. Los productos sin código público (flete, servicios) quedan en blanco. '
             'Además, las cotizaciones y facturas NUEVAS ya no guardan la referencia del proveedor en el nombre de '
             'la línea. Apagado, todo sale exactamente como siempre.')

    dcasa_entrega_facil = fields.Boolean(
        string='Nota de entrega fácil de leer (con fotos y dibujos de cantidad)', default=False,
        help='La nota de entrega que va a bodega sale pensada para leerse sin errores: cada producto con su foto, '
             'la cantidad en número grande y en dibujitos (uno por pieza), una casilla para marcar y poco texto. '
             'Sirve a personas con dislexia, autismo, que leen poco o dominan otro idioma. Apagado, la nota de '
             'entrega sale exactamente como siempre.')

    @api.model
    def _dcasa_poner_textos_iniciales(self):
        """Llena garantía, cambios y términos vacíos con TEXTOS_INICIALES, una sola vez por base."""
        param = self.env['ir.config_parameter'].sudo()
        if param.get_param(TEXTOS_PUESTOS):
            return
        for empresa in self.sudo().search([]):
            vals = {campo: texto for campo, texto in TEXTOS_INICIALES.items() if not empresa[campo]}
            if vals:
                empresa.write(vals)
        param.set_param(TEXTOS_PUESTOS, '1')

    def _dcasa_bloques_legales(self):
        """[(título, texto)] de garantía, cambios y términos; solo los que la dueña escribió."""
        self.ensure_one()
        bloques = []
        for campo, titulo in BLOQUES_LEGALES:
            texto = (self[campo] or '').strip()
            if texto:
                bloques.append((titulo, texto))
        return bloques

    def _dcasa_whatsapp(self):
        """El WhatsApp del pie: el configurado en el sitio web si existe; si no, el teléfono de la empresa."""
        self.ensure_one()
        if 'website' in self.env:
            Website = self.env['website'].sudo()
            if 'dcasa_whatsapp_number' in Website._fields:
                website = Website.search([('company_id', '=', self.id)], limit=1) or Website.search([], limit=1)
                if website.dcasa_whatsapp_number:
                    return website.dcasa_whatsapp_number
        return self.phone or ''

    def _dcasa_direccion_corta(self):
        """«Frente al Parque Libertadores, Diagonal a la Discoteca Seven, La Chorrera» para el pie."""
        self.ensure_one()
        partes = [self.street, self.street2, self.city]
        return ', '.join(parte.strip() for parte in partes if parte and parte.strip())

    def _dcasa_url_publica(self):
        """La dirección del sitio que se imprime en un papel: nunca localhost.

        Por orden: el dominio del sitio web, ``web.base.url`` y la web de la empresa.
        """
        self.ensure_one()
        candidatos = []
        if 'website' in self.env:
            website = self.env['website'].sudo().search([('company_id', '=', self.id)], limit=1)
            candidatos.append(website.domain)
        candidatos += [self.env['ir.config_parameter'].sudo().get_param('web.base.url'), self.website]
        for candidato in candidatos:
            url = formato.url_con_esquema(candidato)
            if url and not formato.url_es_local(url):
                return url
        return ''

    def _dcasa_url_publica_corta(self):
        """'https://dcasapty.com' → 'dcasapty.com' (así se lee mejor en papel)."""
        return self._dcasa_url_publica().split('://', 1)[-1]

    def _dcasa_sin_enlaces_locales(self, html):
        """Cambia en un texto la URL local del servidor por la pública (p. ej. …/terms)."""
        if not html:
            return html
        local = (self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')
        publica = self._dcasa_url_publica()
        texto = str(html)
        if local and publica and formato.url_es_local(local) and local in texto:
            texto = texto.replace(local, publica)
        return Markup(texto) if isinstance(html, Markup) else texto
