"""La app del socio: /socios.

El cliente del QR no tiene correo ni usuario de Odoo, ni lo va a tener: entra con
su celular y un PIN de seis dígitos, de pie en el mostrador. Por eso esta zona no
usa el login de Odoo: la sesión guarda la ficha y la "huella" del PIN (si una
vendedora lo reinicia, las sesiones abiertas dejan de valer).
"""

from urllib.parse import quote

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request

from ..models import reglas as R
from ..models.ir_http import SESSION_PADRINO

SESSION_SOCIO = 'dcasa_socio'
SESSION_AVISO = 'dcasa_aviso'
NO_COINCIDEN = 'Ese número y ese PIN no coinciden.'
MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre',
         'Octubre', 'Noviembre', 'Diciembre']


class SociosDcasa(http.Controller):

    # ------------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------------

    def _socio(self):
        """La ficha de la sesión, o vacío si no hay sesión válida."""
        datos = request.session.get(SESSION_SOCIO) or {}
        Partner = request.env['res.partner'].sudo()
        socio = Partner.browse(datos.get('id')).exists() if datos.get('id') else Partner
        if not socio or not socio.active or socio.dcasa_socio_estado != 'activo' \
                or Partner._dcasa_huella_pin(socio) != datos.get('huella'):
            request.session.pop(SESSION_SOCIO, None)
            return Partner
        return socio

    def _iniciar_sesion(self, socio):
        request.session[SESSION_SOCIO] = {'id': socio.id, 'huella': socio._dcasa_huella_pin(socio)}
        if hasattr(request.session, 'should_rotate'):
            request.session.should_rotate = True

    def _avisar(self, texto, tipo='info'):
        request.session[SESSION_AVISO] = {'texto': texto, 'tipo': tipo}

    def _render(self, plantilla, valores=None):
        valores = dict(valores or {})
        valores.setdefault('aviso', request.session.pop(SESSION_AVISO, None))
        valores.setdefault('reglas', R.cargar_reglas())
        valores.setdefault('fmt_puntos', R.como_puntos)
        valores.setdefault('fmt_dolares', R.como_dolares)
        return request.render(plantilla, valores)

    # ------------------------------------------------------------------------
    # Entrar
    # ------------------------------------------------------------------------

    @http.route('/socios', type='http', auth='public', website=True, sitemap=True)
    def inicio(self, **kwargs):
        if self._socio():
            return request.redirect('/socios/cuenta')
        return self._render('dcasa_socios.socios_inicio')

    @http.route('/socios/entrar', type='http', auth='public', website=True, methods=['POST'], sitemap=False,
                captcha='socios_entrar')
    def entrar(self, celular='', pin='', **kwargs):
        Partner = request.env['res.partner'].sudo()
        socio = Partner._dcasa_por_celular(celular)
        ahora = fields.Datetime.now()
        # Nunca se distingue «ese número no existe» de «ese PIN está mal»: sería
        # un buscador de quién es cliente de D'CASA.
        if not socio or not socio.active or not socio.dcasa_reclamada:
            return self._render('dcasa_socios.socios_inicio', {'error': NO_COINCIDEN, 'celular': celular})
        if socio._dcasa_bloqueada():
            espera = R.cuanto_queda(socio.dcasa_bloqueado_hasta, ahora)
            return self._render('dcasa_socios.socios_inicio', {
                'error': f'Por seguridad, espera {espera} antes de volver a intentar, o pídenos en la tienda '
                         f'que te desbloqueemos.', 'celular': celular})
        try:
            correcto = socio._dcasa_pin_correcto(pin)
        except R.FaltaConfigurar:
            return self._render('dcasa_socios.socios_inicio', {'error': 'El programa aún no está listo. '
                                                               'Escríbenos por WhatsApp.'})
        if not correcto:
            socio._dcasa_registrar_fallo()
            return self._render('dcasa_socios.socios_inicio', {'error': NO_COINCIDEN, 'celular': celular})
        if socio.dcasa_socio_estado != 'activo':
            return self._render('dcasa_socios.socios_inicio', {
                'error': 'Tu cuenta está suspendida. Escríbenos por WhatsApp y lo revisamos.'})
        socio._dcasa_desbloquear()
        self._iniciar_sesion(socio)
        if socio.dcasa_pin_temporal:
            self._avisar('Elige un PIN nuevo: el que te dimos en la tienda era temporal.')
            return request.redirect('/socios/pin')
        return request.redirect('/socios/cuenta')

    @http.route('/socios/salir', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def salir(self, **kwargs):
        request.session.pop(SESSION_SOCIO, None)
        return request.redirect('/socios')

    # ------------------------------------------------------------------------
    # Registro (y reclamar una ficha que ya tiene compras)
    # ------------------------------------------------------------------------

    @http.route('/r/<string:codigo>', type='http', auth='public', website=True, sitemap=False)
    def invitacion(self, codigo, **kwargs):
        """El link que comparte el socio."""
        padrino = request.env['res.partner']._dcasa_por_codigo(codigo)
        if padrino:
            request.session[SESSION_PADRINO] = padrino.dcasa_socio_codigo
        return request.redirect('/socios/registro')

    @http.route('/socios/registro', type='http', auth='public', website=True, methods=['GET', 'POST'],
                sitemap=False, captcha='socios_registro')
    def registro(self, **datos):
        padrino_codigo = datos.get('padrino') or request.session.get(SESSION_PADRINO) or ''
        padrino = request.env['res.partner']._dcasa_por_codigo(padrino_codigo)
        valores = {'datos': datos, 'padrino': padrino, 'meses': MESES}
        if request.httprequest.method != 'POST':
            return self._render('dcasa_socios.socios_registro', valores)
        try:
            socio = self._registrar(datos, padrino)
        except UserError as error:
            valores['error'] = error.args[0]
            return self._render('dcasa_socios.socios_registro', valores)
        except R.FaltaConfigurar:
            valores['error'] = 'El programa aún no está listo. Escríbenos por WhatsApp.'
            return self._render('dcasa_socios.socios_registro', valores)
        request.session.pop(SESSION_PADRINO, None)
        self._iniciar_sesion(socio)
        self._avisar('¡Listo! Ya eres socio de D’CASA.', 'success')
        return request.redirect('/socios/cuenta')

    def _registrar(self, datos, padrino):
        env = request.env
        Partner = env['res.partner'].sudo()
        if not datos.get('acepta'):
            raise UserError('Para entrar al programa hay que aceptar los términos.')
        nombre = (datos.get('nombre') or '').strip()
        apellido = (datos.get('apellido') or '').strip()
        if not nombre:
            raise UserError('Nos falta tu nombre.')
        celular = R.celular_normal(datos.get('celular'))
        if not R.celular_valido(celular):
            raise UserError('Ese número de celular no parece de Panamá. Son 8 números, como 6026-1919.')
        pin = (datos.get('pin') or '').strip()
        problema = R.problema_del_pin(pin, celular)
        if problema:
            raise UserError(R.EXPLICACION_PIN[problema])
        if pin != (datos.get('pin2') or '').strip():
            raise UserError('Los dos PIN no coinciden. Escríbelo otra vez.')
        cumple = ''
        if datos.get('cumple_mes') and datos.get('cumple_dia'):
            cumple = f"{int(datos['cumple_mes']):02d}-{int(datos['cumple_dia']):02d}"
        if not R.cumple_valido(cumple):
            raise UserError('Esa fecha de cumpleaños no existe.')
        correo = (datos.get('correo') or '').strip()
        if correo and '@' not in correo:
            raise UserError('Ese correo no parece un correo. Revísalo o déjalo vacío.')

        ahora = fields.Datetime.now()
        existente = Partner._dcasa_por_celular(celular)
        if existente:
            return self._reclamar(existente, datos, apellido, correo, cumple, pin)

        socio = Partner.create({
            'name': f'{nombre} {apellido}'.strip(),
            'dcasa_celular': celular,
            'phone': datos.get('celular'),
            'email': correo or False,
            'dcasa_cumple': cumple or False,
            'dcasa_terminos_version': R.VERSION_TERMINOS,
            'dcasa_terminos_aceptados_en': ahora,
        })
        socio._dcasa_asegurar_ficha(creado_por='qr')
        if padrino:
            socio._dcasa_asignar_padrino(padrino, ahora)
        socio._dcasa_guardar_pin(pin)
        return socio

    def _reclamar(self, ficha, datos, apellido, correo, cumple, pin):
        """El celular ya tiene ficha: la persona compró antes y sus puntos le esperan."""
        if not ficha.active:
            raise UserError('Ese número tuvo una cuenta que está retirada. Pasa por la tienda y te la '
                            'volvemos a activar.')
        if ficha.dcasa_reclamada:
            raise UserError('Ese número ya tiene cuenta. Entra con tu PIN, o pídenos en la tienda que '
                            'te lo reiniciemos.')
        # Con puntos esperando, reclamarla exige el código impreso en la factura:
        # sin eso, quien supiera el celular de un vecino se quedaría con sus puntos.
        if ficha.dcasa_saldo > 0 and R.codigo_normal(datos.get('codigo')) != ficha.dcasa_socio_codigo:
            raise UserError('Ya tienes compras registradas con ese número, así que tus puntos te esperan. '
                            'Para reclamarlos escribe el código de socio que aparece en tu factura, o pasa '
                            'por la tienda y te ayudamos.')
        if ficha.dcasa_socio_estado == 'suspendido':
            raise UserError('Tu cuenta está suspendida. Escríbenos por WhatsApp y lo revisamos.')
        valores = {
            'dcasa_terminos_version': R.VERSION_TERMINOS,
            'dcasa_terminos_aceptados_en': fields.Datetime.now(),
        }
        # Solo se completa lo que falta: la ficha manda.
        if correo and not ficha.email:
            valores['email'] = correo
        if cumple and not ficha.dcasa_cumple:
            valores['dcasa_cumple'] = cumple
        if apellido and len((ficha.name or '').split()) < 2:
            valores['name'] = f'{ficha.name} {apellido}'.strip()
        ficha.write(valores)
        ficha._dcasa_asegurar_ficha(creado_por='qr')
        ficha._dcasa_guardar_pin(pin)
        return ficha

    # ------------------------------------------------------------------------
    # Mi cuenta
    # ------------------------------------------------------------------------

    @http.route('/socios/cuenta', type='http', auth='public', website=True, sitemap=False)
    def cuenta(self, **kwargs):
        socio = self._socio()
        if not socio:
            return request.redirect('/socios')
        if socio.dcasa_pin_temporal:
            return request.redirect('/socios/pin')
        env = request.env
        saldo = socio.dcasa_saldo
        link = f'{request.httprequest.host_url.rstrip("/")}/r/{socio.dcasa_socio_codigo}'
        texto = (f"Te invito a D'CASA Panamá: muebles, colchones y todo para tu casa. Regístrate con mi "
                 f"código {socio.dcasa_socio_codigo} y con tu primera compra ganamos los dos: {link}")
        return self._render('dcasa_socios.socios_cuenta', {
            'socio': socio,
            'saldo': saldo,
            'movimientos': env['dcasa.movimiento'].sudo().search([('partner_id', '=', socio.id)], limit=30),
            'premios': env['dcasa.premio'].sudo().search([]).filtered(lambda p: p._disponible()),
            'canjes': env['dcasa.canje'].sudo().search([('partner_id', '=', socio.id),
                                                       ('estado', '=', 'solicitado')]),
            'ahijados': socio.dcasa_ahijado_ids.sudo().filtered('active'),
            'link': link,
            'whatsapp': f'https://wa.me/?text={quote(texto)}',
            'qr': f'/report/barcode/?barcode_type=QR&value={quote(link, safe="")}&width=220&height=220',
        })

    @http.route('/socios/canjear', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def canjear(self, premio_id=None, **kwargs):
        socio = self._socio()
        if not socio:
            return request.redirect('/socios')
        premio = request.env['dcasa.premio'].sudo().browse(int(premio_id or 0)).exists()
        try:
            canje = request.env['dcasa.canje']._pedir(socio, premio)
        except UserError as error:
            self._avisar(error.args[0], 'danger')
        else:
            horas = R.cargar_reglas()['canje']['vigenciaDelCodigoHoras']
            self._avisar(f'Tu código es {canje.codigo}. Enséñalo en la tienda en las próximas {horas} horas.',
                         'success')
        return request.redirect('/socios/cuenta')

    @http.route('/socios/canjes/<string:codigo>/cancelar', type='http', auth='public', website=True,
                methods=['POST'], sitemap=False)
    def cancelar_canje(self, codigo, **kwargs):
        socio = self._socio()
        if not socio:
            return request.redirect('/socios')
        canje = request.env['dcasa.canje'].sudo().search([
            ('codigo', '=', R.codigo_normal(codigo)), ('partner_id', '=', socio.id), ('estado', '=', 'solicitado'),
        ], limit=1)
        if canje:
            canje._cancelar_por_socio()
            self._avisar('Listo: cancelaste el premio y tus puntos volvieron.', 'success')
        return request.redirect('/socios/cuenta')

    @http.route('/socios/pin', type='http', auth='public', website=True, methods=['GET', 'POST'], sitemap=False)
    def cambiar_pin(self, **datos):
        socio = self._socio()
        if not socio:
            return request.redirect('/socios')
        if request.httprequest.method != 'POST':
            return self._render('dcasa_socios.socios_pin', {'socio': socio})
        error = None
        if not socio.dcasa_pin_temporal and not socio._dcasa_pin_correcto(datos.get('actual')):
            error = 'Tu PIN actual no es ese.'
        nuevo = (datos.get('nuevo') or '').strip()
        problema = R.problema_del_pin(nuevo, socio.dcasa_celular or '')
        if not error and problema:
            error = R.EXPLICACION_PIN[problema]
        if not error and nuevo != (datos.get('nuevo2') or '').strip():
            error = 'Los dos PIN no coinciden.'
        if error:
            return self._render('dcasa_socios.socios_pin', {'socio': socio, 'error': error})
        socio._dcasa_guardar_pin(nuevo)
        self._iniciar_sesion(socio)
        self._avisar('Tu PIN nuevo quedó guardado.', 'success')
        return request.redirect('/socios/cuenta')

    @http.route('/socios/terminos', type='http', auth='public', website=True, sitemap=True)
    def terminos(self, **kwargs):
        return self._render('dcasa_socios.socios_terminos')
