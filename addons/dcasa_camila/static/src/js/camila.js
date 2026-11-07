/**
 * Camila, la asistente del mail marketing (Marketing › Camila).
 *
 * Todo se decide en el servidor (dcasa.camila): qué productos, qué precios (los de la tienda en línea), qué texto pasa la
 * revisión de marca, a quién le llega (el permiso, la baja y el tope de 15 días por cliente) y si la campaña puede
 * salir. Aquí se arma el correo a todo el ancho (decisión de la dueña, etapa 2: la vista previa no roba espacio; se abre
 * con «Previsualizar»), se cambian productos en un diálogo con buscador y filtros, se escribe con la IA y se elige el
 * público con chips que dicen el número en vivo.
 */
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dialog } from "@web/core/dialog/dialog";
import { mensajeDeError } from "@dcasa_conversaciones/js/utilidades";

const MODELO = "dcasa.camila";
const PAUSA_BUSQUEDA = 250;

/** La copia editable de la campaña (lo que la persona cambia antes de guardar). */
export function borradorEditable(campana) {
    if (!campana) {
        return null;
    }
    return {
        asunto: campana.asunto,
        entrada: campana.entrada,
        idea: campana.idea || "",
        lineas: campana.lineas.map((l) => ({ ...l })),
    };
}

/** Lo que se manda al servidor al guardar: el texto, la idea y los productos en orden (el precio lo pone Odoo). */
export function cambiosParaGuardar(borrador) {
    return {
        asunto: borrador.asunto,
        entrada: borrador.entrada,
        idea: borrador.idea || "",
        lineas: borrador.lineas.map((l) => ({ producto_id: l.producto_id, texto: l.texto || "" })),
    };
}

/** Los chips elegidos después de tocar uno: «Todos» va solo; los demás se suman; si no queda ninguno, «Todos». */
export function chipsTrasTocar(elegidos, clave) {
    if (clave === "todos") {
        return ["todos"];
    }
    const sinTodos = elegidos.filter((c) => c !== "todos");
    const nuevos = sinTodos.includes(clave) ? sinTodos.filter((c) => c !== clave) : [...sinTodos, clave];
    return nuevos.length ? nuevos : ["todos"];
}

/** «Previsualizar»: el correo grande, como en el celular o en la computadora, con su asunto. */
export class CamilaPrevia extends Component {
    static template = "dcasa_camila.Previa";
    static components = { Dialog };
    static props = ["campana", "close"];

    setup() {
        this.state = useState({ vista: "celular", alto: 900 });
    }

    verComo(vista) {
        this.state.vista = vista;
        this.state.alto = 900;
    }

    /** El marco crece hasta el alto del correo: así se ve entero y el diálogo baja con su propio scroll. */
    ajustar(ev) {
        try {
            const documento = ev.target.contentDocument;
            const alto = documento && documento.documentElement.scrollHeight;
            if (alto) {
                this.state.alto = alto + 8;
            }
        } catch {
            // otro origen: se queda con el alto de siempre
        }
    }
}

