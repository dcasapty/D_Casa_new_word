"""Las fotos de un producto: verlas en grande, subir varias, ordenarlas, elegir la principal, quitar, girar y recortar.

Pedido de la dueña (2026-10-22): «ver la foto de un producto es un problema terrible… al hacer clic debería poderse
ver, editar, recortar o reemplazar con mucha facilidad» y «agregar las fotos es muy poco intuitivo y limitado».

* **Cuáles son las fotos.** La principal es ``image_1920`` del producto (la de la ficha, las listas, las cotizaciones y
  la tienda); las demás son las «Imágenes extra» de la pestaña Ventas (``product_template_image_ids``, el
  ``product.image`` de website_sale, en su ``sequence``). Para la pantalla son UNA fila ordenada: la primera es la
  principal. Los videos de la tienda (``video_url``) no son fotos: no salen aquí ni se tocan (quedan al final).
* **Quién las cambia.** Quien puede editar el producto (``check_access('write')`` en ``product.template``: hoy
  Gerencia, administradores y la Vendedora, que «edita el producto: nombre, descripción, fotos…», dcasa_base). Las
  fotos extra se escriben con ``sudo`` DESPUÉS de esa comprobación: Odoo deja editar ``product.image`` solo a Gerencia
  de ventas y a los editores del sitio (que aquí nadie tiene). Quien no puede editar el producto solo ve y descarga, y
  el servidor se lo niega aunque llame a mano (``AccessError``). La regla vive en ``_dcasa_exigir_editar_fotos``.
* **Calidad.** Se guarda el archivo tal cual lo sube la persona; Odoo lo deja en 1920 px como máximo (lado mayor) y saca
  los tamaños chicos (1024, 512, 256, 128). Girar y recortar se hacen en el servidor sobre la foto guardada más grande,
  con la orientación de la cámara ya aplicada (la misma que ve el navegador), y se vuelven a guardar en el mismo
  formato (JPEG a calidad 95, como Odoo; PNG sin pérdida). El recorte llega en píxeles de esa foto (Cropper.js de Odoo
  sobre ``image_1920``), así que no se re-codifica en el navegador.
* **Ordenar sin mover fotos de más.** Cambiar el orden de las extra es cambiar su ``sequence``. Solo cuando cambia la
  principal se intercambian dos fotos (la nueva principal pasa a ``image_1920`` y la vieja ocupa su lugar en las extra).

Cada método devuelve lo mismo que ``dcasa_fotos()`` (la fila de fotos al día) para que la pantalla se redibuje.
"""
import base64
import binascii
import io

from PIL import Image, WebPImagePlugin  # noqa: F401 — odoo.tools.image deja solo los formatos que registra

from odoo import models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.tools.image import IMAGE_MAX_RESOLUTION, image_fix_orientation

PRINCIPAL = 'principal'
PREFIJO_EXTRA = 'extra-'
# Límites técnicos (no del negocio): cuántas fotos por llamada y cuánto pesa una foto como máximo.
MAX_FOTOS_POR_LLAMADA = 10
MAX_MB_POR_FOTO = 25
LADO_MINIMO_DEL_RECORTE = 20
FORMATOS = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'GIF': 'gif'}
EXTENSION_DE = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif'}
SENTIDOS = {'derecha': Image.Transpose.ROTATE_270, 'izquierda': Image.Transpose.ROTATE_90}


