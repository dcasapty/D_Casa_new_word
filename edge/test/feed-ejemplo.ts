import type { Feed, ProductoBlackWeekend, ProductoFeed } from "../src/tienda/tipos";

const imagen = (id: number) => {
  const u = (t: string) => `/web/image/product.template/${id}/${t}?unique=abc1234`;
  return {
    image_256: u("image_256"),
    image_512: u("image_512"),
    image_1024: u("image_1024"),
    image_1920: u("image_1920"),
    foto: { base: `/dcasa/img/product.template/${id}/image_1920`, v: "0123456789ab" },
  };
};

export function producto(id: number, extra: Partial<ProductoFeed> = {}): ProductoFeed {
  const nombre = extra.nombre ?? `Mueble ${id}`;
  return {
    id,
    nombre,
    codigo: `COD-${id}`,
    url: `/shop/mueble-${id}-${id}`,
    precio: 104.99,
    precio_lista: 104.99,
    precio_visible: true,
    mas_itbms: true,
    moneda: "USD",
    categorias: [3],
    descripcion_html: "",
    descripcion_corta: "",
    imagen: imagen(id),
    galeria: [],
    seo: { titulo: "", descripcion: "" },
    json_ld: [
      {
        "@context": "https://schema.org",
        "@type": "Product",
        name: nombre,
        url: `https://dcasapty.com/shop/mueble-${id}-${id}`,
        offers: { "@type": "Offer", price: extra.precio ?? 104.99, priceCurrency: "USD" },
      },
    ],
    compra: "directa",
    variantes: [],
    disponible: null,
    existencias: null,
    whatsapp: `https://wa.me/50760261919?text=Hola%20D'CASA%2C%20me%20interesa%3A%20Mueble%20${id}`,
    secuencia: id,
    ...extra,
  };
}

export function feedEjemplo(productos: ProductoFeed[] = [producto(1), producto(2)]): Feed {
  return {
    version: 1,
    generado: "2026-10-02T12:00:00Z",
    sitio: {
      nombre: "D'CASA Panamá",
      url_base: "https://dcasapty.com",
      moneda: "USD",
      whatsapp: "https://wa.me/50760261919?text=Hola%20D%27CASA%2C%20quiero%20informaci%C3%B3n",
      publicar_disponibilidad: false,
      por_pagina: 20,
      json_ld_tienda: { "@context": "https://schema.org", "@type": "FurnitureStore", name: "D'CASA Panamá" },
      json_ld_organizacion: { "@context": "https://schema.org", "@type": "Organization", name: "D'CASA Panamá" },
    },
    empresa: {
      nombre: "D'CASA Panamá",
      ruc: "155779346-2-2026 DV7",
      calle: "Avenida Las Américas, Urbanización Santa Clara, Local 4550 PB-1",
      ciudad: "La Chorrera",
      telefono: "+507 6026-1919",
      email: "info@dcasapty.com",
      latitud: 8.8765881,
      longitud: -79.7867962,
    },
    socios: { puntos_por_dolar: 1, puntos_al_padrino: 500, puntos_al_ahijado: 250 },
    portada: {
      seo: { titulo: "Mueblería en La Chorrera | D'CASA Panamá", descripcion: "Recámaras, colchones…" },
      categorias: [
        { nombre: "Salas", url: "/shop/category/salas-3", imagen: "/website_dcasa/static/src/img/cat-salas.webp", alt: "Sala" },
      ],
      mas_buscados: productos.slice(0, 8).map((p) => p.id),
      para_dormir: [],
      para_dormir_url: "/shop/category/recamaras-4",
    },
    tienda: { descripcion: "Tienda en línea de D'CASA Panamá." },
    categorias: [
      { id: 3, nombre: "Salas", padre_id: null, secuencia: 1, url: "/shop/category/salas-3", seo: { titulo: "", descripcion: "" } },
      { id: 4, nombre: "Recámaras", padre_id: null, secuencia: 2, url: "/shop/category/recamaras-4", seo: { titulo: "", descripcion: "" } },
      { id: 5, nombre: "Sofás", padre_id: 3, secuencia: 3, url: "/shop/category/sofas-5", seo: { titulo: "", descripcion: "" } },
    ],
    productos,
    paginas: {
      "/privacidad": { titulo: "Política de privacidad", descripcion: "Qué datos…", actualizado: "1 de octubre de 2026", html: "<h2>Quiénes somos</h2><p>Ley 81 de 2019</p>" },
      "/terminos": { titulo: "Términos y condiciones", descripcion: "Cómo…", actualizado: "1 de octubre de 2026", html: "<p>no incluyen el ITBMS</p>" },
    },
  };
}