/** «Cambiar» y «Agregar producto»: buscador, filtros y tarjetas con foto, precio y existencias. */
export class CamilaProductos extends Component {
    static template = "dcasa_camila.Productos";
    static components = { Dialog };
    static props = ["titulo", "enCampana", "sugeridos?", "onElegir", "close"];

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            texto: "",
            filtros: { en_tienda: true, con_foto: true, publicado: true, categoria_id: false },
            productos: this.props.sugeridos || [],
            categorias: [],
            sugeridos: Boolean(this.props.sugeridos && this.props.sugeridos.length),
            buscando: false,
            error: "",
        });
        this.temporizador = null;
        onMounted(() => this.buscar({ conservarSugeridos: this.state.sugeridos }));
        onWillUnmount(() => clearTimeout(this.temporizador));
    }

    get soloOfrecibles() {
        const f = this.state.filtros;
        return f.en_tienda && f.con_foto && f.publicado;
    }

    alEscribir(ev) {
        this.state.texto = ev.target.value;
        this.state.sugeridos = false;
        clearTimeout(this.temporizador);
        this.temporizador = setTimeout(() => this.buscar(), PAUSA_BUSQUEDA);
    }

    cambiarFiltro(clave, valor) {
        this.state.filtros[clave] = valor;
        this.state.sugeridos = false;
        this.buscar();
    }

    alElegirCategoria(ev) {
        this.cambiarFiltro("categoria_id", parseInt(ev.target.value, 10) || false);
    }

    async buscar({ conservarSugeridos = false } = {}) {
        this.state.buscando = true;
        this.state.error = "";
        try {
            const r = await this.orm.call(MODELO, "buscar_productos", [this.state.texto, this.state.filtros]);
            this.state.categorias = r.categorias;
            if (!conservarSugeridos) {
                this.state.productos = r.productos;
            }
        } catch (error) {
            this.state.error = mensajeDeError(error);
        } finally {
            this.state.buscando = false;
        }
    }

    yaEsta(producto) {
        return this.props.enCampana.includes(producto.id);
    }

    elegir(producto) {
        if (!producto.elegible || this.yaEsta(producto)) {
            return;
        }
        this.props.onElegir(producto);
        this.props.close();
    }
}

/** «Nueva campaña»: desde una idea, lo nuevo, los más vendidos, los quietos, lo que más hay o en blanco. */
export class CamilaNueva extends Component {
    static template = "dcasa_camila.Nueva";
    static components = { Dialog };
    static props = ["temas", "onCrear", "close"];

    setup() {
        this.state = useState({ tema: "idea", idea: "", trabajando: false });
    }

    elegirTema(clave) {
        this.state.tema = clave;
    }

