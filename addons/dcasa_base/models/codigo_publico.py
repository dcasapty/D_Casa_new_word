"""Código público del producto: el que ve el cliente (``DC-K7M4PX``).

D'CASA maneja dos códigos distintos por producto y no se mezclan:

* **Referencia interna** (``default_code``): la del proveedor. Es de la casa: sirve para pedir, contar y
  encontrar el producto en Odoo, y el cliente no tiene por qué conocerla.
* **Código público** (``dcasa_codigo_publico``): lo asigna el sistema solo, a cualquier producto nuevo (también
  archivados y combos). Es lo que el cliente ve y dice por WhatsApp: en la ficha de la tienda, en los mensajes de
  Juan y, más adelante, en el QR de las cotizaciones y etiquetas. No es el código de barras de las etiquetas del
  rollo (``barcode``, ``DC0001``…, ver docs/BARRAS.md): son campos distintos y el formato no se puede confundir.

Formato: ``DC-`` + 6 símbolos al azar (``secrets``) de un alfabeto sin ambigüedades:

* Sin ``0 O 1 I L`` (se leen como otra letra o número).
* Sin vocales: con 6 símbolos al azar y vocales saldrían palabras (y alguna sería ofensiva); sin vocales no se
  forma ninguna.
* Siempre al menos una letra: así ``DC-234567`` no existe y, quitando el guion, jamás se parece a una etiqueta
  numerada del rollo (``DC`` + solo números).

Cada código es de un solo producto (``UNIQUE``, también entre archivados) y **no cambia nunca**: el cliente ya pudo
verlo, guardarlo o imprimirlo. Solo un administrador puede regenerarlo, con una acción explícita que deja nota.
"""
import re
import secrets

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain

PREFIJO = 'DC-'
ALFABETO = '23456789BCDFGHJKMNPQRSTVWXYZ'
LARGO = 6
PATRON = re.compile(rf'^{PREFIJO}[{ALFABETO}]{{{LARGO}}}$')
PATRON_SQL = f'^{PREFIJO}[{ALFABETO}]{{{LARGO}}}$'
MINIMO_PARCIAL = 4          # una búsqueda por pedazos del código necesita al menos 4 símbolos
INTENTOS_AL_CREAR = 5       # veces que se vuelve a sortear si otro proceso tomó el mismo código a la vez
CLAVE_PASE = 'dcasa_pase_codigo_publico'
GRUPO_QUE_REGENERA = 'base.group_system'
NO_ALFANUMERICO = re.compile(r'[^0-9A-Za-z]')


class _Pase:
    """Contraseña interna para que solo el servidor cambie un código: un valor del contexto que llegue por RPC es
    texto o número, nunca esta clase."""

    def __repr__(self):
        return '<pase del código público>'


PASE = _Pase()


def generar_codigo_publico():
    """Un código nuevo al azar (no mira si ya existe: de eso se encarga ``_dcasa_codigos_libres``)."""
    while True:
        cuerpo = ''.join(secrets.choice(ALFABETO) for _ in range(LARGO))
        if not cuerpo.isdigit():
            return PREFIJO + cuerpo


def es_codigo_publico(texto):
    return isinstance(texto, str) and bool(PATRON.match(texto))


def normalizar_codigo_publico(texto):
    """«dc-k7m4px», «DC K7M4PX» o «DCK7M4PX» → «DC-K7M4PX»; ``None`` si no es un código público completo."""
    limpio = NO_ALFANUMERICO.sub('', texto or '').upper() if isinstance(texto, str) else ''
    codigo = PREFIJO + limpio[2:] if limpio.startswith('DC') else ''
    return codigo if es_codigo_publico(codigo) else None


