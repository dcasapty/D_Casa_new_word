"""Utilidades comunes de las herramientas de Brian (resolver referencias humanas, formatos, periodos).

Las herramientas reciben lo que diría una persona: «colchón queen», «SOF-001», «6123-4567»,
«INV/2026/00012», «la cotización de Juan». Aquí se convierte eso en UN registro, o en un
``BrianError`` que lista las opciones para que el modelo pregunte o reintente.

Y se devuelven cifras ya formateadas (``$1,234.56``, ``30/09/2026``): los modelos pequeños
no deben hacer cuentas ni formatear, solo leer.
"""
import re
from datetime import date, datetime, timedelta

from odoo import api, fields, models

from .registro import BrianError, normalizar

MAX_FILAS = 20
MAX_OPCIONES = 8

PERIODOS = ['hoy', 'ayer', 'esta_semana', 'semana_pasada', 'este_mes', 'mes_pasado', 'este_anio']
PARAM_PERIODO = {
    'type': 'string', 'enum': PERIODOS,
    'description': 'Periodo, p. ej. «este_mes». Si das «desde»/«hasta», se ignora.',
}
PARAM_DESDE = {'type': 'string', 'description': 'Fecha inicial dd/mm/aaaa, p. ej. «01/09/2026».'}
PARAM_HASTA = {'type': 'string', 'description': 'Fecha final dd/mm/aaaa, p. ej. «30/09/2026».'}
PARAM_LIMITE = {'type': 'integer', 'description': f'Cuántas filas como máximo (1 a {MAX_FILAS}). Por defecto 10.'}
PARAM_LINEAS = {'type': 'string',
                'description': 'Varios productos, separados por «;»: código o nombre, «x» cantidad y opcional '
                               '«@» precio, p. ej. «SOF-001 x 2; MES-003 x 1 @ 99».'}


def moneda(monto):
    """1234.5 → «$1,234.50»; -12 → «-$12.00». (USD, la moneda de D'CASA.)"""
    monto = round(float(monto or 0.0), 2)
    signo = '-' if monto < 0 else ''
    return f'{signo}${abs(monto):,.2f}'


def fecha(valor):
    """date/datetime/'aaaa-mm-dd' → «dd/mm/aaaa». Vacío → ''."""
    if not valor:
        return ''
    if isinstance(valor, str):
        valor = fields.Date.to_date(valor[:10])
    return valor.strftime('%d/%m/%Y')


def cantidad(valor):
    """Se venden camas enteras: 2.0 → 2; 1.5 → 1.5."""
    valor = float(valor or 0.0)
    return int(valor) if valor.is_integer() else round(valor, 2)


def plural(n, singular, plural_=None):
    return f'{n} {singular if n == 1 else (plural_ or singular + "s")}'


def leer_fecha(texto, nombre='fecha'):
    """«30/09/2026», «2026-09-30», «hoy» o «ayer» → date. Si no se entiende, BrianError."""
    if isinstance(texto, (date, datetime)):
        return texto if isinstance(texto, date) and not isinstance(texto, datetime) else texto.date()
    texto = (texto or '').strip().lower()
    if not texto:
        return None
    hoy = date.today()
    if texto == 'hoy':
        return hoy
    if texto == 'ayer':
        return hoy - timedelta(days=1)
    for formato in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise BrianError(f'No entendí la {nombre} «{texto}». Escríbela como dd/mm/aaaa, p. ej. 30/09/2026.')


MAX_LINEAS = 30
_LINEA = re.compile(
    r'^(?P<ref>.+?)'
    r'(?:(?:\s+(?:x|cant(?:idad)?\.?:?)|\s*[×*])\s*(?P<cant>\d+(?:[.,]\d+)?))?'
    r'(?:\s*(?:@|a\s+\$|\$|precio:?|costo:?)\s*\$?\s*(?P<precio>\d[\d,]*(?:\.\d+)?))?\s*$',
    re.IGNORECASE)


