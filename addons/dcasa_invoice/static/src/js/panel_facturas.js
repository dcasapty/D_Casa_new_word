/**
 * Facturación › Tablero: dos tarjetas al principio, «Facturas de clientes» y «Facturas de proveedores»,
 * con sus conteos. El servidor decide cuáles puede ver cada persona (dcasa.facturas.panel).
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { DashboardKanbanRenderer } from "@account/views/account_dashboard_kanban/account_dashboard_kanban_renderer";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

export class DcasaFacturasPanel extends Component {
    static template = "dcasa_invoice.FacturasPanel";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({ tarjetas: [] });
        onWillStart(async () => {
            try {
                const datos = await this.orm.call("dcasa.facturas.panel", "obtener_datos", []);
                this.state.tarjetas = datos.tarjetas;
            } catch {
                // Sin el panel, el Tablero sigue como siempre.
                this.state.tarjetas = [];
            }
        });
    }

    async abrir(tarjeta, fila) {
        const accion = await this.orm.call("dcasa.facturas.panel", "abrir", [tarjeta, fila]);
        await this.actionService.doAction(accion);
    }
}

patch(DashboardKanbanRenderer, {
    components: { ...DashboardKanbanRenderer.components, DcasaFacturasPanel },
});
