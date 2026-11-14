"""Opiniones de los productos: reales, de quien lo compró y lo pagó, y publicadas solo si Gerencia las aprueba.

Reglas (lote 2 de la web, aprobado por la dueña):

* Opina solo el cliente con sesión (Mi cuenta: cuenta de la tienda o celular + PIN), y solo de un producto que está en
  una factura suya publicada y PAGADA por completo (``payment_state`` «paid» o «in_payment»; un abono a medias no).
  Una opinión por cliente y producto. El anónimo no opina.
* Nadie la escribe a mano: ``create`` solo con ``sudo`` desde ``_dcasa_crear_del_cliente`` (que comprueba todo lo de
  arriba). Lo que dijo el cliente (estrellas, texto, quién, qué) no se cambia después, ni Gerencia.
* Se publica con «Publicar» y se esconde con «No publicar» (Gerencia o un administrador, comprobado en el servidor).
  En la ficha y en los datos para Google (``aggregateRating``) cuentan SOLO las publicadas: cero publicadas = no hay
  estrellas ni ``aggregateRating``.
* En la ficha sale el primer nombre y la inicial del apellido; nunca el nombre completo, el celular ni el correo.
* Al publicar o esconder una, la ficha guardada en el borde se renueva (``dcasa_tienda_borde``, si está instalado).

Ningún usuario portal ni el público tiene permiso sobre el modelo (ir.model.access): el sitio lee con ``sudo`` y
siempre filtrando por producto y estado, o por la ficha del cliente con sesión.
"""
import psycopg2

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain

ESTADOS = [('pendiente', 'Por revisar'), ('aprobada', 'Publicada'), ('rechazada', 'No publicada')]
PAGADAS = ('paid', 'in_payment')
LARGO_MAXIMO = 1000
MAXIMO_EN_FICHA = 20
MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre')
GRUPOS_REVISORES = ('dcasa_base.group_gerencia', 'base.group_system')


def nombre_publico(nombre):
    """«LUCÍA MARTÍNEZ PÉREZ» → «Lucía M.»; «Ana» → «Ana». Nunca el nombre completo."""
    partes = (nombre or '').split()
    if not partes:
        return 'Cliente'
    primero = partes[0][:1].upper() + partes[0][1:].lower()
    return f'{primero} {partes[1][:1].upper()}.' if len(partes) > 1 else primero


def limpiar_texto(texto):
    """El texto del cliente: sin caracteres de control (salvo saltos de línea) y sin espacios de sobra."""
    texto = ''.join(c for c in (texto or '') if c in '\n' or c.isprintable())
    lineas = [' '.join(linea.split()) for linea in texto.replace('\r', '').split('\n')]
    return '\n'.join(lineas).strip()