def leer_lineas(texto):
    """«SOF-001 x 2 @ 150; colchón queen x 1» → [('SOF-001', 2.0, 150.0), ('colchón queen', 1.0, None)].

    Una línea por «;» o salto de línea. Cantidad con «x», «×» o «*» (por defecto 1); precio
    opcional con «@», «$» o «precio». Lo que no se entiende da ``BrianError`` con la línea.
    """
    partes = [p.strip(' -•\t') for p in re.split(r'[;\n]+', str(texto or '')) if p.strip(' -•\t')]
    if not partes:
        raise BrianError('No entendí los productos. Escríbelos así: «SOF-001 x 2; MES-003 x 1».')
    if len(partes) > MAX_LINEAS:
        raise BrianError(f'Son {len(partes)} líneas: el máximo por vez es {MAX_LINEAS}. Pártelo en dos.')
    lineas = []
    for parte in partes:
        encontrado = _LINEA.match(parte)
        if not encontrado or not encontrado.group('ref').strip():
            raise BrianError(f'No entendí la línea «{parte}». Escríbela como «código x cantidad», '
                             'p. ej. «SOF-001 x 2».')
        cant = float(encontrado.group('cant').replace(',', '.')) if encontrado.group('cant') else 1.0
        precio = encontrado.group('precio')
        precio = float(precio.replace(',', '')) if precio else None
        if cant <= 0:
            raise BrianError(f'La cantidad de «{parte}» tiene que ser mayor que cero.')
        lineas.append((encontrado.group('ref').strip(), cant, precio))
    return lineas


def normalizar_texto(texto):
    return normalizar(texto).strip()


def limite(valor, defecto=10):
    try:
        valor = int(valor or defecto)
    except (TypeError, ValueError):
        valor = defecto
    return max(1, min(valor, MAX_FILAS))


