/**
 * «Busca con una foto» (views/templates.xml, controllers/main.py).
 *
 * El botón es una <label> con el <input type="file" accept="image/*"> encima: el toque abre el selector del teléfono
 * (cámara o galería) sin JavaScript. Al elegir la foto:
 *
 *   1. Se ve «Buscando muebles parecidos…» (una capa encima de todo, que el lector de pantalla anuncia).
 *   2. La foto se achica en el navegador: lado mayor de 1024 px como mucho, JPEG (una captura de Instagram o una foto de
 *      12 MP queda en unos cientos de KB). Si el navegador no la puede abrir, se manda tal cual si es JPEG, PNG o WebP
 *      de hasta 1,5 MB; si no, se avisa al lado del botón.
 *   3. Se pide un token CSRF fresco (las páginas pueden venir de la caché del borde, con el token de otra sesión) y se
 *      envía un formulario normal a /shop/foto con la foto en base64 en un campo de texto: la respuesta es la página
 *      de resultados. Nada de la foto queda en el navegador (ni en localStorage, ni en el historial).
 *
 * En la página de resultados, el historial se reemplaza por /shop/foto (GET): «recargar» no reenvía la foto.
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

export const LADO_MAXIMO = 1024;
export const CALIDAD_JPEG = 0.85;
export const MAX_BYTES = 1536 * 1024;
export const TIPOS = ["image/jpeg", "image/png", "image/webp"];
export const RUTA = "/shop/foto";
export const TEXTO_CARGANDO = "Buscando muebles parecidos…";
export const TEXTO_NO_ABRE = "Esa foto no la pudimos abrir. Prueba con otra en JPG, PNG o WebP de menos de 1,5 MB.";

/** Medidas para que el lado mayor no pase de `maximo` (nunca agranda). */
export function medidasReducidas(ancho, alto, maximo = LADO_MAXIMO) {
    if (!(ancho > 0 && alto > 0)) {
        return null;
    }
    const escala = Math.min(1, maximo / Math.max(ancho, alto));
    return { ancho: Math.max(1, Math.round(ancho * escala)), alto: Math.max(1, Math.round(alto * escala)) };
}

/** La imagen ya decodificada (con la orientación de la cámara aplicada), o null si el navegador no la puede abrir. */
async function abrirImagen(archivo) {
    if (window.createImageBitmap) {
        try {
            return await createImageBitmap(archivo, { imageOrientation: "from-image" });
        } catch {
            // se prueba con <img>
        }
    }
    const url = URL.createObjectURL(archivo);
    try {
        return await new Promise((resolver) => {
            const img = new Image();
            img.onload = () => resolver(img);
            img.onerror = () => resolver(null);
            img.src = url;
        });
    } finally {
        URL.revokeObjectURL(url);
    }
}

function leerComoBase64(archivo) {
    return new Promise((resolver) => {
        const lector = new FileReader();
        lector.onload = () => resolver(String(lector.result || "").split(",")[1] || null);
        lector.onerror = () => resolver(null);
        lector.readAsDataURL(archivo);
    });
}

/** La foto lista para enviar (base64, sin el prefijo `data:`), o null si no se puede. */
export async function prepararFoto(archivo) {
    if (!archivo) {
        return null;
    }
    const imagen = await abrirImagen(archivo);
    const medidas = imagen && medidasReducidas(imagen.width, imagen.height);
    if (medidas) {
        const lienzo = document.createElement("canvas");
        lienzo.width = medidas.ancho;
        lienzo.height = medidas.alto;
        const ctx = lienzo.getContext("2d");
        ctx.fillStyle = "#FFFFFF"; // un PNG transparente no sale negro en JPEG
        ctx.fillRect(0, 0, medidas.ancho, medidas.alto);
        ctx.drawImage(imagen, 0, 0, medidas.ancho, medidas.alto);
        imagen.close?.();
        const base64 = lienzo.toDataURL("image/jpeg", CALIDAD_JPEG).split(",")[1];
        lienzo.width = lienzo.height = 0;
        if (base64) {
            return base64;
        }
    }
    if (TIPOS.includes(archivo.type) && archivo.size > 0 && archivo.size <= MAX_BYTES) {
        return leerComoBase64(archivo);
    }
    return null;
}

