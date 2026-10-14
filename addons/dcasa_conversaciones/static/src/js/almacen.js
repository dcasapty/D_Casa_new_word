/**
 * El estado y las acciones de la pantalla «Conversaciones». Un solo objeto reactivo que comparten la lista, el hilo,
 * la ficha y la caja de respuesta; toda la comunicación con Odoo pasa por aquí (API de `dcasa.conversacion`,
 * docs/JUAN_ODOO.md) y el tiempo real llega por el bus de Odoo (`dcasa_conversaciones/evento`, sin texto).
 */
import {
    esAnchoParaTodo,
    esCelular,
    esPantallaAmplia,
    esPantallaEstrecha,
    fichaVaAlLado,
    guardarPreferencia,
    leerPreferencia,
} from "./preferencias";
import { cuando, fusionarMensajes, hayHueco, mensajeDeError } from "./utilidades";

const MODELO = "dcasa.conversacion";
const POR_PAGINA = 30;
const MAX_LISTA = 100;
const TRAMO_DEL_HILO = 50;
const ESPERA_DE_EVENTOS = 350;
// La presencia («Ana está viendo») se renueva con cada pulso (cada 20 s); sin pulso en este tiempo, se borra sola.
const VIDA_DE_PRESENCIA_MS = 55_000;
const CADA_CUANTO_AVISA_QUE_ESCRIBE_MS = 4_000;
// Lo mismo que acepta el servidor (models/conversacion_panel_extra.py): fotos, PDF, Word, Excel y texto.
const TIPOS_QUE_SE_SUBEN = /\.(jpe?g|png|webp|gif|pdf|docx?|xlsx?|txt|csv)$/i;

export const FILTROS_VACIOS = () => ({
    canal: "",
    estado: "",
    etiqueta_id: 0,
    asignada_a_mi: false,
    sin_leer: false,
    con_oportunidad: false,
    busqueda: "",
});

export class Almacen {
    constructor({ orm, bus, notification }) {
        this.orm = orm;
        this.bus = bus;
        this.notification = notification;
        this.iniciado = false;
        this.cargandoInicio = true;
        this.errorInicio = null;
        // Datos de arranque
        this.usuario = { id: 0, nombre: "", es_gerencia: false };
        this.bot = { conectado: true, encendido: true };
        this.limites = { adjuntos: 5, bytes: 10 * 1024 * 1024, respuesta: 4000, nota: 1000, nota_para_el_bot: 500, pausa_minutos: 120 };
        this.canales = [];
        this.etiquetas = [];
        this.rapidas = [];
        this.equipo = [];
        // Lista
        this.filtros = FILTROS_VACIOS();
        this.lista = [];
        this.total = 0;
        this.hayMas = false;
        this.sinLeerTotal = 0;
        this.cargandoLista = true;
        this.cargandoMas = false;
        this.errorLista = null;
        // Conversación abierta
        this.seleccionadaId = null;
        this.conversacion = null;
        this.mensajes = [];
        this.programados = []; // lo que está escrito para más tarde (aparte del hilo)
        this.resumen = null; // el resumen con IA de la conversación abierta: { texto, generado_en, vigente } o null
        this.resumiendo = false;
        this.resumenActivo = false; // Ajustes de Juan: ¿se ofrece el botón «Resumir»?
        this.presencia = {}; // conversación → quiénes más la tienen abierta [{usuario_id, escribiendo, hasta}]
        this.disponible = true; // con el reparto por turnos: ¿me tocan conversaciones nuevas?
        this.reparto = "manual";
        this._ultimoAvisoEscribe = 0;
        this.escribiendoBot = {}; // conversación → cuándo (ms) avisó el Worker que el asistente prepara la respuesta; 0 = ya terminó
        this.hayMasAntes = false;
        this.cargandoHilo = false;
        this.cargandoAntes = false;
        this.errorHilo = null;
        this.ficha = null;
        this.cargandoFicha = false;
        this.nuevosSinVer = 0;
        // Pantalla (en celular se ve una columna a la vez). La ficha del cliente nace abierta solo en pantallas amplias
        // (al lado del hilo); en las demás nace cerrada y un botón «Cliente» la abre. La lista nace reducida a las fotos
        // en pantallas estrechas. Cada persona puede cambiarlo y se le recuerda (ver cargarPreferencias).
        this.columna = "lista";
        this.fichaAbierta = esPantallaAmplia();
        this.listaCompacta = esPantallaEstrecha() && !esCelular();
        this.tamanoVersion = 0; // sube cuando la ventana cruza un límite de tamaño: así la pantalla se vuelve a acomodar
        this.enVivo = false;
        this.ahora = Date.now();
        // Ventanas encima de la pantalla: el buscador de fotos, la cotización y el visor de imágenes
        this.panel = null; // "catalogo" | "cotizacion" | "adjuntar" | null
        this.adjuntoAAsociar = null; // el archivo del cliente que se va a adjuntar a una factura o pedido
        this.visor = null; // { imagenes: [{url, nombre}], indice }
        // Lo que se está escribiendo en cada conversación (se conserva al cambiar de una a otra)
        this.borradores = {};
        // Contadores internos
        this._contadorDeArchivos = 0;
        this._numeroDeListado = 0;
        this._numeroDeHilo = 0;
        this._temporizadorEventos = null;
        this._eventosPendientes = new Set();
        // «En vivo» solo lo dice la conexión de verdad (no un deseo): se enciende al conectar y se apaga al caerse.
        this._ultimaSincronizacion = Date.now();
        this._resincronizando = false;
        this._escuchas = [];
    }

