"""El sitio se edita por código (docs/OPERACION.md, «El sitio se edita por código»).

Odoo trae un constructor de páginas (Sitio web → Editar / Nuevo). Al guardar con él una página
que viene de un módulo, Odoo no toca la plantilla del módulo: hace una **copia por sitio**
(``ir.ui.view`` con ``website_id``, mismo ``key``; ``website/models/ir_ui_view.py``, ``write``).
Desde ese momento el sitio dibuja la copia y la plantilla del módulo deja de aplicarse en esa
página: lo que se cambie por código ya no se ve ahí (``_load_records_write`` solo propaga a la
copia los campos que nadie modificó). Como todo el sitio de D'CASA vive en ``website_dcasa`` y
se despliega desde el repositorio, aquí se cierra ese camino:

1. Nadie tiene los grupos de editor/diseñador del sitio (``_sitio_por_codigo``, idempotente,
   se repite en cada actualización del módulo). Sin ellos no aparecen «Editar» ni «Nuevo».
2. Guarda de seguridad: ninguna copia por sitio ni edición desde el panel de las plantillas de
   D'CASA. Las copias que Odoo hace por su cuenta no se tocan: las de instalación (en una base
   limpia: ``website.homepage`` y ``website_dcasa.homepage_dcasa``, que hereda de ella) corren
   como superusuario, y las de otras claves (opciones de la tienda de ``website_sale``, el tema)
   no están protegidas. Solo el SEO de una página (título/descripción para Google) se deja
   escribir en una vista protegida: no toca la plantilla.
3. «Vista previa móvil»: el sitio público en un marco de 390×844 (teléfono), 768 o 1440, sin
   modo edición.

Para dejar editar de verdad (p. ej. una emergencia): Ajustes → Técnico → Parámetros del sistema →
``dcasa_interfaz.sitio_editable`` = ``1``. Para devolverle el constructor a alguien hay que, además,
darle el grupo «Sitio web / Editor y diseñador» (lo retira la siguiente actualización).
"""
from odoo import Command, api, models
from odoo.exceptions import UserError

# Claves de vista (``módulo.nombre``) que se mantienen desde el código.
MODULOS_PROPIOS = ('website_dcasa',)
PREFIJO_PROPIO = 'dcasa_'
# La portada de Odoo (``website.homepage``) la llena website_dcasa por herencia: editarla con el
# constructor rompe la herencia igual que editar una plantilla propia.
CLAVES_PROTEGIDAS = frozenset({'website.homepage'})

# Lo único que sí se cambia de una página desde el panel: publicarla (columnas de la página) y su SEO
# (columnas de la vista: título y descripción para Google; solo administradores, que son quienes
# pueden escribir ``ir.ui.view``). Odoo respeta lo que escriba la dueña (``website._dcasa_seo_portada``).
CAMPOS_SEO = frozenset({
    'website_meta_title', 'website_meta_description', 'website_meta_keywords', 'website_meta_og_img',
    'seo_name',
})
CAMPOS_PAGINA_PERMITIDOS = frozenset({
    'is_published', 'website_published', 'website_indexed', 'date_publish',
}) | CAMPOS_SEO

MENSAJE = ("Esta página se mantiene desde el código y no se edita desde aquí: pide el cambio a quien "
           "mantiene el sitio (docs/OPERACION.md, «El sitio se edita por código»). Si de verdad hace "
           "falta editar desde el panel, un administrador puede poner el parámetro del sistema "
           "«dcasa_interfaz.sitio_editable» en 1.")


def _modulo_de(clave):
    return (clave or '').split('.', 1)[0]


def _clave_protegida(clave):
    if not clave:
        return False
    if clave in CLAVES_PROTEGIDAS:
        return True
    modulo = _modulo_de(clave)
    return modulo in MODULOS_PROPIOS or modulo.startswith(PREFIJO_PROPIO)


def _edicion_permitida(env):
    """Cuándo NO se aplica la guarda: lo que hace Odoo por dentro y el escape documentado.

    * ``env.su``: ``sudo()`` y el superusuario (crons, ganchos, migraciones, funciones de datos).
    * Instalación/actualización de módulos (``pool._init``, ``install_mode``): ahí Odoo crea las
      copias por sitio de las vistas que heredan de una vista ya copiada
      (``_create_all_specific_views``) y recarga las plantillas.
    * El parámetro ``dcasa_interfaz.sitio_editable`` = 1 (Ajustes → Técnico), para quien sabe lo
      que hace.
    """
    if env.su or env.registry._init or env.context.get('install_mode'):
        return True
    return env['ir.config_parameter'].sudo().get_param('dcasa_interfaz.sitio_editable') == '1'


