/**
 * Camila, la asistente del mail marketing (Marketing › Camila).
 *
 * Todo se decide en el servidor (dcasa.camila): qué productos, qué precios (los de la tienda en línea), qué texto pasa la
 * revisión de marca y si la campaña puede salir. Aquí solo se muestra el borrador tal como se ve en el celular, se edita
 * el texto y los productos, y se llama a lo que la persona elige («Volver a armar», «Enviarme una prueba», «Enviar»).
 */
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { mensajeDeError } from "@dcasa_conversaciones/js/utilidades";

const MODELO = "dcasa.camila";
const PAUSA_BUSQUEDA = 250;

/** La copia editable del borrador (lo que la persona cambia antes de guardar). */
export function borradorEditable(campana) {
    if (!campana) {
        return null;
    }
    return {
        asunto: campana.asunto,
        entrada: campana.entrada,
        lineas: campana.lineas.map((l) => ({ ...l })),
    };
}

/** Lo que se manda al servidor al guardar: el texto y los productos en orden (el precio lo pone Odoo). */
export function cambiosParaGuardar(borrador) {
    return {
        asunto: borrador.asunto,
        entrada: borrador.entrada,
        lineas: borrador.lineas.map((l) => ({ producto_id: l.producto_id, texto: l.texto || "" })),
    };
}