/** Feed con la campaña Black Weekend (producto 1 marcado; 2 normal; 3 con color destacado). */
export function feedBlackWeekend(activo = true): Feed {
  const feed = feedEjemplo([producto(1, { black_weekend: true }), producto(2), producto(3, { black_weekend: true, compra: "variantes" })]);
  const item = (id: number, extra: Partial<ProductoBlackWeekend> = {}): ProductoBlackWeekend => ({
    id,
    variante_id: id * 10,
    nombre: `Cama BW ${id}`,
    codigo: `BW-${id}`,
    url: `/shop/mueble-${id}-${id}`,
    precio: 259.99,
    precio_visible: true,
    mas_itbms: true,
    moneda: "USD",
    combo: { texto: "Combo con colchón First Class", precio: 469.99 },
    compra: "directa",
    whatsapp: `https://wa.me/50760261919?text=Hola%20D'CASA%2C%20me%20interesa%20del%20Black%20Weekend%3A%20Cama%20BW%20${id}%20(c%C3%B3digo%20BW-${id})`,
    imagen: {
      image_256: `/web/image/product.product/${id * 10}/image_256`,
      image_512: `/web/image/product.product/${id * 10}/image_512`,
      image_1024: `/web/image/product.product/${id * 10}/image_1024`,
      image_1920: `/web/image/product.product/${id * 10}/image_1920`,
      foto: { base: `/dcasa/img/product.product/${id * 10}/image_variant_1920`, v: "abcdefabcdef" },
    },
    ...extra,
  });
  feed.black_weekend = {
    activo,
    forzado: false,
    inicio: "2026-10-05",
    fin: "2026-10-11",
    zona: "America/Panama",
    fechas: "del 5 al 11 de octubre de 2026",
    ruta: "/black-weekend",
    descripcion: "Black Weekend en D'CASA Panamá del 5 al 11 de octubre de 2026: 2 camas y bases seleccionadas.",
    og_imagen: "https://dcasapty.com/website_dcasa/static/src/img/black_weekend/og.jpg",
    og_imagen_ancho: 1080,
    og_imagen_alto: 1350,
    json_ld: {
      "@context": "https://schema.org",
      "@type": "ItemList",
      numberOfItems: 2,
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "Cama BW 1", url: "https://dcasapty.com/shop/mueble-1-1" },
        { "@type": "ListItem", position: 2, name: "Cama BW 3", url: "https://dcasapty.com/shop/mueble-3-3" },
      ],
    },
    productos: [item(1), item(3, { compra: "variantes", codigo: "BW-3-NEGRO", combo: null, precio: 229.99 })],
  };
  return feed;
}

/** Almacén en memoria con la misma interfaz que KV. */
export function almacenMemoria() {
  const datos = new Map<string, { texto: string; meta?: Record<string, string> }>();
  let escrituras = 0;
  let borrados = 0;
  return {
    datos,
    get escrituras() {
      return escrituras;
    },
    get borrados() {
      return borrados;
    },
    async leer(clave: string) {
      return datos.get(clave) ?? null;
    },
    async escribir(clave: string, texto: string, meta?: Record<string, string>) {
      escrituras++;
      datos.set(clave, { texto, meta });
    },
    async borrar(clave: string) {
      borrados++;
      datos.delete(clave);
    },
  };
}