class DcasaSitio(models.AbstractModel):
    _name = 'dcasa.sitio'
    _description = "El sitio de D'CASA se edita por código"

    @api.model
    def _grupos_de_editor(self):
        return (self.env.ref('website.group_website_designer')
                | self.env.ref('website.group_website_restricted_editor'))

    @api.model
    def _sitio_por_codigo(self):
        """Nadie edita el sitio desde el panel. Idempotente; corre en cada actualización.

        * Ningún grupo ajeno a «Sitio web» implica editor/diseñador: Odoo se lo cuelga a
          Administración/Ajustes (``base.group_system``) y website_dcasa a Gerencia; aquí se quita.
        * Ningún usuario los tiene asignados directamente (Odoo se los da a admin al instalar).
        """
        grupos = self._grupos_de_editor()
        Grupos = self.env['res.groups'].sudo()
        implicadores = Grupos.search([('implied_ids', 'in', grupos.ids)]) - grupos
        if implicadores:
            implicadores.write({'implied_ids': [Command.unlink(g.id) for g in grupos]})
        usuarios = self.env['res.users'].sudo().with_context(active_test=False).search(
            [('group_ids', 'in', grupos.ids)])
        if usuarios:
            usuarios.write({'group_ids': [Command.unlink(g.id) for g in grupos]})
        return bool(implicadores or usuarios)

    @api.model
    def vista_previa(self):
        """Lo que necesita la pantalla «Vista previa móvil»: la URL pública del sitio.

        Es la canónica (``web.base.url`` = https://CANONICAL_HOST, congelada por el entrypoint, o el
        dominio del sitio si está puesto). El navegador la usa tal cual si coincide con el origen
        del panel; si no (p. ej. staging abierto por workers.dev), enmarca su propio origen, porque
        el borde manda ``frame-ancestors 'self'``. No lee nada sensible.
        """
        sitio = self.env['website'].sudo().get_current_website()
        return {
            'url': (sitio.get_base_url() or '').rstrip('/'),
            'nombre': sitio.name,
            'paginas': [
                {'nombre': 'Inicio', 'ruta': '/'},
                {'nombre': 'Tienda', 'ruta': '/shop'},
                {'nombre': 'Socios', 'ruta': '/socios'},
                {'nombre': 'Visítanos', 'ruta': '/visitanos'},
            ],
        }


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    def _dcasa_comprobar_edicion(self, vals=None):
        """Lanza UserError si alguien intenta cambiar desde el panel una plantilla de D'CASA.

        Cambiar solo el SEO (``CAMPOS_SEO``, que la página escribe en su vista) sí se deja: no toca
        la plantilla.
        """
        if _edicion_permitida(self.env) or (vals and set(vals) <= CAMPOS_SEO):
            return
        if any(v.type == 'qweb' and _clave_protegida(v.key or v.xml_id) for v in self):
            raise UserError(MENSAJE)

    @api.model_create_multi
    def create(self, vals_list):
        # La copia por sitio nace aquí: copy() de la vista genérica con website_id y su misma clave.
        if not _edicion_permitida(self.env):
            for vals in vals_list:
                if vals.get('website_id') and _clave_protegida(vals.get('key')):
                    raise UserError(MENSAJE)
        return super().create(vals_list)

    def write(self, vals):
        self._dcasa_comprobar_edicion(vals)
        return super().write(vals)

    def unlink(self):
        self._dcasa_comprobar_edicion()
        return super().unlink()


class WebsitePage(models.Model):
    _inherit = 'website.page'

    def open_website_url(self):
        """La fila de «Sitio web → Páginas» abre la vista previa propia.

        La de Odoo (``website.website_preview``) precarga el constructor completo y la lista de
        bloques en cuanto se abre, tenga o no el usuario el grupo de editor.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'dcasa_vista_previa',
            'name': self.env._('Vista previa móvil'),
            'params': {'ruta': self.url or '/'},
        }

    def write(self, vals):
        # Publicar y el SEO sí; nombre, URL, contenido o vista de una página de D'CASA, no.
        if not _edicion_permitida(self.env) and set(vals) - CAMPOS_PAGINA_PERMITIDOS:
            # sudo(): quien ve páginas (Gerencia) no lee ir.ui.view; aquí solo se mira la clave.
            if any(_clave_protegida(p.view_id.key) or p.url == '/' for p in self.sudo()):
                raise UserError(MENSAJE)
        return super().write(vals)