export class CamilaPanel extends Component {
    static template = "dcasa_camila.Panel";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            cargando: true,
            ocupado: "",
            error: "",
            d: null,
            borrador: null,
            sucio: false,
            vista: "celular",
            altoPrevia: 900,
            busqueda: { abierta: false, texto: "", resultados: [], reemplazar: null, buscando: false },
        });
        this.temporizador = null;
        onMounted(() => this.cargar());
        onWillUnmount(() => clearTimeout(this.temporizador));
    }

    // --- Datos ---------------------------------------------------------------------------------------------------
    ponerPanel(d) {
        this.state.d = d;
        this.state.borrador = borradorEditable(d.campana);
        this.state.sucio = false;
        this.state.error = "";
    }

    async cargar() {
        this.state.cargando = true;
        try {
            this.ponerPanel(await this.orm.call(MODELO, "panel", []));
        } catch (error) {
            this.state.error = mensajeDeError(error);
        } finally {
            this.state.cargando = false;
        }
    }

    async llamar(clave, metodo, args = []) {
        this.state.ocupado = clave;
        this.state.error = "";
        try {
            return await this.orm.call(MODELO, metodo, args);
        } catch (error) {
            this.state.error = mensajeDeError(error);
            return null;
        } finally {
            this.state.ocupado = "";
        }
    }

    get campana() {
        return this.state.d && this.state.d.campana;
    }

    get editable() {
        return Boolean(this.campana && this.campana.editable);
    }

    get puedeEnviar() {
        const d = this.state.d;
        return Boolean(d && this.campana && !d.bloqueos.length && this.campana.lineas.length && !this.state.ocupado);
    }

    get textoEnviar() {
        const n = (this.state.d && this.state.d.con_permiso) || 0;
        return n === 1 ? "Enviar a 1 cliente" : `Enviar a ${n} clientes`;
    }

    // --- Armar y editar ------------------------------------------------------------------------------------------
    async armar() {
        const d = await this.llamar("armar", "armar");
        if (d) {
            this.ponerPanel(d);
            this.notification.add("Camila armó el borrador con lo que hay hoy en la tienda.", { type: "success" });
        }
    }

    confirmarArmar() {
        if (!this.campana) {
            return this.armar();
        }
        this.dialog.add(ConfirmationDialog, {
            title: "¿Volver a armar la campaña?",
            body: "Camila escoge otra vez los productos y escribe el texto de nuevo. Lo que cambiaste a mano se pierde.",
            confirmLabel: "Volver a armar",
            cancelLabel: "Cancelar",
            confirm: () => this.armar(),
            cancel: () => {},
        });
    }

    marcarSucio() {
        this.state.sucio = true;
    }

    async guardar({ aviso = true } = {}) {
        if (!this.campana || !this.state.borrador) {
            return false;
        }
        const d = await this.llamar("guardar", "guardar", [this.campana.id, cambiosParaGuardar(this.state.borrador)]);
        if (!d) {
            return false;
        }
        this.ponerPanel(d);
        if (aviso) {
            this.notification.add("Guardado. La vista previa ya tiene los cambios.", { type: "success" });
        }
        return true;
    }

    async quitar(indice) {
        this.state.borrador.lineas.splice(indice, 1);
        await this.guardar({ aviso: false });
    }

    async mover(indice, paso) {
        const lineas = this.state.borrador.lineas;
        const otro = indice + paso;
        if (otro < 0 || otro >= lineas.length) {
            return;
        }
        [lineas[indice], lineas[otro]] = [lineas[otro], lineas[indice]];
        await this.guardar({ aviso: false });
    }

    abrirBusqueda(reemplazar = null) {
        Object.assign(this.state.busqueda, { abierta: true, reemplazar, texto: "", resultados: [] });
        this.buscar();
    }

    cerrarBusqueda() {
        Object.assign(this.state.busqueda, { abierta: false, reemplazar: null, texto: "", resultados: [] });
    }

    alEscribirBusqueda(ev) {
        this.state.busqueda.texto = ev.target.value;
        clearTimeout(this.temporizador);
        this.temporizador = setTimeout(() => this.buscar(), PAUSA_BUSQUEDA);
    }

    async buscar() {
        const busqueda = this.state.busqueda;
        busqueda.buscando = true;
        try {
            const enCampana = new Set(this.state.borrador.lineas.map((l) => l.producto_id));
            const resultados = await this.orm.call(MODELO, "buscar_productos", [busqueda.texto]);
            busqueda.resultados = resultados.filter((p) => !enCampana.has(p.id));
        } catch (error) {
            this.state.error = mensajeDeError(error);
        } finally {
            busqueda.buscando = false;
        }
    }

    async elegir(producto) {
        const lineas = this.state.borrador.lineas;
        const nueva = { producto_id: producto.id, nombre: producto.nombre, texto: "", precio: producto.precio };
        if (this.state.busqueda.reemplazar !== null) {
            lineas.splice(this.state.busqueda.reemplazar, 1, nueva);
        } else {
            lineas.push(nueva);
        }
        this.cerrarBusqueda();
        await this.guardar({ aviso: false });
    }

    // --- Prueba, envío y descarte --------------------------------------------------------------------------------
    async prueba() {
        if (this.state.sucio && !(await this.guardar({ aviso: false }))) {
            return;
        }
        const r = await this.llamar("prueba", "enviar_prueba", [this.campana.id]);
        if (r) {
            this.notification.add(r.mensaje, { type: "success" });
            await this.cargar();
        }
    }

    confirmarEnviar() {
        this.dialog.add(ConfirmationDialog, {
            title: "¿Enviar la campaña?",
            body: `Le llega a ${this.state.d.con_permiso} clientes que dijeron que sí, con los precios de hoy. No se puede deshacer.`,
            confirmLabel: this.textoEnviar,
            cancelLabel: "Todavía no",
            confirm: () => this.enviar(),
            cancel: () => {},
        });
    }

    async enviar() {
        if (this.state.sucio && !(await this.guardar({ aviso: false }))) {
            return;
        }
        const r = await this.llamar("enviar", "enviar", [this.campana.id, this.campana.huella]);
        if (!r) {
            return;
        }
        if (r.panel) {
            this.ponerPanel(r.panel);
        }
        if (r.ok) {
            this.notification.add(r.mensaje, { type: "success" });
        } else if (r.cambio) {
            this.notification.add(r.mensaje, { type: "warning", sticky: true });
        } else {
            this.state.error = r.mensaje;
        }
    }

    confirmarDescartar() {
        this.dialog.add(ConfirmationDialog, {
            title: "¿Descartar este borrador?",
            body: "Queda en el historial como descartado. Puedes armar otro cuando quieras.",
            confirmLabel: "Descartar",
            cancelLabel: "Cancelar",
            confirm: async () => {
                const d = await this.llamar("descartar", "descartar", [this.campana.id]);
                if (d) {
                    this.ponerPanel(d);
                }
            },
            cancel: () => {},
        });
    }

    async actualizarResultados(id) {
        const d = await this.llamar(`resultados-${id}`, "actualizar_resultados", [id]);
        if (d) {
            this.ponerPanel(d);
        }
    }

    // --- Vista previa --------------------------------------------------------------------------------------------
    verComo(vista) {
        this.state.vista = vista;
        this.state.altoPrevia = 900;
    }

    /** El marco crece hasta el alto del correo: así se ve entero y la pantalla baja con su propio scroll. */
    ajustarPrevia(ev) {
        try {
            const documento = ev.target.contentDocument;
            const alto = documento && documento.documentElement.scrollHeight;
            if (alto) {
                this.state.altoPrevia = alto + 8;
            }
        } catch {
            // otro origen: se queda con el alto de siempre
        }
    }
}

registry.category("actions").add("dcasa_camila.panel", CamilaPanel);