/** Token CSRF de ESTA sesión (dcasa_tienda_borde); si esa ruta no está, el de la página. */
export async function tokenCsrf() {
    try {
        const respuesta = await fetch("/dcasa/borde/csrf", {
            credentials: "same-origin",
            cache: "no-store",
            headers: { Accept: "application/json" },
        });
        if (respuesta.ok) {
            const datos = await respuesta.json();
            if (datos?.csrf_token) {
                return datos.csrf_token;
            }
        }
    } catch {
        // sin red o sin la ruta: el de la página
    }
    return window.odoo?.csrf_token || "";
}

function campo(nombre, valor) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = nombre;
    input.value = valor;
    return input;
}

/** Un formulario normal (no fetch): la respuesta es la página de resultados, con el «atrás» del navegador de siempre. */
export function enviar(base64, token) {
    const formulario = document.createElement("form");
    formulario.method = "post";
    formulario.action = RUTA;
    formulario.enctype = "multipart/form-data";
    formulario.className = "d-none";
    formulario.append(campo("csrf_token", token), campo("foto", base64));
    document.body.appendChild(formulario);
    formulario.submit();
}

let capa = null;

export function mostrarCargando() {
    if (!capa) {
        capa = document.createElement("div");
        capa.className = "o_dcasa_foto_cargando";
        capa.setAttribute("role", "status");
        capa.setAttribute("aria-live", "assertive");
        const caja = document.createElement("div");
        caja.className = "o_dcasa_foto_cargando_caja";
        const giro = document.createElement("span");
        giro.className = "o_dcasa_foto_giro";
        giro.setAttribute("aria-hidden", "true");
        const titulo = document.createElement("p");
        titulo.className = "o_dcasa_foto_cargando_titulo";
        titulo.textContent = TEXTO_CARGANDO;
        const sub = document.createElement("p");
        sub.className = "o_dcasa_foto_cargando_sub";
        sub.textContent = "Estamos mirando tu foto. Tarda unos segundos.";
        caja.append(giro, titulo, sub);
        capa.append(caja);
    }
    document.body.appendChild(capa);
    document.documentElement.classList.add("o_dcasa_foto_ocupado");
}

export function ocultarCargando() {
    capa?.remove();
    document.documentElement.classList.remove("o_dcasa_foto_ocupado");
}

/** El aviso va debajo del botón o, si el botón está dentro de una caja de búsqueda, debajo de la caja (no dentro). */
function avisar(boton, texto) {
    const ancla = boton.closest(".o_searchbar_form") ?? boton;
    let aviso = ancla.parentElement?.querySelector(":scope > .o_dcasa_foto_aviso");
    if (!aviso) {
        aviso = document.createElement("p");
        aviso.className = "o_dcasa_foto_aviso";
        aviso.setAttribute("role", "alert");
        ancla.insertAdjacentElement("afterend", aviso);
    }
    aviso.textContent = texto;
}

export class DcasaBuscarFoto extends Interaction {
    static selector = "[data-dcasa-foto]";
    dynamicContent = {
        ".o_dcasa_foto_archivo": { "t-on-change.noUpdate": this.alElegir },
        _window: { "t-on-pageshow.noUpdate": this.alVolver },
    };

    async alElegir(ev) {
        const input = ev.currentTarget;
        const archivo = input.files?.[0];
        if (!archivo || this.ocupado) {
            return;
        }
        this.ocupado = true;
        mostrarCargando();
        try {
            const base64 = await prepararFoto(archivo);
            if (!base64) {
                ocultarCargando();
                avisar(this.el, TEXTO_NO_ABRE);
                return;
            }
            enviar(base64, await tokenCsrf());
        } catch {
            ocultarCargando();
            avisar(this.el, TEXTO_NO_ABRE);
        } finally {
            this.ocupado = false;
            input.value = ""; // la misma foto se puede volver a elegir; y no queda nada en el input
        }
    }

    /** Volver atrás desde los resultados (caché de páginas del navegador): la capa no puede quedar puesta. */
    alVolver(ev) {
        if (ev.persisted) {
            ocultarCargando();
        }
    }
}

/** En la página de resultados: «recargar» abre /shop/foto (GET) y no vuelve a mandar la foto. */
export class DcasaFotoSinReenvio extends Interaction {
    static selector = ".o_dcasa_foto_pagina";

    start() {
        if (window.location.pathname === RUTA && this.el.dataset.estado !== "inicio") {
            try {
                window.history.replaceState(window.history.state, "", RUTA);
            } catch {
                // sin historial: no pasa nada
            }
        }
    }
}

const interacciones = registry.category("public.interactions");
interacciones.add("dcasa_buscar_foto.buscar_foto", DcasaBuscarFoto);
interacciones.add("dcasa_buscar_foto.sin_reenvio", DcasaFotoSinReenvio);