    /** El borrador de la conversación abierta: texto, modo («respuesta» o «nota») y archivos por enviar. */
    get borrador() {
        const id = this.seleccionadaId;
        if (!id) {
            return { texto: "", modo: "respuesta", adjuntos: [], menciones: [], tareaPara: "", programarPara: "" };
        }
        if (!this.borradores[id]) {
            this.borradores[id] = { texto: "", modo: "respuesta", adjuntos: [], menciones: [], tareaPara: "", programarPara: "" };
        }
        return this.borradores[id];
    }

    // ------------------------------------------------------------------
    // Arranque y tiempo real
    // ------------------------------------------------------------------

    async iniciar() {
        try {
            const datos = await this.orm.call(MODELO, "iniciar_panel", []);
            Object.assign(this, {
                usuario: datos.usuario,
                bot: datos.bot,
                limites: datos.limites,
                canales: datos.canales,
                etiquetas: datos.etiquetas,
                rapidas: datos.rapidas,
                equipo: datos.equipo,
                reparto: datos.reparto,
                resumenActivo: !!datos.resumen_ia,
            });
            this.disponible = datos.usuario.disponible !== false;
            this.cargarPreferencias();
            this.iniciado = true;
        } catch (error) {
            this.errorInicio = mensajeDeError(error);
        } finally {
            this.cargandoInicio = false;
        }
        await this.cargarLista();
        this.suscribir();
    }

    // ------------------------------------------------------------------
    // Cómo se acomoda la pantalla: ficha del cliente y lista (preferencias de cada persona)
    // ------------------------------------------------------------------

    /** Lo que cada persona dejó elegido en este navegador: la ficha (solo desde 1024 px) y la lista. */
    cargarPreferencias() {
        const id = this.usuario.id;
        const ficha = leerPreferencia("ficha", id);
        if (fichaVaAlLado() && ficha) {
            this.fichaAbierta = ficha === "abierta";
        }
        const lista = leerPreferencia("lista", id);
        if (lista && !esCelular()) {
            this.listaCompacta = lista === "compacta";
        }
    }

    /**
     * ¿La lista se ve reducida a las fotos? Cuando la persona lo eligió, o cuando hay poco ancho (menos de 1250 px) y la
     * ficha está abierta: así el hilo no se queda sin espacio. En ese segundo caso no hace falta el botón de la lista
     * (se amplía sola al cerrar la ficha).
     */
    get listaForzada() {
        void this.tamanoVersion;
        return !esCelular() && this.fichaAbierta && !esAnchoParaTodo();
    }

    get listaReducida() {
        void this.tamanoVersion;
        return !esCelular() && (this.listaCompacta || this.listaForzada);
    }

    /** «Cliente»: abre o cierra la ficha. En celular es otra pantalla; en escritorio, al lado; en tablet, encima. */
    alternarFicha() {
        if (esCelular()) {
            this.fichaAbierta = true;
            this.columna = "ficha";
            return;
        }
        this.fichaAbierta = !this.fichaAbierta;
        this.recordarFicha();
    }

    cerrarFicha() {
        this.fichaAbierta = false;
        if (esCelular()) {
            this.columna = this.seleccionadaId ? "hilo" : "lista";
            return;
        }
        this.recordarFicha();
    }

    /** Se recuerda abierta o cerrada desde 1024 px; en tablet (ficha encima del hilo) nace cerrada siempre. */
    recordarFicha() {
        if (fichaVaAlLado()) {
            guardarPreferencia("ficha", this.fichaAbierta ? "abierta" : "cerrada", this.usuario.id);
        }
    }

    alternarLista() {
        this.listaCompacta = !this.listaCompacta;
        guardarPreferencia("lista", this.listaCompacta ? "compacta" : "completa", this.usuario.id);
    }

    /** La ventana cruzó un límite de tamaño (zoom, otra pantalla): la ficha y la lista se acomodan solas. */
    alCambiarElTamano() {
        this.tamanoVersion++;
        if (esCelular()) {
            return;
        }
        if (fichaVaAlLado()) {
            const recordada = leerPreferencia("ficha", this.usuario.id);
            this.fichaAbierta = recordada ? recordada === "abierta" : esPantallaAmplia();
        } else {
            this.fichaAbierta = false;
        }
    }

