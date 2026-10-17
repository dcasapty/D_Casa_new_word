/**
 * «Enviar por correo» en el diálogo «Cotización en PDF» del panel de Conversaciones (dcasa_conversaciones).
 *
 * Al cargar las cotizaciones se le pregunta al servidor si se puede (`correo_de_cotizacion` → `{puede, motivo,
 * destino}`): con los correos apagados o sin correo del cliente, el botón sale deshabilitado y su `title` dice por qué.
 * Si esa pregunta falla, el diálogo sigue igual (el botón queda deshabilitado).
 */
import { patch } from "@web/core/utils/patch";
import { Almacen } from "@dcasa_conversaciones/js/almacen";
import { DialogoCotizacion } from "@dcasa_conversaciones/js/cotizacion";
import { mensajeDeError } from "@dcasa_conversaciones/js/utilidades";

patch(Almacen.prototype, {
    async cotizacionesAbiertas() {
        const r = await super.cotizacionesAbiertas(...arguments);
        // Se guarda al cargar el diálogo: el botón «Enviar por correo» lo lee de aquí.
        this.correoDeCotizacion = null;
        try {
            this.correoDeCotizacion = await this.orm.silent.call("dcasa.conversacion", "correo_de_cotizacion", [
                this.seleccionadaId,
            ]);
        } catch {
            this.correoDeCotizacion = null;
        }
        return r;
    },
});

patch(DialogoCotizacion.prototype, {
    setup() {
        super.setup(...arguments);
        this.local.enviandoCorreo = false;
    },

    get correo() {
        return this.almacen.correoDeCotizacion || { puede: false, motivo: "", destino: "" };
    },

    get tituloCorreo() {
        const c = this.correo;
        return c.puede ? `Se la manda a ${c.destino}, con su PDF.` : c.motivo || "No se puede enviar por correo.";
    },

    async enviarPorCorreo() {
        const c = this.cotizacion;
        if (!c || this.local.ocupado || this.local.enviandoCorreo || !this.correo.puede) {
            return;
        }
        this.local.enviandoCorreo = true;
        try {
            const r = await this.almacen.orm.call("dcasa.conversacion", "enviar_cotizacion_correo", [
                this.almacen.seleccionadaId,
                c.id,
            ]);
            const destino = (r && r.correo && r.correo.destino) || this.correo.destino;
            this.almacen.notification.add(`Cotización ${c.nombre} enviada por correo a ${destino}.`, { type: "success" });
            this.cerrar();
        } catch (error) {
            this.almacen.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.local.enviandoCorreo = false;
        }
    },
});
