/**
 * Filtros rápidos: debajo del buscador de cada lista, los filtros que la pantalla ya trae
 * (Por pagar, Vencidas, Disponibles, Rango de precio…) como botones de un clic.
 *
 * Nada que armar: sin «campos», «operadores» ni condiciones. Un clic filtra, otro clic
 * quita el filtro; filtros del mismo grupo se suman (uno u otro), como en Odoo.
 *
 * En la lista de Productos, además, «Ordenar»: mayor o menor stock y mayor o menor precio, también de un clic
 * (marketing elige qué empujar en una campaña). Solo cambian el orden: los filtros y la categoría elegidos se
 * quedan, así «camas» + «Disponibles» + «Mayor stock» se arma en tres clics. Otro clic en el mismo botón vuelve
 * al orden de siempre.
 */
import { Component, useState } from "@odoo/owl";
import { useBus } from "@web/core/utils/hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";

const VISTAS = ["list", "kanban"];
const MAXIMO = 12;

/** Botones de orden por modelo (solo en la vista de lista, que es donde se ordena). */
export const ORDENES = {
    "product.template": [
        { clave: "stock_desc", etiqueta: "Mayor stock", campo: "dcasa_stock", asc: false },
        { clave: "stock_asc", etiqueta: "Menor stock", campo: "dcasa_stock", asc: true },
        { clave: "precio_desc", etiqueta: "Mayor precio", campo: "list_price", asc: false },
        { clave: "precio_asc", etiqueta: "Menor precio", campo: "list_price", asc: true },
    ],
};

export class DcasaFiltrosRapidos extends Component {
    static template = "dcasa_interfaz.FiltrosRapidos";
    static props = {};

    setup() {
        this.state = useState({ version: 0 });
        if (this.env.searchModel) {
            useBus(this.env.searchModel, "update", () => this.state.version++);
        }
        // El orden vive en el modelo de la lista: este componente se suscribe a él para redibujar los botones cuando
        // cambia (con ellos o con el título de una columna).
        this.lista = this.env.model ? useState(this.env.model) : null;
    }

    get visible() {
        return Boolean(this.env.searchModel) && VISTAS.includes(this.env.config?.viewType) && this.filtros.length > 0;
    }

    get filtros() {
        this.state.version;
        const modelo = this.env.searchModel;
        if (!modelo) {
            return [];
        }
        return modelo
            .getSearchItems((item) => item.type === "filter" && item.description)
            .sort((a, b) => a.groupNumber - b.groupNumber)
            .slice(0, MAXIMO);
    }

    /** Botones de orden de esta pantalla: solo en lista, sin agrupar (agrupado el orden es el de los grupos). */
    get ordenes() {
        this.state.version;
        const lista = this.lista?.root;
        const modelo = this.env.searchModel?.resModel;
        if (this.env.config?.viewType !== "list" || !lista || !ORDENES[modelo] || lista.groupBy?.length) {
            return [];
        }
        const actual = lista.orderBy?.[0];
        return ORDENES[modelo].map((orden) => ({
            ...orden,
            activo: Boolean(actual) && actual.name === orden.campo && Boolean(actual.asc) === orden.asc,
        }));
    }

    async ordenar(orden) {
        // Segundo clic en el mismo botón: vuelve al orden por defecto de la pantalla.
        const orderBy = orden.activo ? [] : [{ name: orden.campo, asc: orden.asc }];
        await this.lista.root.load({ orderBy });
    }

    get hayActivos() {
        return this.filtros.some((f) => f.isActive);
    }

    // El filtro anterior es de otro grupo: se dibuja un separador fino.
    nuevoGrupo(filtro, indice) {
        return indice > 0 && this.filtros[indice - 1].groupNumber !== filtro.groupNumber;
    }

    alternar(filtro) {
        this.env.searchModel.toggleSearchItem(filtro.id);
    }

    limpiar() {
        for (const filtro of this.filtros.filter((f) => f.isActive)) {
            this.env.searchModel.toggleSearchItem(filtro.id);
        }
    }
}

ControlPanel.components = { ...ControlPanel.components, DcasaFiltrosRapidos };
