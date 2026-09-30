/**
 * Filtros rápidos: debajo del buscador de cada lista, los filtros que la pantalla ya trae
 * (Por pagar, Vencidas, Disponibles, Rango de precio…) como botones de un clic.
 *
 * Nada que armar: sin «campos», «operadores» ni condiciones. Un clic filtra, otro clic
 * quita el filtro; filtros del mismo grupo se suman (uno u otro), como en Odoo.
 */
import { Component, useState } from "@odoo/owl";
import { useBus } from "@web/core/utils/hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";

const VISTAS = ["list", "kanban"];
const MAXIMO = 12;

export class DcasaFiltrosRapidos extends Component {
    static template = "dcasa_interfaz.FiltrosRapidos";
    static props = {};

    setup() {
        this.state = useState({ version: 0 });
        if (this.env.searchModel) {
            useBus(this.env.searchModel, "update", () => this.state.version++);
        }
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