    suscribir() {
        // Ojo: las funciones que se le dejan al bus y al navegador usan `almacen`, el objeto REACTIVO (el que llegó aquí
        // como `this` porque la pantalla llamó a este método). Si usaran el objeto «crudo» (p. ej. un `bind` en el
        // constructor), lo que cambian no volvería a pintar la pantalla hasta que otra cosa la moviera.
        const almacen = this;
        this._escuchas = [
            ["dcasa_conversaciones/evento", (carga) => almacen._alEvento(carga)],
            ["BUS:CONNECT", () => (almacen.enVivo = true)],
            ["BUS:RECONNECT", () => almacen._alReconectar()],
            ["BUS:DISCONNECT", () => (almacen.enVivo = false)],
            ["BUS:RECONNECTING", () => (almacen.enVivo = false)],
        ];
        this.bus.subscribe(...this._escuchas[0]);
        for (const [tipo, funcion] of this._escuchas.slice(1)) {
            this.bus.addEventListener?.(tipo, funcion);
        }
        this._alVolverLaRed = () => almacen.resincronizar();
        window.addEventListener("online", this._alVolverLaRed);
        this.bus
            .start?.()
            .then(() => {
                // Si la conexión ya estaba abierta (otra pestaña la comparte) no habrá un aviso de «conectó»: se mira cómo está.
                this.enVivo = this.enVivo || this.bus.workerState === "CONNECTED";
            })
            .catch(() => (this.enVivo = false));
    }

    desuscribir() {
        const [aviso, ...conexion] = this._escuchas;
        if (aviso) {
            this.bus.unsubscribe(...aviso);
        }
        for (const [tipo, funcion] of conexion) {
            this.bus.removeEventListener?.(tipo, funcion);
        }
        this._escuchas = [];
        window.removeEventListener("online", this._alVolverLaRed);
        clearTimeout(this._temporizadorEventos);
    }

    /** Volvió la conexión en vivo: lo que pasó mientras estuvo caída no llegó por avisos, así que se trae de nuevo. */
    _alReconectar() {
        this.enVivo = true;
        return this.resincronizar();
    }

    /**
     * Pone al día la lista y la conversación abierta con lo que tiene el servidor. Se usa al reconectar, al volver a ver la
     * pestaña y, si no hay conexión en vivo, cada tanto. `sinPasarDe`: si se sincronizó hace menos de esos ms, no hace nada.
     */
    async resincronizar(sinPasarDe = 0) {
        if (this._resincronizando || !this.iniciado || Date.now() - this._ultimaSincronizacion < sinPasarDe) {
            return;
        }
        this._resincronizando = true;
        try {
            await this.refrescarTodo();
        } finally {
            this._resincronizando = false;
        }
    }

    /** Un aviso del servidor (solo ids y estado, jamás texto): se juntan los de un instante y se refresca una vez. */
    _alEvento(carga) {
        if (!carga || typeof carga !== "object") {
            return;
        }
        if (carga.evento === "presencia") {
            // Otra persona abrió, cambió o dejó una conversación: solo se mueve su nombre, sin pedir nada al servidor.
            this._aplicarPresencia(carga);
            return;
        }
        if (carga.evento === "escribiendo") {
            // No hay nada que traer del servidor: solo se enciende o se apaga el «escribiendo…» de esa conversación.
            this.escribiendoBot[carga.conversacion_id] = carga.activo ? Date.now() : 0;
            return;
        }
        if (carga.evento === "mensaje" && carga.autor && carga.autor !== "cliente") {
            this.escribiendoBot[carga.conversacion_id] = 0; // ya contestó (el asistente o una persona)
        }
        this._eventosPendientes.add(JSON.stringify(carga));
        clearTimeout(this._temporizadorEventos);
        this._temporizadorEventos = setTimeout(() => this._atenderEventos(), ESPERA_DE_EVENTOS);
    }

    // ------------------------------------------------------------------
    // Quién más está viendo cada conversación, y mi disponibilidad
    // ------------------------------------------------------------------

    /** El pulso de esta pantalla: «tengo abierta esta conversación» (y si estoy escribiéndole al cliente). */
    async latido(escribiendo = false) {
        if (!this.iniciado) {
            return;
        }
        try {
            const r = await this.orm.silent.call(MODELO, "presencia", [this.seleccionadaId || null, escribiendo]);
            const hasta = Date.now() + VIDA_DE_PRESENCIA_MS;
            const mapa = {};
            for (const [conversacion, personas] of Object.entries(r.presencia || {})) {
                mapa[conversacion] = personas.map((p) => ({ ...p, hasta }));
            }
            this.presencia = mapa;
        } catch {
            /* es un extra de la pantalla: si no llega, todo lo demás sigue igual */
        }
    }

    /** Al teclear una respuesta: avisa («escribiendo») a lo más una vez cada 4 s. */
    avisarQueEscribo() {
        const ahora = Date.now();
        if (ahora - this._ultimoAvisoEscribe < CADA_CUANTO_AVISA_QUE_ESCRIBE_MS) {
            return;
        }
        this._ultimoAvisoEscribe = ahora;
        this.latido(true);
    }

    /** Al salir de la pantalla: ya no tengo ninguna conversación abierta. */
    salir() {
        this.orm.silent.call(MODELO, "presencia", [null, false]).catch(() => {});
    }

    _aplicarPresencia(c) {
        const quitar = (conversacion) => {
            if (conversacion && this.presencia[conversacion]) {
                this.presencia[conversacion] = this.presencia[conversacion].filter((p) => p.usuario_id !== c.usuario_id);
            }
        };
        quitar(c.anterior);
        quitar(c.conversacion_id);
        if (c.conversacion_id) {
            const ya = this.presencia[c.conversacion_id] || [];
            this.presencia[c.conversacion_id] = [...ya, { usuario_id: c.usuario_id, escribiendo: !!c.escribiendo, hasta: Date.now() + VIDA_DE_PRESENCIA_MS }];
        }
    }

