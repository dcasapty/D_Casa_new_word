import type { Feed, ProductoFeed } from "../src/tienda/tipos";

const imagen = (id: number) => {
  const u = (t: string) => `/web/image/product.template/${id}/${t}?unique=abc1234`;
  return { image_256: u("image_256"), image_512: u("image_512"), image_1024: u("image_1024"), image_1920: u("image_1920") };
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
