/**
 * «Ya existe esta persona» al crear un cliente (pedido de la dueña, 2026-11-04).
 *
 * Mientras se escribe un cliente nuevo (en «Crear y editar» de la cotización o la factura, en Nuevo cliente o en
 * Contactos), si el celular, el correo o la cédula ya son de otra ficha, aquí sale esa ficha con sus datos para
 * verificar que es la misma persona; si no, las de nombre parecido. «Es esta persona» abre ESA ficha en la misma
 * ventana con lo que se escribió encima (nombre, correo, cédula…): se revisa y se guarda. Desde una cotización o una
 * factura, al guardar queda elegida como cliente: nada de lo que se estaba haciendo se pierde.
 *
 * No hay atajo en el servidor: es la edición normal de esa ficha, con sus reglas y permisos de siempre.
 */
import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

// Lo que se escribió y pasa a la ficha que ya existe: los datos de texto que se ven en la ficha.
const CAMPOS = ["name", "phone", "dcasa_telefono_fijo", "email", "vat", "street", "street2", "city", "zip", "function"];

const soloDigitos = (texto) => String(texto || "").replace(/\D/g, "");
// Lo que «Crear y editar» pone como nombre cuando se buscó un celular o un correo: no es un nombre.
const pareceTelefono = (texto) => soloDigitos(texto).length >= 4 && String(texto).replace(/\s/g, "").length - soloDigitos(texto).length <= 3;
const mismoTelefono = (a, b) => soloDigitos(a).slice(-8) === soloDigitos(b).slice(-8) && soloDigitos(a).length >= 7;

export class DcasaCoincidencias extends Component {
    static template = "dcasa_contactos.Coincidencias";
    static props = { ...standardFieldProps };

    setup() {
        this.notification = useService("notification");
    }

    get lista() {
        return this.props.record.data[this.props.name] || [];
    }

    get hayFuertes() {
        return this.lista.some((c) => c.fuerte);
    }

    /** Lo escrito en la ficha nueva que vale la pena llevar a la que ya existe. */
    loEscrito() {
        const datos = this.props.record.data;
        const escrito = {};
        for (const campo of CAMPOS) {
            const valor = datos[campo];
            if (!(campo in datos) || typeof valor !== "string" || !valor.trim()) {
                continue;
            }
            if (campo === "name" && (pareceTelefono(valor) || valor.includes("@"))) {
                continue;
            }
            escrito[campo] = valor.trim();
        }
        if (datos.dcasa_sin_correo && !escrito.email) {
            escrito.dcasa_sin_correo = true;
        }
        return escrito;
    }

    async usar(coincidencia) {
        const model = this.props.record.model;
        const escrito = this.loEscrito();
        await model.load({ resId: coincidencia.id, resIds: [coincidencia.id] });
        const ficha = model.root;
        const cambios = {};
        for (const [campo, valor] of Object.entries(escrito)) {
            if (!(campo in ficha.data)) {
                continue;
            }
            // Una empresa no toma el nombre ni la cédula de la persona que se estaba escribiendo.
            if ((coincidencia.empresa || ficha.data.is_company) && (campo === "name" || campo === "vat")) {
                continue;
            }
            if (campo === "phone" && mismoTelefono(valor, ficha.data.phone)) {
                continue;
            }
            if (campo === "email" && valor.toLowerCase() === String(ficha.data.email || "").toLowerCase()) {
                continue;
            }
            if (ficha.data[campo] !== valor) {
                cambios[campo] = valor;
            }
        }
        if (coincidencia.archivada && "active" in ficha.data) {
            cambios.active = true;
        }
        if (Object.keys(cambios).length) {
            await ficha.update(cambios);
        }
        this.notification.add(
            Object.keys(cambios).length
                ? _t("Abrimos la ficha que ya existía con lo que escribiste encima. Revisa y toca «Guardar».")
                : _t("Abrimos la ficha que ya existía. Revisa sus datos y toca «Guardar»."),
            { type: "info", title: coincidencia.nombre }
        );
    }
}

export const dcasaCoincidencias = {
    component: DcasaCoincidencias,
    displayName: _t("Ya existe esta persona (D'CASA)"),
    supportedTypes: ["json"],
};

registry.category("fields").add("dcasa_coincidencias", dcasaCoincidencias);