    /** Las otras personas que tienen abierta esa conversación ahora: [{ nombre, escribiendo }]. */
    quienVe(conversacionId) {
        const ahora = Date.now();
        return (this.presencia[conversacionId] || [])
            .filter((p) => p.hasta > ahora)
            .map((p) => ({
                nombre: (this.equipo.find((u) => u.id === p.usuario_id)?.nombre || "Alguien").split(" ")[0],
                escribiendo: p.escribiendo,
            }));
    }

    /**
     * «Resumir»: pide al servidor un resumen de la conversación abierta (si ya hay uno al día, lo devuelve sin gastar IA).
     * `regenerar`: uno nuevo aunque el guardado cubra todo.
     */
    async resumirLaAbierta(regenerar = false) {
        const id = this.seleccionadaId;
        if (!id || this.resumiendo) {
            return;
        }
        this.resumiendo = true;
        try {
            const r = await this.orm.call(MODELO, "resumir_conversacion", [id, regenerar]);
            if (id === this.seleccionadaId) {
                this.resumen = { texto: r.texto, generado_en: r.generado_en, vigente: r.vigente };
                if (r.avisos?.length) {
                    this.notification.add(r.avisos.join(" "), { type: "warning" });
                }
            }
        } catch (error) {
            this.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.resumiendo = false;
        }
    }

    async fijarDisponible(valor) {
        const antes = this.disponible;
        this.disponible = valor;
        try {
            await this.orm.call(MODELO, "fijar_disponible", [valor]);
        } catch (error) {
            this.disponible = antes;
            this.notification.add(mensajeDeError(error), { type: "danger" });
        }
    }

    async _atenderEventos() {
        const eventos = [...this._eventosPendientes].map((e) => JSON.parse(e));
        this._eventosPendientes.clear();
        const abierta = this.seleccionadaId;
        const tocaLaAbierta = eventos.some((e) => e.conversacion_id === abierta);
        const llegoDeCliente = eventos.filter((e) => e.evento === "mensaje" && e.autor === "cliente" && e.conversacion_id !== abierta);
        if (tocaLaAbierta) {
            await this.refrescarTodo();
        } else {
            await this.cargarLista({ silencioso: true });
        }
        for (const evento of llegoDeCliente.slice(0, 2)) {
            const fila = this.lista.find((c) => c.id === evento.conversacion_id);
            if (fila) {
                this.notification.add(`${fila.nombre} escribió.`, { type: "info" });
            }
        }
    }

    // ------------------------------------------------------------------
    // La lista
    // ------------------------------------------------------------------

    get filtrosActivos() {
        const f = this.filtros;
        return [f.canal, f.estado, f.etiqueta_id, f.asignada_a_mi, f.sin_leer, f.con_oportunidad].filter(Boolean).length;
    }

    _filtrosParaElServidor() {
        const f = this.filtros;
        const limpio = {};
        if (f.canal) {
            limpio.canal = f.canal;
        }
        if (f.estado) {
            limpio.estado = f.estado;
        }
        if (f.etiqueta_id) {
            limpio.etiqueta_id = f.etiqueta_id;
        }
        for (const clave of ["asignada_a_mi", "sin_leer", "con_oportunidad"]) {
            if (f[clave]) {
                limpio[clave] = true;
            }
        }
        if (f.busqueda.trim()) {
            limpio.busqueda = f.busqueda.trim();
        }
        return limpio;
    }

    /** Carga la primera página. En modo silencioso (tiempo real) conserva lo ya cargado: pide tantas como hay. */
    async cargarLista({ silencioso = false } = {}) {
        const numero = ++this._numeroDeListado;
        if (!silencioso) {
            this.cargandoLista = true;
            this.errorLista = null;
        }
        const limite = silencioso ? Math.min(MAX_LISTA, Math.max(POR_PAGINA, this.lista.length)) : POR_PAGINA;
        try {
            const orm = silencioso ? this.orm.silent : this.orm;
            const r = await orm.call(MODELO, "lista", [this._filtrosParaElServidor(), 0, limite]);
            if (numero !== this._numeroDeListado) {
                return;
            }
            this._aplicarLista(r);
        } catch (error) {
            if (numero === this._numeroDeListado && !silencioso) {
                this.errorLista = mensajeDeError(error);
            }
        } finally {
            if (numero === this._numeroDeListado) {
                this.cargandoLista = false;
            }
        }
    }

    _aplicarLista(r) {
        this.lista = r.conversaciones;
        this.total = r.total;
        this.hayMas = r.hay_mas;
        this.sinLeerTotal = r.sin_leer_total;
        this._ultimaSincronizacion = Date.now();
        const abierta = this.lista.find((c) => c.id === this.seleccionadaId);
        if (abierta) {
            this.conversacion = abierta;
        }
    }

    async cargarMas() {
        if (this.cargandoMas || !this.hayMas || this.cargandoLista) {
            return;
        }
        const numero = this._numeroDeListado;
        this.cargandoMas = true;
        try {
            const r = await this.orm.call(MODELO, "lista", [this._filtrosParaElServidor(), this.lista.length, POR_PAGINA]);
            if (numero !== this._numeroDeListado) {
                return;
            }
            const vistas = new Set(this.lista.map((c) => c.id));
            this.lista = [...this.lista, ...r.conversaciones.filter((c) => !vistas.has(c.id))];
            this.total = r.total;
            this.hayMas = r.hay_mas;
            this.sinLeerTotal = r.sin_leer_total;
        } catch (error) {
            this.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.cargandoMas = false;
        }
    }

