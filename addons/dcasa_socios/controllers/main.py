"""La app del socio: /socios.

El cliente del QR no tiene correo ni usuario de Odoo, ni lo va a tener: entra con
su celular y un PIN de seis dígitos, de pie en el mostrador. Por eso esta zona no
usa el login de Odoo: la sesión guarda la ficha y la "huella" del PIN (si una
vendedora lo reinicia, las sesiones abiertas dejan de valer).

Cuenta unificada: quien sí tiene usuario de la tienda (portal) es la misma ficha
``res.partner``. Si esa ficha ya es socio (tiene PIN), su sesión de la tienda vale
como sesión del socio; si tiene celular pero todavía no entró al programa, se le
invita a activarlo eligiendo un PIN.
"""

from urllib.parse import quote

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request

from ..models import reglas as R
from ..models.dcasa_canje import ESTADOS_CANJE
from ..models.ir_http import SESSION_PADRINO

SESSION_SOCIO = 'dcasa_socio'
SESSION_AVISO = 'dcasa_aviso'
NO_COINCIDEN = 'Ese número y ese PIN no coinciden.'
MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre',
         'Octubre', 'Noviembre', 'Diciembre']
# A dónde puede volver el socio después de pedir o cancelar un premio (nunca a una URL que mande el cliente).
VOLVER = {'cuenta': '/socios/cuenta', 'premios': '/socios/premios'}


def socio_por_pin():
    """La ficha de la sesión con PIN, o vacío si no hay sesión válida."""
    datos = request.session.get(SESSION_SOCIO) or {}
    Partner = request.env['res.partner'].sudo()
    socio = Partner.browse(datos.get('id')).exists() if datos.get('id') else Partner
    if not socio or not socio.active or socio.dcasa_socio_estado != 'activo' \
            or Partner._dcasa_huella_pin(socio) != datos.get('huella'):
        request.session.pop(SESSION_SOCIO, None)
        return Partner
    return socio


