"""Buscar antes de crear: fichas con un nombre parecido (etapa 3, 2026-10-22).

El candado (``res_partner.py``) impide repetir un celular, un correo o un RUC; el nombre sí se puede repetir (dos
personas pueden llamarse igual). Pero una misma persona escrita dos veces con otro celular o sin datos sí se colaba.
Aquí se avisa, sin bloquear:

* **Al crear una ficha** (Contactos, «Crear y editar» de la cotización, Nuevo cliente del Inicio): mientras se escribe
  el nombre, un aviso amarillo muestra las fichas con un nombre parecido («Ojo: ya hay…») para usar esa en vez de
  crear otra.
* **Brian** (``crear_cliente``, por el chat o por Telegram) busca primero por celular, correo, RUC y nombre parecido;
  si encuentra una parecida, no crea nada y pregunta (para crearla igual, ``confirmar_nuevo``).

«Parecido»: las mismas palabras (sin mayúsculas, tildes ni signos), en cualquier orden, o un nombre que contiene al
otro («Ana Gómez» y «Ana María Gómez Pérez»). Solo fichas de clientes y proveedores: los usuarios y empleados del
sistema no cuentan (no se tocan).
"""
import re
import unicodedata

from odoo import api, fields, models

MINIMO_LETRAS = 4
MAXIMO = 5


def palabras(nombre):
    """«Ana  Gómez-Pérez» → ['ana', 'gomez', 'perez'] (sin tildes ni signos; las de una letra no cuentan)."""
    texto = unicodedata.normalize('NFKD', (nombre or '').lower())
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return [p for p in re.split(r'[^0-9a-zñ]+', texto) if len(p) > 1]


def parecidos(uno, otro):
    """¿Dos nombres parecen la misma persona? Las palabras de uno están todas en el otro (con al menos dos)."""
    a, b = set(palabras(uno)), set(palabras(otro))
    if not a or not b:
        return False
    if a == b:
        return True
    menor, mayor = (a, b) if len(a) <= len(b) else (b, a)
    return len(menor) >= 2 and menor <= mayor


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dcasa_parecidas_aviso = fields.Char(
        'Fichas parecidas', compute='_compute_dcasa_parecidas_aviso',
        help='Al crear una ficha: otras con un nombre parecido, para no repetir a la misma persona.')

    @api.model
    def _dcasa_fichas_parecidas(self, nombre, excepto=None, limite=MAXIMO):
        """Fichas (clientes y proveedores; nunca usuarios ni empleados) con un nombre parecido, la más vieja primero."""
        lista = palabras(nombre)
        if len(''.join(lista)) < MINIMO_LETRAS:
            return self.browse()
        # La palabra más larga filtra en la base; el parecido de verdad se mira aquí.
        clave = max(lista, key=len)
        dominio = self._dcasa_dominio_fichas() + [('name', 'ilike', clave)]
        if excepto:
            dominio.append(('id', 'not in', excepto.ids))
        candidatas = self.sudo().with_context(active_test=False).search(dominio, order='id', limit=200)
        return candidatas.filtered(lambda ficha: parecidos(nombre, ficha.name))[:limite]

    @api.model
    def _dcasa_describir_ficha(self, ficha):
        extra = ficha.phone or ficha.email or ficha.vat
        return f'«{ficha.name}»' + (f' ({extra})' if extra else '') + ('' if ficha.active else ' (archivada)')

    @api.depends('name')
    def _compute_dcasa_parecidas_aviso(self):
        es_equipo = self.env.user.has_group('base.group_user')
        for partner in self:
            partner.dcasa_parecidas_aviso = False
            # Solo mientras se crea la ficha (la que ya existe se limpia en «Posibles duplicados»), y solo al equipo.
            if not es_equipo or partner._origin.id or partner.parent_id:
                continue
            parecidas = self._dcasa_fichas_parecidas(partner.name)
            if parecidas:
                partner.dcasa_parecidas_aviso = self.env._(
                    'Ojo: ya hay fichas con un nombre parecido: %s. Si es la misma persona, usa esa ficha en vez de '
                    'crear otra.', ', '.join(self._dcasa_describir_ficha(f) for f in parecidas))