def patron_de_busqueda(texto):
    """Lo que se busca dentro de los códigos cuando alguien escribe solo un pedazo («K7M4», «dc-k7»); ``None`` si es
    muy corto para no traer medio catálogo."""
    limpio = NO_ALFANUMERICO.sub('', texto or '').upper() if isinstance(texto, str) else ''
    if len(limpio) < MINIMO_PARCIAL:
        return None
    return PREFIJO + limpio[2:] if limpio.startswith('DC') else limpio


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    dcasa_codigo_publico = fields.Char(
        string='Código público', readonly=True, copy=False,
        help='El código que ve el cliente (DC-K7M4PX). Lo pone el sistema solo al crear el producto y no cambia: '
             'el cliente ya pudo verlo o guardarlo. Es distinto de la referencia interna (la del proveedor), que el '
             'cliente no ve. Se busca igual que el nombre.')

    _dcasa_codigo_publico_unico = models.Constraint(
        'UNIQUE(dcasa_codigo_publico)', 'Ese código público ya es de otro producto.')
    _dcasa_codigo_publico_forma = models.Constraint(
        f"CHECK(dcasa_codigo_publico IS NULL OR dcasa_codigo_publico ~ '{PATRON_SQL}')",
        'El código público tiene la forma DC- y 6 símbolos (letras sin vocales ni L, y números del 2 al 9).')

    # ------------------------------------------------------------------
    # Sorteo
    # ------------------------------------------------------------------
    @api.model
    def _dcasa_codigos_libres(self, cantidad, reservados=()):
        """``cantidad`` códigos distintos entre sí y de todos los que ya existen, también los de productos archivados
        y de otras empresas (por eso se pregunta a la base y no al ORM, que filtra por empresa y archivo)."""
        reservados = set(reservados)
        self.env['product.template'].flush_model(['dcasa_codigo_publico'])
        nuevos = []
        while len(nuevos) < cantidad:
            candidatos = set()
            while len(candidatos) < cantidad - len(nuevos):
                candidatos.add(generar_codigo_publico())
            candidatos -= reservados
            if candidatos:
                self.env.cr.execute(
                    'SELECT dcasa_codigo_publico FROM product_template WHERE dcasa_codigo_publico = ANY(%s)',
                    [list(candidatos)])
                candidatos -= {fila[0] for fila in self.env.cr.fetchall()}
            reservados |= candidatos
            nuevos.extend(candidatos)
        return nuevos

    # ------------------------------------------------------------------
    # Crear: ningún producto nuevo se queda sin código
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        dados = {vals['dcasa_codigo_publico'] for vals in vals_list if vals.get('dcasa_codigo_publico')}
        if not all(es_codigo_publico(codigo) for codigo in dados):
            raise ValidationError(self.env._(
                'El código público tiene la forma DC-K7M4PX. Déjalo vacío y el sistema le pone uno.'))
        if dados:
            self.env.cr.execute(
                'SELECT dcasa_codigo_publico FROM product_template WHERE dcasa_codigo_publico = ANY(%s)', [list(dados)])
            if self.env.cr.fetchone():
                raise ValidationError(self.env._('Ese código público ya es de otro producto.'))
        sin_codigo = [vals for vals in vals_list if not vals.get('dcasa_codigo_publico')]
        for _intento in range(INTENTOS_AL_CREAR):
            for vals, codigo in zip(
                    sin_codigo, self._dcasa_codigos_libres(len(sin_codigo), reservados=dados), strict=True):
                vals['dcasa_codigo_publico'] = codigo
            try:
                with self.env.cr.savepoint():
                    return super().create(vals_list)
            except Exception as error:   # noqa: BLE001 — solo se atiende el choque de códigos; lo demás sigue su camino
                if not self._dcasa_es_choque_de_codigo(error) or not sin_codigo:
                    raise
                # Otra transacción tomó el mismo código a la vez: se sortean otros y se vuelve a intentar.
                for vals in sin_codigo:
                    vals.pop('dcasa_codigo_publico', None)
        raise UserError(self.env._('No pude asignar un código público libre. Vuelve a intentarlo.'))

    @staticmethod
    def _dcasa_es_choque_de_codigo(error):
        diag = getattr(error, 'diag', None)
        return 'dcasa_codigo_publico' in str(getattr(diag, 'constraint_name', '') or '')

    # ------------------------------------------------------------------
    # Escribir: un código ya dado no cambia
    # ------------------------------------------------------------------
    def write(self, vals):
        if 'dcasa_codigo_publico' in vals and self.env.context.get(CLAVE_PASE) is not PASE:
            nuevo = vals['dcasa_codigo_publico'] or False
            for plantilla in self:
                actual = plantilla.dcasa_codigo_publico
                if actual and actual != nuevo:
                    raise UserError(self.env._(
                        'El código público %(codigo)s de «%(producto)s» ya lo pudo ver el cliente y no se cambia. Si '
                        'de verdad hace falta otro, un administrador usa «Regenerar código público» en la ficha.',
                        codigo=actual, producto=plantilla.name))
            if nuevo and not es_codigo_publico(nuevo):
                raise ValidationError(self.env._(
                    'El código público tiene la forma DC-K7M4PX. Déjalo vacío y el sistema le pone uno.'))
        return super().write(vals)

    def action_dcasa_regenerar_codigo_publico(self):
        """Solo un administrador. El código viejo deja de existir: cualquier cliente que lo tenga ya no lo encuentra,
        así que queda anotado en el historial del producto."""
        if not self.env.user.has_group(GRUPO_QUE_REGENERA):
            raise AccessError(self.env._('Solo un administrador puede regenerar el código público de un producto.'))
        self.check_access('write')
        for plantilla in self:
            viejo = plantilla.dcasa_codigo_publico
            nuevo = self._dcasa_codigos_libres(1)[0]
            plantilla.with_context(**{CLAVE_PASE: PASE}).write({'dcasa_codigo_publico': nuevo})
            plantilla.message_post(
                body=self.env._('Código público regenerado por %(quien)s: %(viejo)s → %(nuevo)s.',
                                quien=self.env.user.name, viejo=viejo or self.env._('(sin código)'), nuevo=nuevo))
        return True

    @api.model
    def _dcasa_rellenar_codigos_publicos(self, lote=500):
        """Le da código a los productos que no tienen (también archivados y de otras empresas). Seguro de repetir: no
        toca los que ya tienen. Va por lotes, vuelve a sortear si un código choca y no cambia la fecha de
        modificación de los productos (las fotos del sitio no se vuelven a pedir). Devuelve cuántos rellenó."""
        cr = self.env.cr
        self.env['product.template'].flush_model(['dcasa_codigo_publico'])
        cr.execute('SELECT id FROM product_template WHERE dcasa_codigo_publico IS NULL ORDER BY id')
        pendientes = [fila[0] for fila in cr.fetchall()]
        total = 0
        for inicio in range(0, len(pendientes), lote):
            ids = pendientes[inicio:inicio + lote]
            for _intento in range(INTENTOS_AL_CREAR):
                codigos = self._dcasa_codigos_libres(len(ids))
                try:
                    with cr.savepoint(flush=False):
                        cr.execute(
                            'UPDATE product_template AS t SET dcasa_codigo_publico = v.codigo '
                            'FROM (SELECT unnest(%s::int[]) AS id, unnest(%s::text[]) AS codigo) AS v '
                            'WHERE t.id = v.id AND t.dcasa_codigo_publico IS NULL', [ids, codigos])
                        total += cr.rowcount
                    break
                except Exception as error:   # noqa: BLE001 — solo el choque de códigos se repite
                    if not self._dcasa_es_choque_de_codigo(error):
                        raise
            else:
                raise UserError(self.env._('No pude asignar códigos públicos libres. Vuelve a correrlo.'))
        self.env['product.template'].invalidate_model(['dcasa_codigo_publico'])
        return total

    def _dcasa_url_codigo_publico(self):
        """La dirección que debe llevar el QR de un producto: ``https://…/codigo/DC-K7M4PX``. Abre la ficha del
        producto en la tienda (si está publicado; si no, la tienda). Vacío si el producto aún no tiene código."""
        self.ensure_one()
        if not self.dcasa_codigo_publico:
            return ''
        base = (self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')
        return f'{base}/codigo/{self.dcasa_codigo_publico}'

    # ------------------------------------------------------------------
    # Buscar
    # ------------------------------------------------------------------
    @api.model
    def _dcasa_dominio_codigo_publico(self, operator, value):
        """Dominio que encuentra un producto por su código público, o ``None`` si lo escrito no parece un código.

        El código completo se encuentra igual con o sin guion y en minúsculas; un pedazo («K7M4») también."""
        if not isinstance(value, str) or operator in Domain.NEGATIVE_OPERATORS:
            return None
        completo = normalizar_codigo_publico(value)
        if completo and operator in ('=', '=ilike', 'ilike', 'like', '=like'):
            return Domain('dcasa_codigo_publico', '=', completo)
        if operator in ('ilike', 'like'):
            patron = patron_de_busqueda(value)
            if patron:
                return Domain('dcasa_codigo_publico', 'ilike', patron)
        return None

    @api.model
    def _search_display_name(self, operator, value):
        dominio = super()._search_display_name(operator, value)
        por_codigo = self._dcasa_dominio_codigo_publico(operator, value)
        return Domain.OR([dominio, por_codigo]) if por_codigo is not None else dominio


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # ``dcasa_codigo_publico`` ya está aquí: product.product hereda (_inherits) todos los campos de la plantilla,
    # así que la variante muestra y busca el código de su producto.

    @api.model
    def _search_display_name(self, operator, value):
        dominio = super()._search_display_name(operator, value)
        por_codigo = self.env['product.template']._dcasa_dominio_codigo_publico(operator, value)
        return Domain.OR([dominio, por_codigo]) if por_codigo is not None else dominio