def transformar(env, datos, cambio):
    """Los bytes de la foto ``datos`` con ``cambio(imagen PIL) → imagen PIL`` aplicado, en su mismo formato.

    La orientación de la cámara (EXIF) se aplica antes, y la foto nueva sale sin EXIF: si no, el navegador la giraría
    otra vez. Se conserva el perfil de color. Una foto animada (GIF) no se toca."""
    try:
        original = Image.open(io.BytesIO(datos))
        original.load()
    except (OSError, ValueError, Image.DecompressionBombError):
        raise UserError(env._('No pude abrir esta foto. Vuelve a subirla.')) from None
    if getattr(original, 'is_animated', False):
        raise UserError(env._('Esta foto es animada (GIF): no se puede girar ni recortar aquí.'))
    formato = (original.format or '').upper()
    perfil = original.info.get('icc_profile')
    imagen = cambio(image_fix_orientation(original))
    if imagen is None:
        return None
    salida = io.BytesIO()
    extra = {'icc_profile': perfil} if perfil else {}
    if formato == 'JPEG':
        if imagen.mode not in ('RGB', 'L'):
            imagen = imagen.convert('RGB')
        imagen.save(salida, format='JPEG', quality=95, optimize=True, **extra)
    elif formato == 'WEBP':
        imagen.save(salida, format='WEBP', quality=95, method=4, **extra)
    else:
        imagen.save(salida, format='PNG', optimize=True, **extra)
    return salida.getvalue()