    cambiarFiltro(clave, valor) {
        this.filtros[clave] = valor;
        return this.cargarLista();
    }

    limpiarFiltros() {
        this.filtros = FILTROS_VACIOS();
        return this.cargarLista();
    }

    /** Pone al día una fila de la lista con el resumen que devuelve el servidor (tomar, devolver, etiquetas…). */
    actualizarFila(resumen) {
        if (!resumen) {
            return;
        }
        const i = this.lista.findIndex((c) => c.id === resumen.id);
        if (i >= 0) {
            this.lista[i] = resumen;
        }
        if (resumen.id === this.seleccionadaId) {
            this.conversacion = resumen;
        }
    }

    // ------------------------------------------------------------------
    // El hilo
    // ------------------------------------------------------------------

    async abrir(id) {
        if (this.seleccionadaId === id && this.conversacion) {
            this.columna = "hilo";
            return;
        }
        const numero = ++this._numeroDeHilo;
        this.seleccionadaId = id;
        this.conversacion = this.lista.find((c) => c.id === id) || null;
        this.mensajes = [];
        this.programados = [];
        this.resumen = null;
        this.hayMasAntes = false;
        this.ficha = null;
        this.errorHilo = null;
        this.nuevosSinVer = 0;
        this.cargandoHilo = true;
        this.columna = "hilo";
        if (!fichaVaAlLado()) {
            this.fichaAbierta = false; // encima del hilo (tablet) o en celular, la ficha se cierra al cambiar de conversación
        }
        this.latido();
        try {
            const r = await this.orm.call(MODELO, "hilo", [id, null, TRAMO_DEL_HILO]);
            if (numero !== this._numeroDeHilo) {
                return;
            }
            this.mensajes = r.mensajes;
            this.programados = r.programados || [];
            if (r.resumen_ia !== undefined && r.resumen_ia !== null) {
                this.resumen = r.resumen_ia;
            }
            this.hayMasAntes = r.hay_mas;
            this.conversacion = r.conversacion;
            this.actualizarFila(r.conversacion);
        } catch (error) {
            if (numero === this._numeroDeHilo) {
                this.errorHilo = mensajeDeError(error);
            }
        } finally {
            if (numero === this._numeroDeHilo) {
                this.cargandoHilo = false;
            }
        }
        if (numero === this._numeroDeHilo) {
            this.cargarFicha();
            this.marcarLeida();
        }
    }

    volverALaLista() {
        this.columna = "lista";
        if (!fichaVaAlLado()) {
            this.fichaAbierta = false;
        }
    }

    async cargarAntes() {
        if (!this.hayMasAntes || this.cargandoAntes || !this.mensajes.length) {
            return;
        }
        const numero = this._numeroDeHilo;
        this.cargandoAntes = true;
        try {
            const r = await this.orm.call(MODELO, "hilo", [this.seleccionadaId, this.mensajes[0].id, TRAMO_DEL_HILO]);
            if (numero !== this._numeroDeHilo) {
                return;
            }
            this.mensajes = fusionarMensajes(this.mensajes, r.mensajes);
            this.hayMasAntes = r.hay_mas;
        } catch (error) {
            this.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.cargandoAntes = false;
        }
    }

    /** Trae lo último del hilo abierto (tiempo real). Si llegaron más de los que caben en un tramo, lo recarga entero. */
    async refrescarAbierta() {
        const id = this.seleccionadaId;
        if (!id) {
            return;
        }
        const numero = this._numeroDeHilo;
        const teniaAntes = this.mensajes.length;
        try {
            const r = await this.orm.silent.call(MODELO, "hilo", [id, null, TRAMO_DEL_HILO]);
            if (numero !== this._numeroDeHilo) {
                return;
            }
            this._aplicarHiloReciente(r, teniaAntes);
        } catch {
            /* el tiempo real es un extra: la próxima vez se pone al día */
        }
    }

    _aplicarHiloReciente(r, teniaAntes) {
        const hueco = hayHueco(this.mensajes, r.mensajes, true);
        const nuevos = r.mensajes.filter((m) => !this.mensajes.some((x) => x.id === m.id));
        this.mensajes = hueco ? r.mensajes : fusionarMensajes(this.mensajes, r.mensajes);
        this.programados = r.programados || [];
        if (r.resumen_ia !== undefined && r.resumen_ia !== null) {
            this.resumen = r.resumen_ia;
        }
        if (hueco) {
            this.hayMasAntes = r.hay_mas;
        }
        this.conversacion = r.conversacion;
        this.actualizarFila(r.conversacion);
        if (teniaAntes && nuevos.some((m) => m.autor === "cliente")) {
            this.nuevosSinVer += nuevos.filter((m) => m.autor === "cliente").length;
        }
        this.cargarFicha({ silencioso: true });
        if (document.visibilityState === "visible") {
            this.marcarLeida();
        }
    }