class DcasaResena(models.Model):
    _name = 'dcasa.resena'
    _description = 'Opinión de un producto (de quien lo compró y lo pagó)'
    _order = 'create_date desc, id desc'
    _rec_name = 'product_tmpl_id'

    partner_id = fields.Many2one('res.partner', 'Cliente', required=True, readonly=True, index=True,
                                 ondelete='cascade', help='La ficha del cliente que la dejó (la de sus facturas).')
    product_tmpl_id = fields.Many2one('product.template', 'Producto', required=True, readonly=True, index=True,
                                      ondelete='cascade')
    factura_id = fields.Many2one('account.move', 'Factura pagada', readonly=True, ondelete='set null',
                                 help='La factura pagada con la que se comprobó que lo compró.')
    estrellas = fields.Integer('Estrellas', required=True, readonly=True)
    texto = fields.Text('Opinión', readonly=True)
    estado = fields.Selection(ESTADOS, 'Estado', required=True, default='pendiente', readonly=True, index=True)
    revisado_por_id = fields.Many2one('res.users', 'Revisada por', readonly=True, ondelete='set null')
    revisado_el = fields.Datetime('Revisada el', readonly=True)
    nombre_publico = fields.Char('Nombre en la ficha', compute='_compute_nombre_publico',
                                 help='Lo que se ve en la ficha: primer nombre e inicial del apellido.')

    _una_por_producto = models.Constraint('UNIQUE(partner_id, product_tmpl_id)',
                                          'Este cliente ya dejó su opinión de este producto.')
    _estrellas_validas = models.Constraint('CHECK(estrellas BETWEEN 1 AND 5)', 'Las estrellas van de 1 a 5.')
    _publicadas_idx = models.Index('(product_tmpl_id, estado)')

    @api.depends('partner_id.name')
    def _compute_nombre_publico(self):
        for resena in self:
            resena.nombre_publico = nombre_publico(resena.partner_id.name)

    @api.constrains('texto')
    def _check_texto(self):
        for resena in self:
            if len(resena.texto or '') > LARGO_MAXIMO:
                raise ValidationError(self.env._('La opinión puede tener hasta %s letras.', LARGO_MAXIMO))

    # ------------------------------------------------------------------
    # Nadie las escribe a mano ni cambia lo que dijo el cliente
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(self.env._('Las opiniones las deja el cliente desde Mi cuenta: no se escriben a mano.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise UserError(self.env._('La opinión es del cliente: solo se publica o no se publica, con sus botones.'))
        return super().write(vals)

    def unlink(self):
        # Solo un administrador puede borrar (ACL); si estaba publicada, la ficha cambia.
        publicadas = self.filtered(lambda r: r.estado == 'aprobada').product_tmpl_id
        resultado = super().unlink()
        self._dcasa_renovar_fichas(publicadas)
        return resultado

    # ------------------------------------------------------------------
    # Revisión (Gerencia o administrador)
    # ------------------------------------------------------------------

    def action_aprobar(self):
        """Botón «Publicar»: sale en la ficha y cuenta para las estrellas."""
        self._dcasa_revisar('aprobada')

    def action_rechazar(self):
        """Botón «No publicar»: no sale en ningún lado (se queda aquí, sin borrar)."""
        self._dcasa_revisar('rechazada')

    def _dcasa_revisar(self, estado):
        usuario = self.env.user
        if not any(usuario.has_group(grupo) for grupo in GRUPOS_REVISORES):
            raise AccessError(self.env._('Solo Gerencia o un administrador publica las opiniones.'))
        self.check_access('read')
        cambian = self.filtered(lambda r: r.estado != estado)
        if not cambian:
            return
        # sudo: el grupo ya se comprobó; el estado nunca se escribe por RPC (write lo exige).
        cambian.sudo().write({'estado': estado, 'revisado_por_id': usuario.id, 'revisado_el': fields.Datetime.now()})
        self._dcasa_renovar_fichas(cambian.product_tmpl_id)

    def _dcasa_renovar_fichas(self, plantillas):
        """La ficha guardada en el borde (Cloudflare) se vuelve a pedir: sus estrellas cambiaron."""
        if plantillas and 'dcasa.tienda.pendiente' in self.env:
            self.env['dcasa.tienda.pendiente']._dcasa_marcar(plantillas.ids, 'opiniones')

    # ------------------------------------------------------------------
    # Quién puede opinar de qué
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_facturas_pagadas(self, ficha):
        """Facturas de cliente publicadas y pagadas por completo de esta ficha (y sus contactos)."""
        Factura = self.env['account.move'].sudo()
        if not ficha:
            return Factura
        return Factura.search([
            ('partner_id', 'child_of', ficha.commercial_partner_id.id), ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'), ('payment_state', 'in', PAGADAS)], order='invoice_date desc, id desc')

    @api.model
    def _dcasa_por_resenar(self, ficha, website=None, facturas=None):
        """{product.template: factura} de lo que esta ficha compró y pagó, se ve en la tienda y todavía no opinó.

        ``facturas`` limita la búsqueda (el correo de una factura pagada solo invita por lo de esa factura)."""
        if not ficha:
            return {}
        ficha = ficha.commercial_partner_id
        pagadas = self._dcasa_facturas_pagadas(ficha)
        if facturas is not None:
            pagadas = pagadas & facturas.sudo()
        ya = set(self.sudo().search([('partner_id', '=', ficha.id)]).product_tmpl_id.ids)
        website = website or self.env['website'].sudo().get_current_website()
        publicado = website._dcasa_dominio_publicado() if website else Domain('is_published', '=', True)
        resultado = {}
        for factura in pagadas:
            for linea in factura.invoice_line_ids.filtered(lambda li: li.display_type == 'product' and li.product_id):
                plantilla = linea.product_id.product_tmpl_id
                if plantilla.id in ya or plantilla in resultado or plantilla.type == 'service':
                    continue
                resultado[plantilla] = factura
        if not resultado:
            return {}
        Plantilla = self.env['product.template'].sudo()
        visibles = Plantilla.browse([p.id for p in resultado]).filtered_domain(publicado)
        return {plantilla: factura for plantilla, factura in resultado.items() if plantilla in visibles}

    @api.model
    def _dcasa_crear_del_cliente(self, ficha, plantilla_id, estrellas, texto='', website=None):
        """Guarda la opinión del cliente con sesión (Mi cuenta), pendiente de revisión. Devuelve la reseña.

        Lanza ``UserError`` con el texto que ve el cliente si algo no cuadra: sin sesión, un producto que no compró
        o no pagó, uno del que ya opinó, estrellas fuera de 1 a 5 o un texto demasiado largo."""
        if not ficha:
            raise UserError(self.env._('Entra a tu cuenta para dejar tu opinión.'))
        try:
            plantilla_id, estrellas = int(plantilla_id), int(estrellas)
        except (TypeError, ValueError):
            raise UserError(self.env._('Elige de 1 a 5 estrellas.')) from None
        if not 1 <= estrellas <= 5:
            raise UserError(self.env._('Elige de 1 a 5 estrellas.'))
        texto = limpiar_texto(texto if isinstance(texto, str) else '')
        if len(texto) > LARGO_MAXIMO:
            raise UserError(self.env._('Tu opinión puede tener hasta %s letras.', LARGO_MAXIMO))
        por_resenar = {p.id: f for p, f in self._dcasa_por_resenar(ficha, website=website).items()}
        if plantilla_id not in por_resenar:
            raise UserError(self.env._('Puedes opinar de lo que compraste y ya pagaste, una vez por producto.'))
        # sudo: comprobado arriba que es su compra pagada y que no opinó; ningún portal tiene ACL sobre el modelo.
        try:
            with self.env.cr.savepoint():
                return self.sudo().create({
                    'partner_id': ficha.commercial_partner_id.id, 'product_tmpl_id': plantilla_id,
                    'factura_id': por_resenar[plantilla_id].id, 'estrellas': estrellas, 'texto': texto or False,
                })
        except psycopg2.IntegrityError:
            # Dos envíos a la vez del mismo formulario: la otra ya quedó guardada.
            raise UserError(self.env._('Ya nos dejaste tu opinión de este producto. ¡Gracias!')) from None

    @api.model
    def _dcasa_del_cliente(self, ficha):
        """Las opiniones que ya dejó esta ficha, para que vea en qué quedaron."""
        if not ficha:
            return self.sudo()
        return self.sudo().search([('partner_id', '=', ficha.commercial_partner_id.id)])

    # ------------------------------------------------------------------
    # Lo que se publica (ficha y datos para Google)
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_resumen(self, plantilla):
        """(cuántas publicadas, promedio) de un producto. Solo las aprobadas."""
        if not plantilla:
            return 0, 0.0
        [(total, suma)] = self.sudo()._read_group(
            [('product_tmpl_id', '=', plantilla.id), ('estado', '=', 'aprobada')],
            aggregates=['__count', 'estrellas:sum'])
        return total, ((suma or 0) / total if total else 0.0)

    @api.model
    def _dcasa_publicadas(self, plantilla):
        """Para la ficha: {'total', 'promedio', 'promedio_texto', 'redondeo', 'opiniones': [...]}; total 0 = nada."""
        total, promedio = self._dcasa_resumen(plantilla)
        if not total:
            return {'total': 0, 'opiniones': []}
        resenas = self.sudo().search([('product_tmpl_id', '=', plantilla.id), ('estado', '=', 'aprobada')],
                                     order='revisado_el desc, id desc', limit=MAXIMO_EN_FICHA)
        return {
            'total': total,
            'promedio': promedio,
            'promedio_texto': f'{promedio:.1f}',
            'redondeo': int(promedio + 0.5),
            'opiniones': [{
                'autor': resena.nombre_publico,
                'estrellas': resena.estrellas,
                'texto': resena.texto or '',
                'cuando': f'{MESES[resena.create_date.month - 1]} de {resena.create_date.year}',
            } for resena in resenas],
        }

    @api.model
    def _dcasa_valoracion_google(self, plantilla):
        """``aggregateRating`` de schema.org con las publicadas, o ``None`` si no hay ninguna (no se inventa)."""
        total, promedio = self._dcasa_resumen(plantilla)
        if not total:
            return None
        return {'@type': 'AggregateRating', 'ratingValue': round(promedio, 1), 'reviewCount': total,
                'bestRating': 5, 'worstRating': 1}


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _dcasa_opiniones(self):
        """Las opiniones publicadas de este producto, para la ficha (ver ``DcasaResena._dcasa_publicadas``)."""
        self.ensure_one()
        return self.env['dcasa.resena']._dcasa_publicadas(self)
