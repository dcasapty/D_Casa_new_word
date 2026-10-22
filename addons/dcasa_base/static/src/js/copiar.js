/**
 * Copiar con un toque (pedido de la dueña, 2026-10-22): «un ícono de copiar en la mayoría de cosas de productos y
 * clientes: nombre, correo, teléfono, códigos, nombres de productos».
 *
 * Genérico: el campo de un formulario, una lista o una tarjeta que lleve la clase `o_dcasa_copiar` muestra un ícono
 * pequeño al lado del dato. Un toque lo copia y avisa «Copiado». El campo no cambia (el enlace para llamar o escribir
 * del teléfono y del correo sigue igual); el ícono no se lleva el foco al pasar de un campo a otro con el teclado y se
 * esconde mientras el campo está vacío.
 */
import { Component, useRef } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { usePopover } from "@web/core/popover/popover_hook";
import { Tooltip } from "@web/core/tooltip/tooltip";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { Field } from "@web/views/fields/field";

export const CLASE_COPIAR = "o_dcasa_copiar";
const AVISO = "Copiado";
const MILISEGUNDOS = 1200;

/**
 * Copia el texto al portapapeles. `true` si se pudo. Primero el portapapeles del navegador; si no está (una página sin
 * candado, un navegador viejo) o lo niega, el respaldo de siempre: un cuadro de texto escondido y «copiar», que también
 * sirve en el iPhone.
 */
export async function copiarTexto(texto) {
    try {
        if (browser.navigator.clipboard?.writeText) {
            await browser.navigator.clipboard.writeText(texto);
            return true;
        }
    } catch {
        // sigue con el respaldo
    }
    const area = document.createElement("textarea");
    area.value = texto;
    area.setAttribute("readonly", "");
    area.style.cssText = "position:fixed;top:0;left:0;opacity:0;pointer-events:none;";
    document.body.appendChild(area);
    area.select();
    area.setSelectionRange(0, texto.length);
    let copiado = false;
    try {
        copiado = document.execCommand("copy");
    } catch {
        copiado = false;
    }
    area.remove();
    return copiado;
}

/** El valor del campo como texto para copiar ('' si está vacío). */
export function textoDelCampo(record, nombre) {
    const valor = record?.data?.[nombre];
    if (valor === false || valor === null || valor === undefined) {
        return "";
    }
    if (typeof valor === "string") {
        return valor.trim();
    }
    if (typeof valor === "number") {
        return String(valor);
    }
    if (Array.isArray(valor)) {
        return String(valor[1] || "").trim();
    }
    return String(valor.display_name || "").trim();
}

export class DcasaCopiar extends Component {
    static template = "dcasa_base.Copiar";
    static props = { texto: String };

    setup() {
        this.boton = useRef("boton");
        this.popover = usePopover(Tooltip, { position: "top" });
        this.notification = useService("notification");
    }

    async copiar() {
        if (!(await copiarTexto(this.props.texto))) {
            this.notification.add("No se pudo copiar. Mantén el dedo sobre el dato y elige «Copiar».", {
                type: "warning",
            });
            return;
        }
        this.popover.open(this.boton.el, { tooltip: AVISO });
        browser.setTimeout(() => this.popover.close(), MILISEGUNDOS);
    }
}

patch(Field, { components: { ...Field.components, DcasaCopiar } });

patch(Field.prototype, {
    /** El texto a copiar si el campo lleva la clase `o_dcasa_copiar` y tiene algo; si no, ''. */
    get dcasaCopiar() {
        const clases = [this.props.class, this.props.fieldInfo?.attrs?.class]
            .filter((clase) => typeof clase === "string")
            .join(" ")
            .split(/\s+/);
        return clases.includes(CLASE_COPIAR) ? textoDelCampo(this.props.record, this.props.name) : "";
    },
});