class SociosDcasa(http.Controller):

    # ------------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------------

    def _socio_por_pin(self):
        return socio_por_pin()

    def _ficha_de_la_tienda(self):
        """La ficha del usuario de la tienda con sesión (portal), o vacío para el visitante público."""
        usuario = request.env.user
        if not usuario or usuario._is_public():
            return request.env['res.partner'].sudo()
        return usuario.partner_id.commercial_partner_id.sudo()

    def _socio_de_la_tienda(self):
        """Cuenta unificada: la sesión de la tienda vale como sesión del socio si la ficha ya es socio."""
        ficha = self._ficha_de_la_tienda()
        if ficha and ficha.active and ficha.dcasa_reclamada and ficha.dcasa_socio_estado == 'activo':
            return ficha
        return request.env['res.partner'].sudo()

    def _socio(self):
        """La ficha del socio con sesión (por PIN o por la tienda), o vacío."""
        return self._socio_por_pin() or self._socio_de_la_tienda()

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
        valores.setdefault('sesion_tienda', bool(self._ficha_de_la_tienda()))
        valores.setdefault('estados_canje', dict(ESTADOS_CANJE))
        return request.render(plantilla, valores)

    def _celular_para_activar(self, ficha):
        """El celular con el que la ficha de la tienda entraría al programa, o ''. Tiene que ser válido
        y no ser ya la llave de otra ficha (un celular, un socio)."""
        celular = ficha.dcasa_celular or R.celular_normal(ficha.phone)
        if not R.celular_valido(celular):
            return ''
        otra = request.env['res.partner']._dcasa_por_celular(celular)
        if otra and otra != ficha:
            return ''
        return celular

    # ------------------------------------------------------------------------
    # Entrar
    # ------------------------------------------------------------------------

    @http.route('/socios', type='http', auth='public', website=True, sitemap=True)
    def inicio(self, **kwargs):
        if self._socio():
            return request.redirect('/socios/cuenta')
        ficha = self._ficha_de_la_tienda()
        if ficha:
            # Usuario de la tienda que todavía no es socio: misma ficha, se activa con un PIN.
            if not ficha.active or ficha.dcasa_socio_estado != 'activo':
                return self._render('dcasa_socios.socios_inicio', {
                    'error': 'Tu cuenta está suspendida. Escríbenos por WhatsApp y lo revisamos.'})
            celular = self._celular_para_activar(ficha)
            if celular:
                return self._render('dcasa_socios.socios_activar', {'ficha': ficha, 'celular': celular,
                                                                    'meses': MESES, 'datos': {}})
            return self._render('dcasa_socios.socios_inicio', {'ficha_sin_celular': ficha})
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
        if self._ficha_de_la_tienda():
            # La sesión del socio es la de la tienda: salir es cerrar la sesión de la tienda.
            return request.redirect('/web/session/logout?redirect=/socios')
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
        pin = self._pin_nuevo(datos, celular)
        cumple = self._cumple(datos)
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

    @staticmethod
    def _pin_nuevo(datos, celular):
        pin = (datos.get('pin') or '').strip()
        problema = R.problema_del_pin(pin, celular)
        if problema:
            raise UserError(R.EXPLICACION_PIN[problema])
        if pin != (datos.get('pin2') or '').strip():
            raise UserError('Los dos PIN no coinciden. Escríbelo otra vez.')
        return pin

    @staticmethod
    def _cumple(datos):
        cumple = ''
        if datos.get('cumple_mes') and datos.get('cumple_dia'):
            cumple = f"{int(datos['cumple_mes']):02d}-{int(datos['cumple_dia']):02d}"
        if not R.cumple_valido(cumple):
            raise UserError('Esa fecha de cumpleaños no existe.')
        return cumple

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
    # Cuenta unificada: el usuario de la tienda activa el programa en su misma ficha
    # ------------------------------------------------------------------------

    @http.route('/socios/activar', type='http', auth='user', website=True, methods=['POST'], sitemap=False)
    def activar(self, **datos):
        """El usuario de la tienda elige un PIN y acepta los términos: su ficha pasa a ser socio.

        La sesión de la tienda ya prueba quién es, así que no se le pide el código de la factura
        aunque tenga puntos esperando: esos puntos son de esta misma ficha.
        """
        if self._socio():
            return request.redirect('/socios/cuenta')
        ficha = self._ficha_de_la_tienda()
        celular = self._celular_para_activar(ficha) if ficha else ''
        if not celular:
            return request.redirect('/socios')
        valores = {'ficha': ficha, 'celular': celular, 'meses': MESES, 'datos': datos}
        try:
            if not datos.get('acepta'):
                raise UserError('Para entrar al programa hay que aceptar los términos.')
            if ficha.dcasa_socio_estado != 'activo':
                raise UserError('Tu cuenta está suspendida. Escríbenos por WhatsApp y lo revisamos.')
            pin = self._pin_nuevo(datos, celular)
            cumple = self._cumple(datos)
        except UserError as error:
            valores['error'] = error.args[0]
            return self._render('dcasa_socios.socios_activar', valores)
        cambios = {
            'dcasa_terminos_version': R.VERSION_TERMINOS,
            'dcasa_terminos_aceptados_en': fields.Datetime.now(),
        }
        if not ficha.dcasa_celular:
            cambios['dcasa_celular'] = celular
        if cumple and not ficha.dcasa_cumple:
            cambios['dcasa_cumple'] = cumple
        ficha.write(cambios)
        ficha._dcasa_asegurar_ficha(creado_por='tienda')
        try:
            ficha._dcasa_guardar_pin(pin)
        except R.FaltaConfigurar:
            valores['error'] = 'El programa aún no está listo. Escríbenos por WhatsApp.'
            return self._render('dcasa_socios.socios_activar', valores)
        self._avisar('¡Listo! Ya eres socio de D’CASA. Tus compras en la tienda suman puntos aquí.', 'success')
        return request.redirect('/socios/cuenta')

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
        Canje = env['dcasa.canje'].sudo()
        return self._render('dcasa_socios.socios_cuenta', {
            'socio': socio,
            'saldo': saldo,
            'movimientos': env['dcasa.movimiento'].sudo().search([('partner_id', '=', socio.id)], limit=30),
            'premios': env['dcasa.premio']._catalogo(),
            'canjes': Canje.search([('partner_id', '=', socio.id), ('estado', '=', 'solicitado')]),
            'historial': Canje.search([('partner_id', '=', socio.id), ('estado', '!=', 'solicitado')], limit=10),
            'ahijados': socio.dcasa_ahijado_ids.sudo().filtered('active'),
            'link': link,
            'whatsapp': f'https://wa.me/?text={quote(texto)}',
            'qr': f'/report/barcode/?barcode_type=QR&value={quote(link, safe="")}&width=220&height=220',
        })

    @http.route('/socios/premios', type='http', auth='public', website=True, sitemap=True)
    def premios(self, **kwargs):
        """El catálogo de premios, público: lo que edita Gerencia en Socios > Premios. Pedir exige sesión."""
        socio = self._socio()
        Canje = request.env['dcasa.canje'].sudo()
        return self._render('dcasa_socios.socios_premios', {
            'socio': socio,
            'saldo': socio.dcasa_saldo if socio else 0,
            'premios': request.env['dcasa.premio']._catalogo(),
            'canjes': Canje.search([('partner_id', '=', socio.id), ('estado', '=', 'solicitado')]) if socio else Canje,
            'historial': Canje.search([('partner_id', '=', socio.id), ('estado', '!=', 'solicitado')], limit=10)
            if socio else Canje,
        })

    @http.route('/socios/canjear', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def canjear(self, premio_id=None, volver='cuenta', **kwargs):
        socio = self._socio()
        if not socio:
            return request.redirect('/socios')
        premio = request.env['dcasa.premio'].sudo().browse(int(premio_id or 0)).exists()
        try:
            if premio.libre:
                raise UserError('Ese premio no se puede pedir desde aquí.')
            canje = request.env['dcasa.canje']._pedir(socio, premio)
        except UserError as error:
            self._avisar(error.args[0], 'danger')
        else:
            horas = R.cargar_reglas()['canje']['vigenciaDelCodigoHoras']
            donde = 'Recógelo en la tienda' if canje.premio_tipo == 'producto' else 'Enséñalo al pagar en la tienda'
            self._avisar(f'Tu código es {canje.codigo}. {donde} en las próximas {horas} horas.', 'success')
        return request.redirect(VOLVER.get(volver, VOLVER['cuenta']))

    @http.route('/socios/canjes/<string:codigo>/cancelar', type='http', auth='public', website=True,
                methods=['POST'], sitemap=False)
    def cancelar_canje(self, codigo, volver='cuenta', **kwargs):
        socio = self._socio()
        if not socio:
            return request.redirect('/socios')
        canje = request.env['dcasa.canje'].sudo().search([
            ('codigo', '=', R.codigo_normal(codigo)), ('partner_id', '=', socio.id), ('estado', '=', 'solicitado'),
        ], limit=1)
        if canje and canje.origen == 'web':
            self._avisar('Ese premio está en tu carrito de la tienda web: quítalo desde el carrito.', 'danger')
        elif canje:
            canje._cancelar_por_socio()
            self._avisar('Listo: cancelaste el premio y tus puntos volvieron.', 'success')
        return request.redirect(VOLVER.get(volver, VOLVER['cuenta']))

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
        if self._socio_por_pin() or not self._socio_de_la_tienda():
            self._iniciar_sesion(socio)
        self._avisar('Tu PIN nuevo quedó guardado.', 'success')
        return request.redirect('/socios/cuenta')

    @http.route('/socios/terminos', type='http', auth='public', website=True, sitemap=True)
    def terminos(self, **kwargs):
        return self._render('dcasa_socios.socios_terminos')

    # ------------------------------------------------------------------------
    # Puntos en el carrito de la tienda web
    # ------------------------------------------------------------------------

    @http.route('/socios/carrito/usar', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def carrito_usar(self, premio_id=None, puntos=None, **kwargs):
        """«Usar mis puntos» en el carrito: pide el canje y lo aplica a la orden. El que paga es el
        usuario de la tienda con sesión (``request.cart`` es su carrito)."""
        orden = request.cart
        if not orden:
            self._avisar('Tu carrito está vacío.', 'danger')
            return request.redirect('/shop/cart')
        Premio = request.env['dcasa.premio'].sudo()
        premio = Premio.browse(int(premio_id)).exists() if (premio_id or '').strip().isdigit() else Premio
        cuantos = int(puntos) if (puntos or '').strip().isdigit() else None
        try:
            canje = orden._dcasa_usar_puntos_web(premio=premio, puntos=cuantos)
        except UserError as error:
            self._avisar(error.args[0], 'danger')
        else:
            self._avisar(f'Listo: {R.como_dolares(R.a_centavos(canje.valor))} de descuento con '
                         f'{R.como_puntos(canje.puntos)} puntos. Si quitas el premio, los puntos vuelven.',
                         'success')
        return request.redirect('/shop/cart')

    @http.route('/socios/carrito/quitar', type='http', auth='public', website=True, methods=['POST'], sitemap=False)
    def carrito_quitar(self, **kwargs):
        orden = request.cart
        if orden and orden._dcasa_lineas_premio():
            orden._dcasa_quitar_puntos_web()
            self._avisar('Quitaste el premio del carrito: tus puntos volvieron.', 'success')
        return request.redirect('/shop/cart')