class BrianHerramientasComun(models.AbstractModel):
    _inherit = 'brian.herramientas'

    # ------------------------------------------------------------------
    # Fechas y periodos (hora de Panamá)
    # ------------------------------------------------------------------

    @api.model
    def _b_hoy(self):
        return fields.Date.context_today(self)

    @api.model
    def _b_rango(self, periodo=None, desde=None, hasta=None, defecto='este_mes'):
        """(desde, hasta, etiqueta) como fechas. «desde/hasta» mandan sobre «periodo»."""
        hoy = self._b_hoy()
        if desde or hasta:
            inicio = leer_fecha(desde, 'fecha inicial') or hoy.replace(day=1)
            fin = leer_fecha(hasta, 'fecha final') or hoy
            if inicio > fin:
                raise BrianError('La fecha inicial es posterior a la final. Revisa «desde» y «hasta».')
            return inicio, fin, f'del {fecha(inicio)} al {fecha(fin)}'
        periodo = periodo or defecto
        if periodo not in PERIODOS:
            raise BrianError(f'Periodo desconocido «{periodo}». Usa uno de: {", ".join(PERIODOS)}.')
        lunes = hoy - timedelta(days=hoy.weekday())
        inicio_mes = hoy.replace(day=1)
        fin_mes_pasado = inicio_mes - timedelta(days=1)
        rangos = {
            'hoy': (hoy, hoy, 'hoy'),
            'ayer': (hoy - timedelta(days=1), hoy - timedelta(days=1), 'ayer'),
            'esta_semana': (lunes, hoy, 'esta semana'),
            'semana_pasada': (lunes - timedelta(days=7), lunes - timedelta(days=1), 'la semana pasada'),
            'este_mes': (inicio_mes, hoy, 'este mes'),
            'mes_pasado': (fin_mes_pasado.replace(day=1), fin_mes_pasado, 'el mes pasado'),
            'este_anio': (hoy.replace(month=1, day=1), hoy, 'este año'),
        }
        return rangos[periodo]

    @api.model
    def _b_limites(self, inicio, fin):
        """Días de Panamá [inicio, fin] → (desde, hasta) en UTC para campos Datetime (hasta exclusivo)."""
        tablero = self.env['dcasa.tablero']
        return tablero._limites_del_dia(inicio)[0], tablero._limites_del_dia(fin)[1]

    # ------------------------------------------------------------------
    # Resolver referencias humanas
    # ------------------------------------------------------------------

    @api.model
    def _b_ambiguo(self, registros, texto, etiqueta, describir=None):
        describir = describir or (lambda r: r.display_name)
        opciones = '; '.join(describir(r) for r in registros[:MAX_OPCIONES])
        mas = ' (y más)' if len(registros) > MAX_OPCIONES else ''
        raise BrianError(
            f'Hay varios {etiqueta}s que coinciden con «{texto}»: {opciones}{mas}. '
            f'Dime cuál, con el nombre completo o el código.')

    @api.model
    def _b_resolver(self, modelo, texto, etiqueta, exactos=(), dominio=None, describir=None, buscar=None):
        """Un solo registro a partir de lo que escribió la persona.

        1. Coincidencia exacta (sin mayúsculas) en ``exactos`` (código, número, RUC…).
        2. Búsqueda por nombre (``display_name`` ilike: usa las búsquedas de D'CASA por varias
           palabras y por celular). Si el texto coincide exacto con un nombre, gana ese.
        Ninguno o varios → ``BrianError`` útil.
        """
        texto = str(texto or '').strip()
        if not texto:
            raise BrianError(f'Dime qué {etiqueta} (nombre o código).')
        Modelo = self.env[modelo]
        dominio = list(dominio or [])
        for campo in exactos:
            encontrados = Modelo.search(dominio + [(campo, '=ilike', texto)], limit=MAX_OPCIONES + 1)
            if len(encontrados) == 1:
                return encontrados
            if encontrados:
                self._b_ambiguo(encontrados, texto, etiqueta, describir)
        encontrados = Modelo.search(dominio + (buscar or [('display_name', 'ilike', texto)]),
                                    limit=MAX_OPCIONES * 5)
        if len(encontrados) == 1:
            return encontrados
        if not encontrados:
            raise BrianError(
                f'No encontré ningún {etiqueta} con «{texto}». Prueba con otra palabra, el código o búscalo primero.')
        exacto = encontrados.filtered(lambda r: (r.display_name or '').strip().lower() == texto.lower())
        if len(exacto) == 1:
            return exacto
        self._b_ambiguo(encontrados, texto, etiqueta, describir)

    @api.model
    def _b_producto(self, texto):
        """La variante vendible (product.product): «SOF-001», «colchón ortopédico queen»."""
        return self._b_resolver('product.product', texto, 'producto', exactos=('default_code', 'barcode'))

    @api.model
    def _b_lineas_productos(self, texto):
        """[(variante, cantidad, precio|None)] de «SOF-001 x 2; MES-003 x 1 @ 99». Si alguna línea no
        se resuelve, un solo BrianError con TODAS las que fallaron (para corregir de una vez)."""
        resultado, errores = [], []
        for referencia, cant, precio in leer_lineas(texto):
            try:
                resultado.append((self._b_producto(referencia), cant, precio))
            except BrianError as error:
                errores.append(f'«{referencia}»: {error}')
        if errores:
            raise BrianError('No pude resolver estas líneas (no hice nada): ' + ' | '.join(errores))
        return resultado

    @api.model
    def _b_plantilla(self, texto):
        """El producto como ficha (product.template), aunque den el código de una variante."""
        texto = str(texto or '').strip()
        variante = self.env['product.product'].search(
            ['|', ('default_code', '=ilike', texto), ('barcode', '=ilike', texto)], limit=2)
        if len(variante) == 1:
            return variante.product_tmpl_id
        return self._b_resolver('product.template', texto, 'producto', exactos=('default_code',))

    @api.model
    def _b_contacto(self, texto, etiqueta='cliente'):
        """Cliente o proveedor por nombre, celular, RUC/cédula o código de socio."""
        texto = str(texto or '').strip()
        digitos = re.sub(r'\D', '', texto)
        dominio = [('parent_id', '=', False)]
        if len(digitos) >= 7 and len(digitos) >= len(texto.replace(' ', '').replace('+', '')) - 2:
            celular = digitos[-8:]
            encontrados = self.env['res.partner'].search(dominio + [
                '|', ('dcasa_telefono_digitos', '=', celular), ('dcasa_celular', '=', celular)], limit=MAX_OPCIONES)
            if len(encontrados) == 1:
                return encontrados
            if encontrados:
                self._b_ambiguo(encontrados, texto, etiqueta, self._b_describir_contacto)
        return self._b_resolver('res.partner', texto, etiqueta, exactos=('vat', 'ref', 'dcasa_socio_codigo'),
                                dominio=dominio, describir=self._b_describir_contacto)

    @api.model
    def _b_describir_contacto(self, partner):
        extra = partner.phone or partner.vat or partner.email
        return f'{partner.display_name} ({extra})' if extra else partner.display_name

    @api.model
    def _b_venta(self, texto):
        """Venta o cotización por número («S00012») o por cliente («la de Juan Pérez»)."""
        return self._b_resolver(
            'sale.order', texto, 'venta', exactos=('name', 'client_order_ref'),
            buscar=['|', ('name', 'ilike', texto), ('partner_id', 'ilike', texto)],
            describir=lambda o: f'{o.name} — {o.partner_id.display_name} — {moneda(o.amount_total)} '
                                f'({self._b_estado_venta(o)})')

    @api.model
    def _b_factura(self, texto, dominio=None):
        """Factura por número («INV/2026/00012»), borrador («#45»), referencia o tercero."""
        texto = str(texto or '').strip()
        dominio = list(dominio or []) + [('move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund'))]
        borrador = re.fullmatch(r'(?:borrador\s*)?#\s*(\d+)', texto, re.IGNORECASE)
        if borrador:
            factura = self.env['account.move'].search(dominio + [('id', '=', int(borrador.group(1)))])
            if factura:
                return factura
        return self._b_resolver(
            'account.move', texto, 'factura', exactos=('name', 'ref'), dominio=dominio,
            buscar=['|', '|', ('name', 'ilike', texto), ('ref', 'ilike', texto), ('partner_id', 'ilike', texto)],
            describir=lambda f: f'{self._b_numero_factura(f)} — {f.partner_id.display_name} — '
                                f'{moneda(f.amount_total)} ({self._b_estado_factura(f)})')

    @api.model
    def _b_usuario(self, texto):
        return self._b_resolver('res.users', texto, 'usuario', exactos=('login', 'email'),
                                dominio=[('share', '=', False)],
                                describir=lambda u: f'{u.name} ({u.login})')

    # ------------------------------------------------------------------
    # Cómo se nombran las cosas
    # ------------------------------------------------------------------

    @api.model
    def _b_estado_venta(self, orden):
        return {'draft': 'cotización', 'sent': 'cotización enviada', 'sale': 'venta confirmada',
                'cancel': 'cancelada'}.get(orden.state, orden.state)

    @api.model
    def _b_numero_factura(self, factura):
        return factura.name if factura.name and factura.name != '/' else f'Borrador #{factura.id}'

    @api.model
    def _b_estado_factura(self, factura):
        if factura.state == 'draft':
            return 'borrador'
        if factura.state == 'cancel':
            return 'cancelada'
        return {'not_paid': 'publicada, sin pagar', 'partial': 'pagada en parte', 'paid': 'pagada',
                'in_payment': 'en proceso de pago', 'reversed': 'revertida con nota de crédito',
                'blocked': 'bloqueada'}.get(factura.payment_state, 'publicada')

    @api.model
    def _b_tipo_factura(self, factura):
        return {'out_invoice': 'factura de cliente', 'out_refund': 'nota de crédito de cliente',
                'in_invoice': 'factura de proveedor', 'in_refund': 'nota de crédito de proveedor'
                }.get(factura.move_type, factura.move_type)

    # ------------------------------------------------------------------
    # Política (reglas que no dependen de lo que pida el modelo)
    # ------------------------------------------------------------------

    @api.model
    def _b_politica(self):
        return self.env['brian.politica'] if 'brian.politica' in self.env else None

    @api.model
    def _b_exigir_factura_borrador(self, factura):
        """Una factura publicada, pagada o cancelada no se edita: la corrige una persona."""
        politica = self._b_politica()
        if politica is not None and hasattr(politica, 'puede_editar_factura'):
            politica.puede_editar_factura(factura)
        if factura.state != 'draft':
            raise BrianError(
                f'La {self._b_tipo_factura(factura)} {self._b_numero_factura(factura)} está '
                f'{self._b_estado_factura(factura)}: ya no se edita. Corregirla requiere intervención humana '
                f'con una nota de crédito (o un asiento contrario) desde Contabilidad.')

    @api.model
    def _b_proteger_usuario(self, usuario):
        """Ni el administrador, ni OdooBot/superusuario, ni quien conversa."""
        politica = self._b_politica()
        if politica is not None and hasattr(politica, 'proteger_usuario'):
            politica.proteger_usuario(usuario)
        protegidos = (self.env.ref('base.user_admin', raise_if_not_found=False)
                      | self.env.ref('base.user_root', raise_if_not_found=False))
        if usuario in protegidos:
            raise BrianError('Al administrador principal no lo toco: ni su rol, ni su acceso. '
                             'Si hace falta, lo cambia una persona desde Ajustes.')
        if usuario == self.env.user:
            raise BrianError('No puedo cambiar tu propio usuario (rol ni acceso). Pídeselo a otro administrador.')
        if usuario.has_group('base.group_system') and not self.env.user.has_group('base.group_system'):
            raise BrianError(f'{usuario.name} es administrador del sistema: solo otro administrador puede cambiarlo.')
