/**
 * Listas: el ancho de las columnas.
 *
 * 1. Las fechas (computadora y celular).
 *
 * Odoo reserva para cada fecha el ancho del peor caso: con el año y con segundos («25 sept 2017, 10:00:00 p. m.»).
 * Casi todas las filas son de este año y sin segundos («11 nov, 12:14 a. m.»), así que en una pantalla de 1366 px esa
 * reserva dejaba un hueco en blanco y apretaba las columnas de al lado (la vendedora, el estado). Aquí la columna puede
 * encogerse hasta lo que mide una fecha de este año, y crecer hasta el ancho de Odoo cuando sobra espacio o cuando hay
 * fechas de otros años.
 *
 * No se tocan los campos de Odoo: se registran copias de los campos de fecha de las listas con otro `listViewWidth`
 * (el rango de fechas, que calcula con los originales, sigue igual).
 *
 * 2. El texto, en el celular.
 *
 * Odoo deja encoger cada columna de texto hasta 80 px. En una pantalla de 390 px, una lista de seis columnas quedaba en
 * «CAM…», «Client…», «+507…»: no se podía leer nada (48 de las 105 listas del panel, auditoría del 2026-11-11). En el
 * celular las columnas de texto no bajan de un ancho que se lee y la lista se desliza de lado, como ya hacía. Solo la
 * lista de la pantalla: las líneas de un formulario (productos de la cotización) siguen como estaban.
 */
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { toLocaleDateString, toLocaleDateTimeString } from "@web/core/l10n/dates";
import { exprToBoolean } from "@web/core/utils/strings";
import { dateField, dateTimeField } from "@web/views/fields/datetime/datetime_field";
import { listDateField, listDateTimeField } from "@web/views/fields/datetime/list_datetime_field";
import { ListRenderer } from "@web/views/list/list_renderer";

const { DateTime } = luxon;
let _deEsteAno = null;

/** Lo más ancho que sale una fecha de ESTE año (sin el año) y sin segundos, medido con la letra de la página. */
export function anchosDeEsteAno() {
    if (!_deEsteAno) {
        const ano = DateTime.local().year;
        const textos = { date: [], datetime: [] };
        for (let mes = 1; mes <= 12; mes++) {
            textos.date.push(toLocaleDateString(DateTime.local(ano, mes, 20)));
            for (const hora of [10, 22]) {
                textos.datetime.push(
                    toLocaleDateTimeString(DateTime.local(ano, mes, 25, hora, 0, 0), { showSeconds: false })
                );
            }
        }
        const caja = document.createElement("div");
        caja.style.cssText =
            "position:absolute;left:0;top:0;visibility:hidden;white-space:nowrap;font-variant-numeric:tabular-nums;";
        document.body.append(caja);
        _deEsteAno = {};
        for (const [clave, lista] of Object.entries(textos)) {
            let maximo = 0;
            for (const texto of lista) {
                const span = document.createElement("span");
                span.textContent = texto;
                caja.replaceChildren(span);
                maximo = Math.max(maximo, span.getBoundingClientRect().width);
            }
            // 5 % de margen, como Odoo, por si la fila va en negrita.
            _deEsteAno[clave] = Math.ceil(maximo * 1.05);
        }
        caja.remove();
    }
    return _deEsteAno;
}

/** [mínimo, máximo]: de «una fecha de este año» a «lo que reserva Odoo». Si Odoo ya da algo más angosto, se respeta. */
function entre(minimo, deOdoo) {
    return typeof deOdoo === "number" && minimo > 0 && minimo < deOdoo ? [minimo, deOdoo] : deOdoo;
}

export function anchoDeFecha(info) {
    const deOdoo = dateField.listViewWidth(info);
    return info.options?.numeric ? deOdoo : entre(anchosDeEsteAno().date, deOdoo);
}

export function anchoDeFechaConHora(info) {
    const opciones = info.options || {};
    const deOdoo = dateTimeField.listViewWidth(info);
    if (opciones.numeric || exprToBoolean(opciones.show_seconds ?? false)) {
        return deOdoo;
    }
    const conHora = exprToBoolean(opciones.show_time ?? true);
    return entre(conHora ? anchosDeEsteAno().datetime : anchosDeEsteAno().date, deOdoo);
}

// Las listas usan sus propios campos de fecha («list.date», «list.datetime»): son los que se cambian.
registry
    .category("fields")
    .add("list.date", { ...listDateField, listViewWidth: anchoDeFecha }, { force: true })
    .add("list.datetime", { ...listDateTimeField, listViewWidth: anchoDeFechaConHora }, { force: true });

// --- El texto, en el celular ---------------------------------------------------------------------------------------

/** En el celular, una columna de este tipo no baja de este ancho (px, sin contar el relleno de la celda). */
export const MINIMO_EN_CELULAR = Object.freeze({
    char: 170,
    many2one: 170,
    reference: 170,
    many2one_reference: 170,
    many2many: 170,
    one2many: 170,
    selection: 104,
    text: 200,
    html: 200,
});

// La misma copia en cada dibujado: si cambiara, Odoo volvería a pintar todas las celdas.
const copias = new WeakMap();

/** La columna con su mínimo de celular; la misma si no es de texto o si ya trae un ancho propio (fechas, montos…). */
export function columnaParaCelular(columna) {
    const minimo = MINIMO_EN_CELULAR[columna.fieldType];
    if (columna.type !== "field" || !minimo || !columna.field || columna.field.listViewWidth || columna.attrs?.width) {
        return columna;
    }
    if (!copias.has(columna)) {
        copias.set(columna, { ...columna, field: { ...columna.field, listViewWidth: [minimo] } });
    }
    return copias.get(columna);
}

patch(ListRenderer.prototype, {
    getActiveColumns() {
        const columnas = super.getActiveColumns(...arguments);
        return this.env.isSmall && !this.isX2Many ? columnas.map(columnaParaCelular) : columnas;
    },
});
