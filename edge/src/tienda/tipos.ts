/**
 * Forma del feed `GET /dcasa/tienda/feed` (addons/dcasa_tienda_borde/models/website.py).
 * Si cambia allá, cambia aquí (y VERSION_FEED de los dos lados).
 */
export const VERSION_FEED = 1;

export type ModoCompra = "directa" | "variantes" | "ficha";

/**
 * Foto servida por `/dcasa/img` (addons/website_dcasa/models/imagen.py): la URL es
 * `${base}/${ancho}.${"webp" | "jpg"}?v=${v}`, con `ancho` en `ANCHOS_IMAGEN` (render.ts).
 * Inmutable: `v` es el checksum de la foto.
 */
export interface FotoFeed {
  base: string;
  v: string;
}

export interface ImagenesProducto {
  image_256: string;
  image_512: string;
  image_1024: string;
  image_1920: string;
  /** Ausente en un feed de un Odoo anterior: entonces se usan las URL de `/web/image`. */
  foto?: FotoFeed | null;
}

export interface VarianteFeed {
  id: number;
  nombre: string;
  precio: number;
  disponible: boolean | null;
  existencias: number | null;
}

export interface ProductoFeed {
  id: number;
  nombre: string;
  codigo: string;
  /** `website_url` de Odoo, p. ej. `/shop/cama-twin-12`. */
  url: string;
  precio: number;
  precio_lista: number;
  precio_visible: boolean;
  mas_itbms: boolean;
  moneda: string;
  categorias: number[];
  /** HTML de `description_ecommerce` (ya saneado por Odoo al guardarlo). */
  descripcion_html: string;
  descripcion_corta: string;
  imagen: ImagenesProducto | null;
  galeria: string[];
  /** Las mismas fotos de `galeria`, en `/dcasa/img` (null si Odoo no la tiene). */
  galeria_fotos?: (FotoFeed | null)[];
  seo: { titulo: string; descripcion: string };
  json_ld: unknown[];
  compra: ModoCompra;
  variantes: VarianteFeed[];
  /** `null` mientras PUBLICAR_DISPONIBILIDAD sea falso: no se publica nada sobre existencias. */
  disponible: boolean | null;
  existencias: number | null;
  whatsapp: string;
  secuencia: number;
}

export interface CategoriaFeed {
  id: number;
  nombre: string;
  padre_id: number | null;
  secuencia: number;
  /** `/shop/category/<slug>`, igual que Odoo. */
  url: string;
  seo: { titulo: string; descripcion: string };
}

export interface PaginaFeed {
  titulo: string;
  descripcion: string;
  actualizado: string;
  html: string;
}

export interface Feed {
  version: number;
  generado: string;
  sitio: {
    nombre: string;
    /** URL pública (dominio); "" si Odoo solo conoce una URL local. */
    url_base: string;
    moneda: string;
    whatsapp: string;
    publicar_disponibilidad: boolean;
    por_pagina: number;
    /** Anchos que acepta `/dcasa/img` (los mismos que `ANCHOS_IMAGEN`). */
    imagen_anchos?: number[];
    json_ld_tienda: Record<string, unknown>;
    json_ld_organizacion: Record<string, unknown>;
  };
  empresa: {
    nombre: string;
    ruc: string;
    calle: string;
    ciudad: string;
    telefono: string;
    email: string;
    latitud: number;
    longitud: number;
  };
  socios: {
    puntos_por_dolar: number | null;
    puntos_al_padrino: number | null;
    puntos_al_ahijado: number | null;
  };
  portada: {
    seo: { titulo: string; descripcion: string };
    categorias: { nombre: string; url: string; imagen: string; alt: string }[];
    mas_buscados: number[];
    para_dormir: number[];
    para_dormir_url: string;
  };
  tienda: { descripcion: string };
  categorias: CategoriaFeed[];
  productos: ProductoFeed[];
  paginas: Record<string, PaginaFeed>;
}

/** Validación mínima: lo justo para no publicar un sitio vacío por un feed roto. */
export function esFeedValido(datos: unknown): datos is Feed {
  if (!datos || typeof datos !== "object") return false;
  const f = datos as Partial<Feed>;
  return (
    f.version === VERSION_FEED &&
    !!f.sitio &&
    Array.isArray(f.productos) &&
    Array.isArray(f.categorias) &&
    !!f.portada &&
    !!f.paginas &&
    f.productos.every((p) => typeof p?.url === "string" && p.url.startsWith("/shop/"))
  );
}