    async crear() {
        if (this.state.tema === "idea" && !this.state.idea.trim()) {
            return;
        }
        this.state.trabajando = true;
        const listo = await this.props.onCrear({ tema: this.state.tema, idea: this.state.idea });
        this.state.trabajando = false;
        if (listo) {
            this.props.close();
        }
    }
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
            // «producto»: de qué producto es el aviso (se muestra junto a él); sin producto, arriba, en la idea.
            ia: { escribiendo: "", error: "", reintentar: null, producto: false },
            // El campo «Remitente de las campañas» (Gerencia y administradores).
            remitente: "",
        });
        this.inicial = this.props.action?.params?.campana_id || false;
        onMounted(() => this.cargar(this.inicial));
    }

    // --- Datos ---------------------------------------------------------------------------------------------------
    ponerPanel(d) {
        this.state.d = d;
        this.state.borrador = borradorEditable(d.campana);
        this.state.sucio = false;
        this.state.error = "";
        this.state.remitente = (d.remitente && d.remitente.propio) || "";
    }

    async cargar(campanaId = false) {
        this.state.cargando = true;
        try {
            this.ponerPanel(await this.orm.call(MODELO, "panel", [campanaId || false]));
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

    get publico() {
        return (this.campana && this.campana.publico) || { chips: [], total: 0, fuera: [], elegidos: ["todos"] };
    }

    get puedeEnviar() {
        const d = this.state.d;
        return Boolean(d && this.campana && !d.bloqueos.length && this.campana.lineas.length && this.publico.total
            && !this.state.ocupado);
    }

    get textoEnviar() {
        const n = this.publico.total || 0;
        return n === 1 ? "Enviar a 1 cliente" : `Enviar a ${n} clientes`;
    }

    // --- Campañas ------------------------------------------------------------------------------------------------
    async elegirCampana(id) {
        if (this.campana && id === this.campana.id) {
            return;
        }
        if (this.state.sucio && !(await this.guardar({ aviso: false }))) {
            return;
        }
        await this.cargar(id);
    }

    nuevaCampana() {
        this.dialog.add(CamilaNueva, {
            temas: this.state.d.temas,
            onCrear: async (opciones) => {
                if (this.state.sucio && !(await this.guardar({ aviso: false }))) {
                    return false;
                }
                const d = await this.llamar("nueva", "nueva", [opciones]);
                if (!d) {
                    return false;
                }
                this.ponerPanel(d);
                this.notification.add("Camila armó la campaña nueva. Revísala antes de enviarla.", { type: "success" });
                return true;
            },
        });
    }

    async armar() {
        const d = await this.llamar("armar", "armar", [this.campana ? this.campana.id : false]);
        if (d) {
            this.ponerPanel(d);
            this.notification.add("Camila armó la campaña otra vez con lo que hay hoy en la tienda.", { type: "success" });
        }
    }

    confirmarArmar() {
        this.dialog.add(ConfirmationDialog, {
            title: "¿Volver a armar la campaña?",
            body: "Camila escoge otra vez los productos y escribe el texto de nuevo. Lo que cambiaste a mano se pierde.",
            confirmLabel: "Volver a armar",
            cancelLabel: "Cancelar",
            confirm: () => this.armar(),
            cancel: () => {},
        });
    }

    // --- Editar --------------------------------------------------------------------------------------------------
    marcarSucio() {
        this.state.sucio = true;
    }

    async guardar({ aviso = true, extra = {} } = {}) {
        if (!this.campana || !this.state.borrador) {
            return false;
        }
        // Tocar un chip o un botón sin haber cambiado el texto manda solo eso (el texto sigue siendo de quien lo escribió).
        const soloExtra = !this.state.sucio && Object.keys(extra).length;
        const cambios = soloExtra ? extra : { ...cambiosParaGuardar(this.state.borrador), ...extra };
        const d = await this.llamar("guardar", "guardar", [this.campana.id, cambios]);
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

    abrirProductos(reemplazar = null, sugeridos = null) {
        const lineas = this.state.borrador.lineas;
        this.dialog.add(CamilaProductos, {
            titulo: reemplazar !== null ? `Cambiar «${lineas[reemplazar].nombre}» por…`
                : sugeridos ? "Productos que encajan con tu idea" : "Agregar un producto",
            enCampana: lineas.map((l) => l.producto_id),
            sugeridos,
            onElegir: (producto) => this.elegir(producto, reemplazar),
        });
    }

    async elegir(producto, reemplazar) {
        const lineas = this.state.borrador.lineas;
        const nueva = { producto_id: producto.id, nombre: producto.nombre, texto: "", precio: producto.precio };
        if (reemplazar !== null) {
            lineas.splice(reemplazar, 1, nueva);
        } else {
            lineas.push(nueva);
        }
        await this.guardar({ aviso: false });
    }

    // --- Público -------------------------------------------------------------------------------------------------
    async tocarChip(clave) {
        if (!this.editable || this.state.ocupado) {
            return;
        }
        await this.guardar({ aviso: false, extra: { publico: chipsTrasTocar(this.publico.elegidos, clave) } });
    }

    /** Prende o apaga un botón o enlace del correo (el servidor no deja apagar los dos botones). */
    async cambiarBoton(clave, ev = null) {
        const casilla = ev && ev.target;
        const antes = Boolean(this.campana && this.campana.botones[clave]);
        if (!this.editable || this.state.ocupado) {
            if (casilla) {
                casilla.checked = antes;
            }
            return;
        }
        const botones = { [clave]: !antes };
        if (!(await this.guardar({ aviso: false, extra: { botones } })) && casilla) {
            // Lo rechazó el servidor (p. ej. quedarse sin botones): la casilla vuelve a como estaba, el motivo
            // queda a la vista y lo que la persona escribió sin guardar no se pierde (no se vuelve a cargar).
            casilla.checked = antes;
        }
    }

    // --- La IA ---------------------------------------------------------------------------------------------------
    async escribir(que, productoId = false) {
        if (this.state.sucio && !(await this.guardar({ aviso: false }))) {
            return;
        }
        const etiquetas = { linea: "la línea del producto", asunto: "el asunto", entrada: "la entrada", todo: "todo el texto" };
        Object.assign(this.state.ia, {
            escribiendo: etiquetas[que], error: "", reintentar: null, producto: (que === "linea" && productoId) || false,
        });
        const r = await this.llamar(`ia-${que}-${productoId || ""}`, "escribir", [this.campana.id, que, productoId]);
        this.state.ia.escribiendo = "";
        if (!r) {
            return;
        }
        if (!r.ok) {
            Object.assign(this.state.ia, { error: r.mensaje, reintentar: () => this.escribir(que, productoId) });
            return;
        }
        this.ponerPanel(r.panel);
        this.notification.add("Camila escribió el texto: revísalo y cámbialo si quieres.", { type: "success" });
    }

    async sugerir() {
        if (this.state.sucio && !(await this.guardar({ aviso: false }))) {
            return;
        }
        Object.assign(this.state.ia, { escribiendo: "productos para tu idea", error: "", reintentar: null, producto: false });
        const r = await this.llamar("ia-sugerir", "sugerir_productos", [this.campana.id, this.state.borrador.idea]);
        this.state.ia.escribiendo = "";
        if (!r) {
            return;
        }
        if (!r.ok) {
            Object.assign(this.state.ia, { error: r.mensaje, reintentar: () => this.sugerir() });
            return;
        }
        this.abrirProductos(null, r.productos);
    }

    reintentarIA() {
        const reintentar = this.state.ia.reintentar;
        if (reintentar) {
            reintentar();
        }
    }

    // --- Ver, probar, enviar y descartar ------------------------------------------------------------------------
    async previsualizar() {
        if (this.state.sucio && !(await this.guardar({ aviso: false }))) {
            return;
        }
        this.dialog.add(CamilaPrevia, { campana: this.campana });
    }

    async prueba() {
        if (this.state.sucio && !(await this.guardar({ aviso: false }))) {
            return;
        }
        const r = await this.llamar("prueba", "enviar_prueba", [this.campana.id]);
        if (r) {
            this.notification.add(r.mensaje, { type: "success" });
            await this.cargar(this.campana.id);
        }
    }

    confirmarEnviar() {
        this.dialog.add(ConfirmationDialog, {
            title: "¿Enviar la campaña?",
            body: `Le llega a ${this.publico.total} clientes que dijeron que sí (a ninguno le llegó otra en los últimos ${this.state.d.dias} días), con los precios de hoy. No se puede deshacer.`,
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
            title: this.editable ? "¿Descartar este borrador?" : "¿Descartar esta campaña?",
            body: this.editable
                ? "Queda en el historial como descartado. Puedes armar otro cuando quieras."
                : "Se revisa en Resend que no haya salido ni vaya a salir. Queda en el historial como descartada.",
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

    async cambiarEnlacePie(encendido) {
        const d = await this.llamar("enlace-pie", "ajustar_enlace_pie", [encendido]);
        if (d) {
            this.ponerPanel(d);
            this.notification.add(encendido ? "La línea «Sí, quiero» quedó encendida." : "La línea «Sí, quiero» quedó apagada.",
                { type: "success" });
        }
    }

    // --- El remitente de las campañas ---------------------------------------------------------------------------
    /** Lo que la persona escribió en la campaña se guarda antes (al volver, la pantalla se arma de nuevo). */
    async guardarPendiente() {
        return !(this.state.sucio && this.campana && !(await this.guardar({ aviso: false })));
    }

    async guardarRemitente() {
        if (!(await this.guardarPendiente())) {
            return;
        }
        const correo = (this.state.remitente || "").trim();
        const d = await this.llamar("remitente", "ajustar_remitente", [correo, this.campana ? this.campana.id : false]);
        if (d) {
            this.ponerPanel(d);
            this.notification.add(`Listo: las campañas saldrán de ${d.remitente.correo}.`, { type: "success" });
        }
    }

    /** «Revisar ahora»: pregunta otra vez a Resend por el dominio del remitente (el servidor no martilla a Resend). */
    async revisarRemitente() {
        if (!(await this.guardarPendiente())) {
            return;
        }
        const d = await this.llamar("revisar-remitente", "revisar_remitente", [this.campana ? this.campana.id : false]);
        if (d) {
            this.ponerPanel(d);
        }
    }

    async actualizarResultados(id) {
        const d = await this.llamar(`resultados-${id}`, "actualizar_resultados", [id]);
        if (d) {
            this.ponerPanel(d);
        }
    }
}

registry.category("actions").add("dcasa_camila.panel", CamilaPanel);