    /**
     * Pone al día la lista y la conversación abierta con UNA sola llamada (antes eran dos). Es lo que se hace cuando el
     * servidor avisa que algo cambió en la conversación que se está viendo, al reconectar y al volver a la pestaña.
     */
    async refrescarTodo() {
        const id = this.seleccionadaId;
        if (!id) {
            return this.cargarLista({ silencioso: true });
        }
        const numeroLista = ++this._numeroDeListado;
        const numeroHilo = this._numeroDeHilo;
        const teniaAntes = this.mensajes.length;
        const limite = Math.min(MAX_LISTA, Math.max(POR_PAGINA, this.lista.length));
        try {
            const r = await this.orm.silent.call(MODELO, "refrescar", [this._filtrosParaElServidor(), limite, id, TRAMO_DEL_HILO]);
            if (numeroLista === this._numeroDeListado) {
                this._aplicarLista(r.lista);
            }
            if (r.hilo && id === this.seleccionadaId && numeroHilo === this._numeroDeHilo) {
                this._aplicarHiloReciente(r.hilo, teniaAntes);
            }
        } catch {
            /* el tiempo real es un extra: la próxima vez se pone al día */
        }
    }

    async marcarLeida() {
        const id = this.seleccionadaId;
        const fila = this.lista.find((c) => c.id === id);
        const pendiente = (fila?.sin_leer || 0) > 0 || (this.conversacion?.sin_leer || 0) > 0;
        if (!id || !pendiente) {
            return;
        }
        try {
            await this.orm.silent.call(MODELO, "marcar_leida", [[id]]);
            if (fila?.sin_leer) {
                this.sinLeerTotal = Math.max(0, this.sinLeerTotal - 1);
            }
            for (const c of [fila, this.conversacion]) {
                if (c) {
                    c.sin_leer = 0;
                }
            }
        } catch {
            /* se marcará la próxima vez */
        }
    }

    // ------------------------------------------------------------------
    // La ficha
    // ------------------------------------------------------------------

    async cargarFicha({ silencioso = false } = {}) {
        const id = this.seleccionadaId;
        if (!id) {
            return;
        }
        if (!silencioso) {
            this.cargandoFicha = true;
        }
        try {
            const orm = silencioso ? this.orm.silent : this.orm;
            const ficha = await orm.call(MODELO, "ficha", [id]);
            if (id === this.seleccionadaId) {
                this.ficha = ficha;
            }
        } catch (error) {
            if (!silencioso) {
                this.notification.add(mensajeDeError(error), { type: "danger" });
            }
        } finally {
            this.cargandoFicha = false;
        }
    }

    // ------------------------------------------------------------------
    // Lo que hacen los botones
    // ------------------------------------------------------------------

    /** Llama a un método y, si trae el resumen de la conversación, pone al día la lista. Los errores salen en pantalla. */
    async _hacer(metodo, args, { exito = null, tipo = "success" } = {}) {
        try {
            const r = await this.orm.call(MODELO, metodo, args);
            this.actualizarFila(r?.conversacion || (r?.id ? r : null));
            if (exito) {
                this.notification.add(exito, { type: tipo });
            }
            return r;
        } catch (error) {
            this.notification.add(mensajeDeError(error), { type: "danger" });
            return null;
        }
    }

    async tomar(minutos = null) {
        const r = await this._hacer("tomar", [this.seleccionadaId, minutos]);
        if (r) {
            this.refrescarAbierta();
        }
        return r;
    }

    async devolver(nota = "") {
        const r = await this._hacer("devolver", [this.seleccionadaId, nota || null], { exito: "Se la devolviste al asistente." });
        if (r) {
            this.refrescarAbierta();
        }
        return r;
    }

    async cerrar() {
        const r = await this._hacer("cerrar", [this.seleccionadaId], { exito: "Conversación cerrada." });
        if (r) {
            this.refrescarAbierta();
        }
        return r;
    }

    /** Elimina la conversación abierta (Gerencia): la quita de la lista y vuelve a ella. */
    async eliminar() {
        const id = this.seleccionadaId;
        const r = await this._hacer("eliminar", [id], { exito: "Conversación eliminada." });
        if (r?.eliminada) {
            this.lista = this.lista.filter((c) => c.id !== id);
            this.total = Math.max(0, this.total - 1);
            this.seleccionadaId = null;
            this.conversacion = null;
            this.mensajes = [];
            this.programados = [];
            this.ficha = null;
            this.volverALaLista();
        }
        return r;
    }

    async asignar(usuarioId) {
        const r = await this._hacer("asignar", [this.seleccionadaId, usuarioId || null]);
        if (r) {
            this.refrescarAbierta();
        }
        return r;
    }

    async ponerEtiquetas(ids) {
        const r = await this._hacer("poner_etiquetas", [this.seleccionadaId, ids]);
        if (r) {
            this.cargarFicha({ silencioso: true });
        }
        return r;
    }

    async agregarNota(texto, menciones = [], tareaPara = "") {
        const r = await this._hacer("agregar_nota", [this.seleccionadaId, texto, menciones, tareaPara || null]);
        if (r) {
            if (r.mencionadas) {
                const tareas = r.tareas ? ` y les dejé ${r.tareas === 1 ? "una tarea" : "tareas"}` : "";
                this.notification.add(`Nota guardada. Les avisé a ${r.mencionadas === 1 ? "la mencionada" : `las ${r.mencionadas} mencionadas`}${tareas}.`, { type: "success" });
            }
            await this.refrescarAbierta();
        }
        return r;
    }

