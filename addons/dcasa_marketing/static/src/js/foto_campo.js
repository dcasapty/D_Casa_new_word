/**
 * La foto del producto que se toca para verla en grande (ficha, lista y tarjetas de Productos) y el botón de la galería
 * en la pestaña Ventas. Antes la foto solo se agrandaba un poco al pasar el mouse y seguía siendo muy pequeña.
 *
 * - En un producto ya guardado, tocar la foto abre las fotos en grande (dcasa_marketing.Fotos); sin foto, abre la
 *   galería para subirlas. Si la ficha tenía cambios sin guardar, se guardan antes (si no se pueden guardar, no abre).
 * - En un producto nuevo (sin guardar) queda el cargador de Odoo de siempre: no hay dónde guardar las fotos extra.
 * - Al cerrar, si algo cambió, se recarga el producto para ver la foto nueva.
 */
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ImageField, imageField } from "@web/views/fields/image/image_field";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { abrirFotos } from "./fotos_dialogo";

function plantillaDe(record) {
    if (record.resModel === "product.template") {
        return record.resId;
    }
    const plantilla = record.data.product_tmpl_id;
    return (plantilla && (plantilla.id || plantilla[0])) || false;
}

async function guardarSiHaceFalta(record) {
    if (record.isInEdition && (await record.isDirty())) {
        return await record.save();
    }
    return true;
}

export class DcasaFotoProducto extends ImageField {
    static template = "dcasa_marketing.FotoProducto";

    setup() {
        super.setup();
        this.dialogo = useService("dialog");
    }

    get conFoto() {
        return Boolean(this.props.record.data[this.props.name]) && this.state.isValid;
    }

    get puedeAbrir() {
        return Boolean(this.props.record.resId && plantillaDe(this.props.record));
    }

    get etiqueta() {
        return this.conFoto ? "Ver las fotos en grande" : "Agregar fotos";
    }

    async abrir() {
        const record = this.props.record;
        if (!(await guardarSiHaceFalta(record))) {
            return;
        }
        abrirFotos(this.dialogo, {
            plantillaId: plantillaDe(record),
            modo: this.conFoto ? "visor" : "galeria",
            alCambiar: () => record.load(),
        });
    }
}

export const dcasaFotoProducto = {
    ...imageField,
    component: DcasaFotoProducto,
    displayName: "Foto del producto (D'CASA)",
};

registry.category("fields").add("dcasa_foto_producto", dcasaFotoProducto);

/** Pestaña Ventas: «Fotos del producto» abre la galería (subir varias, ordenar, elegir la principal). */
export class DcasaGaleriaFotos extends Component {
    static template = "dcasa_marketing.GaleriaFotos";
    static props = { ...standardWidgetProps };

    setup() {
        this.dialogo = useService("dialog");
    }

    get cuantas() {
        const data = this.props.record.data;
        const extras = data.product_template_image_ids ? data.product_template_image_ids.records.length : 0;
        return (data.image_1920 ? 1 : 0) + extras;
    }

    async abrir() {
        const record = this.props.record;
        if (!record.resId || !(await guardarSiHaceFalta(record))) {
            return;
        }
        abrirFotos(this.dialogo, { plantillaId: record.resId, modo: "galeria", alCambiar: () => record.load() });
    }
}

registry.category("view_widgets").add("dcasa_galeria_fotos", {
    component: DcasaGaleriaFotos,
    fieldDependencies: [{ name: "image_1920", type: "binary" }],
});
