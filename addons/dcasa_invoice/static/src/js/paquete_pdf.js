/**
 * «Imprimir documentos» (dcasa_invoice): el navegador pide el PDF unido al servidor, lo guarda solo en memoria
 * (un blob) y lo imprime o lo descarga. Nunca deja un archivo en la carpeta Descargas salvo en «Descargar».
 *
 * Imprimir: iframe fuera de la pantalla con el blob; al cargar se llama a contentWindow.print(). Si el
 * navegador no deja imprimir desde el iframe, plan B: abrir el PDF en una pestaña con el visor (que trae su
 * propio botón de imprimir); si el navegador bloquea la pestaña, un aviso con un enlace.
 */
import { markup } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

// Lo que se espera a que cargue el visor del iframe antes de pasar al plan B.
const ESPERA_CARGA_MS = 8000;
// Un respiro entre «cargó» y print(): el visor de Firefox imprime en blanco si se llama antes de estar listo.
const RESPIRO_MS = 400;
// El iframe y el blob viven lo que tarda el cuadro de impresión en tomarlos; después se sueltan.
const VIDA_IFRAME_MS = 2 * 60 * 1000;
const VIDA_ENLACE_MS = 10 * 60 * 1000;

export async function pedirPdf(url) {
    let respuesta;
    try {
        respuesta = await fetch(url, { credentials: "same-origin" });
    } catch {
        throw new Error(_t("No se pudo conectar con el servidor. Revisa tu internet e inténtalo otra vez."));
    }
    if (!respuesta.ok) {
        const mensaje = ((await respuesta.text().catch(() => "")) || "").slice(0, 300);
        throw new Error(mensaje || _t("No se pudo armar el PDF."));
    }
    return await respuesta.blob();
}

export function descargarBlob(blob, nombre) {
    const url = URL.createObjectURL(blob);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download = nombre || "documentos.pdf";
    enlace.style.display = "none";
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60 * 1000);
}

/** Abre el cuadro de impresión con el PDF. Devuelve true si llamó a print(), false si hay que ir al plan B. */
export function imprimirBlob(blob) {
    return new Promise((resolve) => {
        const url = URL.createObjectURL(blob);
        const iframe = document.createElement("iframe");
        iframe.className = "o_dcasa_paquete_iframe";
        iframe.setAttribute("aria-hidden", "true");
        iframe.tabIndex = -1;
        // Fuera de la pantalla pero con tamaño real: un iframe oculto del todo no imprime en Chrome.
        iframe.style.cssText =
            "position:fixed;left:-10000px;top:0;width:900px;height:1200px;border:0;opacity:0;pointer-events:none;";
        let resuelto = false;
        const soltar = () =>
            setTimeout(() => {
                iframe.remove();
                URL.revokeObjectURL(url);
            }, VIDA_IFRAME_MS);
        const terminar = (llamo) => {
            if (resuelto) {
                return;
            }
            resuelto = true;
            resolve(llamo);
            soltar();
        };
        iframe.addEventListener("load", () => {
            if (resuelto) {
                return;
            }
            setTimeout(() => {
                try {
                    iframe.contentWindow.focus();
                    iframe.contentWindow.print();
                    terminar(true);
                } catch {
                    terminar(false);
                }
            }, RESPIRO_MS);
        });
        setTimeout(() => terminar(false), ESPERA_CARGA_MS);
        iframe.src = url;
        document.body.appendChild(iframe);
    });
}

/** Plan B: el PDF en una pestaña con el visor del navegador; si la bloquea, un aviso con el enlace. */
export function abrirEnPestana(blob, notificaciones) {
    const url = URL.createObjectURL(blob);
    const pestana = window.open(url, "_blank");
    if (!pestana) {
        notificaciones.add(
            markup`${_t("Tu navegador no dejó abrir la impresión solo.")} <a href="${url}" target="_blank">${_t(
                "Abrir el PDF para imprimirlo"
            )}</a>`,
            { type: "warning", sticky: true }
        );
    }
    setTimeout(() => URL.revokeObjectURL(url), VIDA_ENLACE_MS);
}

async function paquetePdf(env, action) {
    const { url, modo, nombre, next } = action.params;
    let blob;
    try {
        blob = await pedirPdf(url);
    } catch (error) {
        // El cuadro se queda abierto para que se pueda corregir y volver a intentar.
        env.services.notification.add(error.message, {
            type: "danger",
            sticky: true,
            title: _t("No se pudo preparar el PDF"),
        });
        return;
    }
    if (modo === "descargar") {
        descargarBlob(blob, nombre);
    } else if (!(await imprimirBlob(blob))) {
        abrirEnPestana(blob, env.services.notification);
    }
    return next;
}

registry.category("actions").add("dcasa_paquete_pdf", paquetePdf);