    /** Con `programarPara` (ISO en UTC) el mensaje no sale ahora: queda programado y sale solo a esa hora. */
    async enviar(texto, adjuntosIds, programarPara = null) {
        const r = await this._hacer("enviar_respuesta", [this.seleccionadaId, texto, adjuntosIds, programarPara]);
        if (r) {
            await this.refrescarAbierta();
            if (r.programado) {
                this.notification.add(`Programado: se envía ${cuando(r.mensaje.programado_para, this.ahora)}. El asistente sigue atendiendo hasta entonces.`, { type: "success" });
            } else if (!r.enviado) {
                this.notification.add("Quedó por enviar: el Worker no respondió y se reintenta solo.", { type: "warning" });
            }
        }
        return r;
    }

    async cancelarProgramado(mensajeId) {
        const r = await this._hacer("cancelar_programado", [mensajeId], { exito: "Cancelaste el mensaje programado." });
        if (r) {
            this.programados = this.programados.filter((m) => m.id !== mensajeId);
            await this.refrescarAbierta();
        }
        return r;
    }

    async reintentar() {
        const r = await this._hacer("reintentar_envios_panel", [this.seleccionadaId]);
        if (r) {
            await this.refrescarAbierta();
            this.notification.add(
                r.salieron === r.reintentados ? "Salió." : "Todavía no salió. Se reintenta solo cada 5 minutos.",
                { type: r.salieron === r.reintentados ? "success" : "warning" }
            );
        }
        return r;
    }

    async crearOportunidad() {
        const r = await this.orm
            .call(MODELO, "nueva_oportunidad", [this.seleccionadaId])
            .catch((e) => this.notification.add(mensajeDeError(e), { type: "danger" }));
        if (r?.oportunidad) {
            this.actualizarFila(r.conversacion);
            this.notification.add(r.nueva ? "Oportunidad creada." : "Ya había una oportunidad abierta de este cliente.", {
                type: r.nueva ? "success" : "info",
            });
            await Promise.all([this.cargarFicha({ silencioso: true }), this.refrescarAbierta()]);
        }
        return r;
    }

    async cancelarSeguimiento() {
        const r = await this._hacer("cancelar_seguimiento", [this.seleccionadaId], { exito: "Seguimiento cancelado." });
        if (r) {
            this.cargarFicha({ silencioso: true });
            this.refrescarAbierta();
        }
        return r;
    }

    async marcarSensible(adjuntoId, valor) {
        try {
            await this.orm.call("dcasa.mensaje", "marcar_sensible", [[adjuntoId], valor]);
            await this.refrescarAbierta();
            this.notification.add(valor ? "Marcado como comprobante o documento sensible." : "Ya no está marcado como sensible.", {
                type: "success",
            });
        } catch (error) {
            this.notification.add(mensajeDeError(error), { type: "danger" });
        }
    }

    // ------------------------------------------------------------------
    // Archivos de la caja (se suben al elegirlos, así «Enviar» es rápido)
    // ------------------------------------------------------------------

    /** Revisa un archivo antes de subirlo: devuelve el motivo en español si no sirve, o `null`. */
    motivoDeRechazo(archivo, yaHay) {
        if (yaHay >= this.limites.adjuntos) {
            return `Máximo ${this.limites.adjuntos} archivos por mensaje.`;
        }
        if (archivo.size > this.limites.bytes) {
            return `«${archivo.name}» pesa demasiado (máximo ${Math.round(this.limites.bytes / 1024 / 1024)} MB).`;
        }
        if (!archivo.size) {
            return `«${archivo.name}» está vacío.`;
        }
        if (!TIPOS_QUE_SE_SUBEN.test(archivo.name)) {
            return `«${archivo.name}» no se puede enviar. Adjunta una foto, un PDF, un Word, un Excel o un texto.`;
        }
        return null;
    }

    async agregarArchivos(archivos) {
        const id = this.seleccionadaId;
        if (!id) {
            return;
        }
        const borrador = this.borradores[id] || this.borrador;
        for (const archivo of archivos) {
            const motivo = this.motivoDeRechazo(archivo, borrador.adjuntos.length);
            if (motivo) {
                this.notification.add(motivo, { type: "warning" });
                continue;
            }
            const esImagen = /^image\//.test(archivo.type);
            const ficha = {
                clave: `a${++this._contadorDeArchivos}`,
                nombre: archivo.name,
                tamano: archivo.size,
                mime: archivo.type,
                estado: "subiendo",
                local: esImagen ? URL.createObjectURL(archivo) : null,
                id: null,
                error: null,
            };
            borrador.adjuntos.push(ficha);
            const actual = borrador.adjuntos[borrador.adjuntos.length - 1];
            try {
                const subido = await this.subirArchivo(archivo, id);
                actual.id = subido.id;
                actual.mime = subido.mime;
                actual.estado = "listo";
            } catch (error) {
                actual.estado = "error";
                actual.error = mensajeDeError(error);
                this.notification.add(actual.error, { type: "danger" });
            }
        }
    }