def leer_foto(env, datos_b64):
    """``(base64 limpio, formato)`` de una foto que manda la pantalla, o ``UserError`` en palabras sencillas."""
    if not isinstance(datos_b64, str) or not datos_b64:
        raise UserError(env._('No llegó la foto. Vuelve a elegirla.'))
    if datos_b64.startswith('data:'):
        datos_b64 = datos_b64.split(',', 1)[-1]
    if len(datos_b64) * 3 // 4 > MAX_MB_POR_FOTO * 1024 * 1024:
        raise UserError(env._('Esa foto pesa más de %(mb)s MB. Elige una más liviana.', mb=MAX_MB_POR_FOTO))
    try:
        datos = base64.b64decode(datos_b64, validate=True)
    except (binascii.Error, ValueError):
        raise UserError(env._('Ese archivo no es una foto. Elige un JPG, PNG o WebP.')) from None
    try:
        with Image.open(io.BytesIO(datos)) as imagen:
            formato = (imagen.format or '').upper()
            ancho, alto = imagen.size
    except (OSError, ValueError, Image.DecompressionBombError):
        raise UserError(env._('Ese archivo no es una foto. Elige un JPG, PNG o WebP.')) from None
    if formato not in FORMATOS:
        raise UserError(env._('Ese formato de foto no se puede usar. Elige un JPG, PNG o WebP.'))
    if ancho * alto > IMAGE_MAX_RESOLUTION:
        raise UserError(env._('Esa foto es demasiado grande (más de %(mp)s megapíxeles). Elige una más chica.',
                              mp=int(IMAGE_MAX_RESOLUTION / 1e6)))
    return base64.b64encode(datos).decode(), formato


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # ------------------------------------------------------------------
    # Permisos y lectura
    # ------------------------------------------------------------------

    def _dcasa_exigir_editar_fotos(self):
        """Quien cambia las fotos de un producto es quien puede editar ese producto (ver el docstring del módulo)."""
        self.ensure_one()
        if not self.has_access('write'):
            raise AccessError(self.env._('No puedes cambiar las fotos de este producto: solo verlas.'))

    def _dcasa_al_dia(self):
        """Lo guardado de verdad: las fotos se leen sin su contenido (``bin_size``) y esa lectura no se entera de lo
        que se acaba de escribir con el contenido completo (otra entrada de la caché)."""
        self.env.flush_all()
        self.invalidate_recordset(['image_1920', 'product_template_image_ids'])
        self.env['product.image'].invalidate_model(['image_1920', 'sequence'])

    def _dcasa_tiene_principal(self):
        self._dcasa_al_dia()
        return bool(self.with_context(bin_size=True).image_1920)

    def _dcasa_extras(self):
        """Las fotos extra de la tienda, sin los videos, en su orden (``sudo``: ya se comprobó el permiso)."""
        self._dcasa_al_dia()
        imagenes = self.sudo().with_context(bin_size=True).product_template_image_ids
        return imagenes.filtered(lambda imagen: imagen.image_1920 and not imagen.video_url).sorted(
            lambda imagen: (imagen.sequence, imagen.id))

    def _dcasa_claves(self):
        claves = [PRINCIPAL] if self._dcasa_tiene_principal() else []
        return claves + [f'{PREFIJO_EXTRA}{imagen.id}' for imagen in self._dcasa_extras()]

    def _dcasa_adjuntos_de_fotos(self, extras):
        """``{(modelo, id): (checksum, mimetype)}`` de las fotos: la versión de cada URL (cambia si cambia la foto)."""
        dominio = Domain.OR([
            Domain([('res_model', '=', 'product.template'), ('res_id', '=', self.id)]),
            Domain([('res_model', '=', 'product.image'), ('res_id', 'in', extras.ids)]),
        ]) & Domain('res_field', '=', 'image_1920')
        return {(adjunto.res_model, adjunto.res_id): (adjunto.checksum or '', adjunto.mimetype or '')
                for adjunto in self.env['ir.attachment'].sudo().search_fetch(
                    dominio, ['res_model', 'res_id', 'checksum', 'mimetype'])}

    def _dcasa_foto(self, modelo, registro_id, clave, adjuntos, posicion):
        checksum, mimetype = adjuntos.get((modelo, registro_id), ('', ''))
        version = f'?unique={checksum[:12]}' if checksum else ''
        base = f'/web/image/{modelo}/{registro_id}'
        nombre = f'{self.default_code or "producto-" + str(self.id)}-{posicion}.{EXTENSION_DE.get(mimetype, "jpg")}'
        return {
            'clave': clave,
            'principal': clave == PRINCIPAL,
            'grande': f'{base}/image_1920{version}',
            'mediana': f'{base}/image_1024{version}',
            'miniatura': f'{base}/image_256{version}',
            'descarga': f'/web/content/{modelo}/{registro_id}/image_1920?download=true&filename={nombre}',
            'nombre_archivo': nombre,
        }

    def _dcasa_fotos_datos(self):
        self.ensure_one()
        extras = self._dcasa_extras()
        adjuntos = self._dcasa_adjuntos_de_fotos(extras)
        fotos = []
        if self._dcasa_tiene_principal():
            fotos.append(self._dcasa_foto('product.template', self.id, PRINCIPAL, adjuntos, 1))
        for imagen in extras:
            fotos.append(self._dcasa_foto('product.image', imagen.id, f'{PREFIJO_EXTRA}{imagen.id}', adjuntos,
                                          len(fotos) + 1))
        return {
            'producto': {
                'id': self.id,
                'nombre': self.name,
                'codigo': self.default_code or '',
                'publicado': bool(self.is_published),
            },
            'puede_editar': self.has_access('write'),
            'fotos': fotos,
        }

    def dcasa_fotos(self):
        """Las fotos del producto en su orden (la primera es la principal) y si quien mira puede cambiarlas. Solo para
        el equipo (usuarios internos): el cliente ve las fotos en la tienda."""
        self.ensure_one()
        if not self.env.user._is_internal():
            raise AccessError(self.env._('Las fotos del producto se ven desde Odoo.'))
        self.check_access('read')
        return self._dcasa_fotos_datos()

    # ------------------------------------------------------------------
    # Cambios
    # ------------------------------------------------------------------

    def _dcasa_destino(self, clave):
        """El registro que guarda la foto ``clave``: el producto (la principal) o su foto extra (``sudo``)."""
        if clave == PRINCIPAL:
            return self
        if isinstance(clave, str) and clave.startswith(PREFIJO_EXTRA) and clave[len(PREFIJO_EXTRA):].isdigit():
            imagen = self._dcasa_extras().filtered(lambda i: i.id == int(clave[len(PREFIJO_EXTRA):]))
            if imagen:
                return imagen.with_context(bin_size=False)
        raise UserError(self.env._('Esa foto ya no está: cierra y vuelve a abrir las fotos del producto.'))

    def _dcasa_nombre_de_extra(self, posicion):
        return f'{self.name} ({posicion})'

    def dcasa_fotos_subir(self, fotos):
        """Agrega fotos (``[{'nombre', 'datos' en base64}]``, hasta 10 por llamada). Si el producto no tenía foto
        principal, la primera queda de principal; las demás van al final de las extra, en el orden en que llegan."""
        self._dcasa_exigir_editar_fotos()
        if not isinstance(fotos, list) or not fotos:
            raise UserError(self.env._('Elige al menos una foto.'))
        if len(fotos) > MAX_FOTOS_POR_LLAMADA:
            raise UserError(self.env._('Sube hasta %(maximo)s fotos por vez.', maximo=MAX_FOTOS_POR_LLAMADA))
        leidas = [leer_foto(self.env, foto.get('datos') if isinstance(foto, dict) else None)[0] for foto in fotos]
        if not self._dcasa_tiene_principal():
            self.image_1920 = leidas.pop(0)
        if leidas:
            todas = self.sudo().product_template_image_ids
            ultima = max(todas.mapped('sequence') or [0])
            cuantas = len(self._dcasa_extras()) + 2
            self.env['product.image'].sudo().create([{
                'product_tmpl_id': self.id,
                'name': self._dcasa_nombre_de_extra(cuantas + indice),
                'sequence': ultima + indice + 1,
                'image_1920': datos,
            } for indice, datos in enumerate(leidas)])
            self._dcasa_videos_al_final()
        return self._dcasa_fotos_datos()

    def dcasa_fotos_reemplazar(self, clave, datos):
        """Cambia la foto ``clave`` por otra (archivo o cámara), en el mismo lugar."""
        self._dcasa_exigir_editar_fotos()
        nueva, _formato = leer_foto(self.env, datos)
        destino = self._dcasa_destino(clave)
        destino.image_1920 = nueva
        return self._dcasa_fotos_datos()

    def dcasa_fotos_ordenar(self, claves):
        """Deja las fotos en el orden de ``claves`` (todas las de ahora, cada una una vez). La primera es la
        principal."""
        self._dcasa_exigir_editar_fotos()
        actuales = self._dcasa_claves()
        if not isinstance(claves, list) or len(claves) != len(actuales) or set(claves) != set(actuales):
            raise UserError(self.env._('Las fotos cambiaron mientras tanto: cierra y vuelve a abrir las fotos del '
                                       'producto.'))
        self._dcasa_aplicar_orden(list(claves))
        return self._dcasa_fotos_datos()

    def dcasa_fotos_principal(self, clave):
        """La foto ``clave`` pasa a ser la principal; la que era principal queda segunda."""
        self._dcasa_exigir_editar_fotos()
        actuales = self._dcasa_claves()
        if clave not in actuales:
            raise UserError(self.env._('Esa foto ya no está: cierra y vuelve a abrir las fotos del producto.'))
        if clave != PRINCIPAL:
            self._dcasa_aplicar_orden([clave] + [otra for otra in actuales if otra != clave])
        return self._dcasa_fotos_datos()

    def _dcasa_aplicar_orden(self, claves):
        extras = {f'{PREFIJO_EXTRA}{imagen.id}': imagen.with_context(bin_size=False) for imagen in self._dcasa_extras()}
        primera = claves.pop(0)
        if primera != PRINCIPAL:
            # Cambia la principal: la foto elegida pasa al producto y la que era principal ocupa su registro (y su
            # lugar en la fila). Si no había principal, el registro de la elegida sobra.
            elegida = extras[primera]
            vieja = self.with_context(bin_size=False).image_1920
            self.image_1920 = elegida.image_1920
            if PRINCIPAL in claves:
                elegida.image_1920 = vieja
                claves[claves.index(PRINCIPAL)] = primera
            else:
                elegida.unlink()
        for posicion, clave in enumerate(claves, start=1):
            if extras[clave].exists() and extras[clave].sequence != posicion:
                extras[clave].sequence = posicion
        self._dcasa_videos_al_final()

    def _dcasa_videos_al_final(self):
        """Los videos de la tienda van después de todas las fotos, en su mismo orden."""
        todas = self.sudo().with_context(bin_size=True).product_template_image_ids
        videos = todas.filtered('video_url').sorted(lambda v: (v.sequence, v.id))
        if not videos:
            return
        ultima = max((todas - videos).mapped('sequence') or [0])
        for posicion, video in enumerate(videos, start=ultima + 1):
            if video.sequence != posicion:
                video.sequence = posicion

    def dcasa_fotos_quitar(self, clave):
        """Quita la foto ``clave``. Si era la principal, la siguiente pasa a ser la principal."""
        self._dcasa_exigir_editar_fotos()
        destino = self._dcasa_destino(clave)
        if clave == PRINCIPAL:
            siguiente = self._dcasa_extras()[:1].with_context(bin_size=False)
            if siguiente:
                self.image_1920 = siguiente.image_1920
                siguiente.unlink()
            else:
                self.image_1920 = False
        else:
            destino.unlink()
        return self._dcasa_fotos_datos()

    def dcasa_fotos_girar(self, clave, sentido='derecha'):
        """Gira la foto un cuarto de vuelta (``derecha`` o ``izquierda``)."""
        self._dcasa_exigir_editar_fotos()
        if sentido not in SENTIDOS:
            raise UserError(self.env._('Elige girar a la derecha o a la izquierda.'))
        destino = self._dcasa_destino(clave)
        datos = destino.with_context(bin_size=False).image_1920
        if not datos:
            raise UserError(self.env._('Esa foto ya no está: cierra y vuelve a abrir las fotos del producto.'))
        girada = transformar(self.env, base64.b64decode(datos), lambda imagen: imagen.transpose(SENTIDOS[sentido]))
        destino.image_1920 = base64.b64encode(girada)
        return self._dcasa_fotos_datos()

    def dcasa_fotos_recortar(self, clave, x, y, ancho, alto):
        """Recorta la foto ``clave`` al rectángulo dado en píxeles de la foto guardada más grande (``image_1920``,
        con la orientación de la cámara aplicada: lo mismo que ve el navegador)."""
        self._dcasa_exigir_editar_fotos()
        try:
            x, y, ancho, alto = (int(round(float(valor))) for valor in (x, y, ancho, alto))
        except (TypeError, ValueError, OverflowError):
            raise UserError(self.env._('El recorte no se entendió. Vuelve a marcarlo.')) from None
        destino = self._dcasa_destino(clave)
        datos = destino.with_context(bin_size=False).image_1920
        if not datos:
            raise UserError(self.env._('Esa foto ya no está: cierra y vuelve a abrir las fotos del producto.'))

        def recortar(imagen):
            total_ancho, total_alto = imagen.size
            x0, y0 = min(max(x, 0), total_ancho - 1), min(max(y, 0), total_alto - 1)
            x1, y1 = min(max(x + ancho, x0 + 1), total_ancho), min(max(y + alto, y0 + 1), total_alto)
            if x1 - x0 < LADO_MINIMO_DEL_RECORTE or y1 - y0 < LADO_MINIMO_DEL_RECORTE:
                raise UserError(self.env._('Ese recorte es demasiado pequeño. Agranda el cuadro.'))
            if (x0, y0, x1, y1) == (0, 0, total_ancho, total_alto):
                return None
            return imagen.crop((x0, y0, x1, y1))

        recortada = transformar(self.env, base64.b64decode(datos), recortar)
        if recortada:
            destino.image_1920 = base64.b64encode(recortada)
        return self._dcasa_fotos_datos()
