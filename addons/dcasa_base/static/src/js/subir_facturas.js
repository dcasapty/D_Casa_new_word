/**
 * «Subir» en Facturas, solo a quien puede hacer facturas ahí (cabo suelto del 2026-10-22).
 *
 * A quien no cobra (la Vendedora) el servidor ya le quita «Nuevo» en Facturación › Facturas (`create="0"`,
 * models/cobros.py) y le rechaza la factura suelta: ella cotiza y factura desde el pedido. Subir un PDF también crea una
 * factura suelta, así que donde la lista o las tarjetas no ofrecen «Nuevo» tampoco se ofrece «Subir», ni soltar o pegar
 * un archivo encima. Vale para cualquier lista de asientos con `create="0"`: subir siempre crea.
 */
import { patch } from "@web/core/utils/patch";
import { AccountMoveKanbanController } from "@account/views/account_move_kanban/account_move_kanban_controller";
import { AccountMoveListController } from "@account/views/account_move_list/account_move_list_controller";
import { FileUploadKanbanRenderer } from "@account/views/file_upload_kanban/file_upload_kanban_renderer";
import { FileUploadListRenderer } from "@account/views/file_upload_list/file_upload_list_renderer";

const puedeCrear = (activeActions) => activeActions?.create !== false;

for (const Controlador of [AccountMoveListController, AccountMoveKanbanController]) {
    patch(Controlador.prototype, {
        setup() {
            super.setup(...arguments);
            if (!puedeCrear(this.props.archInfo?.activeActions)) {
                this.showUploadButton = false;
            }
        },
    });
}

patch(FileUploadListRenderer.prototype, {
    onDragStart(ev) {
        if (puedeCrear(this.props.activeActions)) {
            return super.onDragStart(ev);
        }
    },
    async onPaste(ev) {
        if (puedeCrear(this.props.activeActions)) {
            return super.onPaste(ev);
        }
    },
});

patch(FileUploadKanbanRenderer.prototype, {
    onDragStart(ev) {
        if (puedeCrear(this.props.archInfo?.activeActions)) {
            return super.onDragStart(ev);
        }
    },
    async onPaste(ev) {
        if (puedeCrear(this.props.archInfo?.activeActions)) {
            return super.onPaste(ev);
        }
    },
});