    async subirArchivo(archivo, conversacionId) {
        const datos = await new Promise((ok, mal) => {
            const lector = new FileReader();
            lector.onload = () => ok(String(lector.result).split(",")[1] || "");
            lector.onerror = () => mal(new Error("No pude leer el archivo."));
            lector.readAsDataURL(archivo);
        });
        const r = await this.orm.call(MODELO, "subir_adjunto", [conversacionId, archivo.name, datos, archivo.type || null]);
        return r.adjunto;
    }

    quitarAdjunto(clave) {
        const adjuntos = this.borrador.adjuntos;
        const i = adjuntos.findIndex((a) => a.clave === clave);
        if (i < 0) {
            return;
        }
        const [quitado] = adjuntos.splice(i, 1);
        if (quitado.local) {
            URL.revokeObjectURL(quitado.local);
        }
        if (quitado.id) {
            this.orm.silent.call(MODELO, "descartar_adjunto", [quitado.id]).catch(() => {
                /* un archivo sin enviar se limpia solo a los 2 días */
            });
        }
    }

    /** Después de enviar: los archivos ya son del mensaje, solo se sueltan las vistas previas. */
    vaciarBorrador() {
        const borrador = this.borrador;
        for (const a of borrador.adjuntos) {
            if (a.local) {
                URL.revokeObjectURL(a.local);
            }
        }
        borrador.texto = "";
        borrador.adjuntos = [];
        borrador.menciones = [];
        borrador.tareaPara = "";
        borrador.programarPara = "";
    }

    /** El buscador de fotos deja el pie y las fotos en la caja para revisarlos antes de enviar. */
    ponerEnLaCaja({ texto, adjuntos }) {
        const borrador = this.borrador;
        borrador.modo = "respuesta";
        borrador.texto = borrador.texto ? `${borrador.texto}\n${texto}` : texto;
        for (const a of adjuntos) {
            borrador.adjuntos.push({
                clave: `a${++this._contadorDeArchivos}`,
                nombre: a.nombre,
                tamano: a.tamano,
                mime: a.mime,
                estado: "listo",
                local: a.miniatura,
                id: a.id,
                error: null,
            });
        }
    }

    // ------------------------------------------------------------------
    // Foto del catálogo y cotización en PDF
    // ------------------------------------------------------------------

    abrirPanel(panel) {
        this.panel = panel;
    }

    cerrarPanel() {
        this.panel = null;
    }

    async buscarCatalogo(consulta) {
        return this.orm.silent.call(MODELO, "buscar_catalogo", [consulta]);
    }

    async fotosDelCatalogo(productoId) {
        return this.orm.call(MODELO, "fotos_catalogo", [productoId]);
    }

    async enviarFotoDelCatalogo(productoId, fotos, texto = null) {
        const r = await this.orm.call(MODELO, "enviar_foto_catalogo", [this.seleccionadaId, productoId, fotos, texto]);
        this.actualizarFila(r.conversacion);
        await this.refrescarAbierta();
        if (!r.enviado) {
            this.notification.add("Quedó por enviar: el Worker no respondió y se reintenta solo.", { type: "warning" });
        }
        return r;
    }

    async prepararFotoDelCatalogo(productoId, fotos) {
        return this.orm.call(MODELO, "preparar_foto_catalogo", [this.seleccionadaId, productoId, fotos]);
    }

    /** Abre la ventana para adjuntar un archivo del cliente a uno de sus pedidos o facturas. */
    abrirAdjuntar(adjunto) {
        this.adjuntoAAsociar = adjunto;
        this.abrirPanel("adjuntar");
    }

    async documentosDelCliente() {
        return this.orm.call(MODELO, "documentos_del_cliente", [this.seleccionadaId]);
    }

    async adjuntarADocumento(adjuntoId, modelo, registroId) {
        const r = await this._hacer("adjuntar_a_documento", [this.seleccionadaId, adjuntoId, modelo, registroId]);
        if (r) {
            await this.refrescarAbierta();
        }
        return r;
    }

    async cotizacionesAbiertas() {
        return this.orm.call(MODELO, "cotizaciones_abiertas", [this.seleccionadaId]);
    }

    async crearCotizacion(lineas) {
        return this.orm.call(MODELO, "crear_cotizacion", [this.seleccionadaId, lineas]);
    }

    async enviarCotizacion(ordenId, texto) {
        const r = await this.orm.call(MODELO, "enviar_cotizacion", [this.seleccionadaId, ordenId || null, texto || null]);
        this.actualizarFila(r.conversacion);
        await this.refrescarAbierta();
        if (!r.enviado) {
            this.notification.add("Quedó por enviar: el Worker no respondió y se reintenta solo.", { type: "warning" });
        }
        return r;
    }

    // ------------------------------------------------------------------
    // Visor de imágenes
    // ------------------------------------------------------------------

    abrirVisor(imagenes, indice) {
        this.visor = { imagenes, indice };
    }

    cerrarVisor() {
        this.visor = null;
    }

    // ------------------------------------------------------------------
    // Respuestas rápidas y «Sugerir»
    // ------------------------------------------------------------------

    async textoDeRapida(atajo) {
        const r = await this.orm.call("dcasa.respuesta.rapida", "texto_para", [this.seleccionadaId, atajo]);
        return r.texto;
    }

    async sugerir() {
        return this.orm.call(MODELO, "sugerir_respuesta", [this.seleccionadaId]);
    }
}
