"""El link del vendedor (/v/<código>) y su panel (/socios/vendedor).

El vendedor entra con la misma sesión de Socios (celular + PIN, o la sesión de la tienda): es la misma ficha. Aquí no
hay otro login.
"""

from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from ..models import reglas as R
from ..models import reglas_vendedores as RV
from ..models.dcasa_canje import ESTADOS_CANJE
from ..models.ir_http import SESSION_VENDEDOR
from .main import SESSION_AVISO, socio_por_pin


class VendedoresDcasa(http.Controller):

    # ------------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------------

    def _ficha(self):
        """La ficha con sesión (por PIN o por la tienda), o vacío."""
        socio = socio_por_pin()
        if socio:
            return socio
        usuario = request.env.user
        if usuario and not usuario._is_public():
            ficha = usuario.partner_id.commercial_partner_id.sudo()
            if ficha.active and ficha.dcasa_reclamada and ficha.dcasa_socio_estado == 'activo':
                return ficha
        return request.env['res.partner'].sudo()

    def _avisar(self, texto, tipo='info'):
        request.session[SESSION_AVISO] = {'texto': texto, 'tipo': tipo}

    def _render(self, plantilla, valores=None):
        valores = dict(valores or {})
        valores.setdefault('aviso', request.session.pop(SESSION_AVISO, None))
        valores.setdefault('reglas', R.cargar_reglas())
        valores.setdefault('fmt_puntos', R.como_puntos)
        valores.setdefault('fmt_dolares', R.como_dolares)
        valores.setdefault('sesion_tienda', bool(request.env.user and not request.env.user._is_public()))
        valores.setdefault('estados_canje', dict(ESTADOS_CANJE))
        return request.render(plantilla, valores)

    # ------------------------------------------------------------------------
    # El link que comparte el vendedor
    # ------------------------------------------------------------------------

    @http.route('/v/<string:codigo>', type='http', auth='public', website=True, sitemap=False)
    def link_del_vendedor(self, codigo, **kwargs):
        """Quien llega por aquí queda con el código del vendedor en su sesión: su carrito sale a nombre de ese
        vendedor. Un código que no existe o suspendido no hace nada: igual se le lleva a la tienda."""
        vendedor = request.env['res.partner']._dcasa_vendedor_por_codigo(codigo)
        if vendedor and vendedor.dcasa_vendedor_estado == 'activo' and vendedor.active:
            request.session[SESSION_VENDEDOR] = vendedor.dcasa_vendedor_codigo
        return request.redirect('/shop')

    # ------------------------------------------------------------------------
    # El panel del vendedor
    # ------------------------------------------------------------------------

    @http.route('/socios/vendedor', type='http', auth='public', website=True, sitemap=False)
    def panel(self, **kwargs):
        ficha = self._ficha()
        if not ficha:
            return request.redirect('/socios')
        resumen = ficha._dcasa_vend_resumen_panel()
        if not resumen:
            return request.redirect('/socios/cuenta')
        env = request.env
        link = f'{request.httprequest.host_url.rstrip("/")}/v/{ficha.dcasa_vendedor_codigo}'
        texto = (f"Compra en D'CASA Panamá (muebles, colchones y todo para tu casa) con mi código "
                 f"{ficha.dcasa_vendedor_codigo}: {link}")
        Canje = env['dcasa.vend.canje'].sudo()
        return self._render('dcasa_socios.vendedor_panel', {
            'socio': ficha,
            'resumen': resumen,
            'movimientos': env['dcasa.vend.movimiento'].sudo().search([('partner_id', '=', ficha.id)], limit=30),
            'comisiones': env['dcasa.vend.comision'].sudo().search(
                [('partner_id', '=', ficha.id), ('anulada_en', '=', False)], limit=20),
            'premios': env['dcasa.premio']._catalogo_vendedores(),
            'canjes': Canje.search([('partner_id', '=', ficha.id), ('estado', '=', 'solicitado')]),
            'historial': Canje.search([('partner_id', '=', ficha.id), ('estado', '!=', 'solicitado')], limit=10),
            'directos': ficha.dcasa_vendedor_directo_ids.sudo().filtered('dcasa_vendedor_codigo'),
            'link': link,
            'whatsapp': f'https://wa.me/?text={quote(texto)}',
            'qr': f'/report/barcode/?barcode_type=QR&value={quote(link, safe="")}&width=220&height=220',
        })

    @http.route('/socios/vendedor/canjear', type='http', auth='public', website=True, methods=['POST'],
                sitemap=False)
    def canjear(self, premio_id=None, **kwargs):
        ficha = self._ficha()
        if not ficha or not ficha.dcasa_vendedor_codigo:
            return request.redirect('/socios')
        premio = request.env['dcasa.premio'].sudo().browse(int(premio_id)).exists() \
            if (premio_id or '').strip().isdigit() else request.env['dcasa.premio']
        try:
            canje = request.env['dcasa.vend.canje']._pedir(ficha, premio)
        except UserError as error:
            self._avisar(error.args[0], 'danger')
        else:
            horas = (RV.seccion(R.cargar_reglas()).get('canje') or {}).get('vigenciaDelCodigoHoras') or 72
            self._avisar(f'Tu código es {canje.codigo}. Recógelo en la tienda en las próximas {horas} horas.',
                         'success')
        return request.redirect('/socios/vendedor')

    @http.route('/socios/vendedor/canjes/<string:codigo>/cancelar', type='http', auth='public', website=True,
                methods=['POST'], sitemap=False)
    def cancelar_canje(self, codigo, **kwargs):
        ficha = self._ficha()
        if not ficha or not ficha.dcasa_vendedor_codigo:
            return request.redirect('/socios')
        canje = request.env['dcasa.vend.canje'].sudo().search([
            ('codigo', '=', R.codigo_normal(codigo)), ('partner_id', '=', ficha.id), ('estado', '=', 'solicitado'),
        ], limit=1)
        if canje:
            canje._cancelar_por_vendedor()
            self._avisar('Listo: cancelaste el premio y tus puntos volvieron.', 'success')
        return request.redirect('/socios/vendedor')

    @http.route('/vendedores/terminos', type='http', auth='public', website=True, sitemap=True)
    def terminos(self, **kwargs):
        return self._render('dcasa_socios.vendedor_terminos')
