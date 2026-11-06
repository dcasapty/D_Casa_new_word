/**
 * Sofía, la asistente del CRM: muestra lo que propone y deja aprobarlo o descartarlo en un clic.
 * Todo se decide en el servidor (dcasa.sofia): quién ve qué, qué se puede hacer y si todavía hace falta. Aquí solo se
 * muestra, se edita el mensaje antes de enviarlo y se llama a la acción que la persona elige.
 *
 * La pantalla (2026-11-06, «Sofía puede mejorar mucho, sobre todo la interfaz visual»): lo urgente arriba por secciones
 * («Hoy sin falta», «Hoy», «Cuando puedas»), un filtro rápido por tipo y, para Gerencia, por vendedora, con conteos;
 * el mensaje se lee como en el chat y se edita con «Editar»; al aprobar, la tarjeta dice lo que pasó EN SU LUGAR y
 * después se cierra despacio (la pantalla no salta ni deja otro botón bajo el dedo).
 */
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { mensajeDeError } from "@dcasa_conversaciones/js/utilidades";

const MODELO = "dcasa.sofia";
/** Por aquí pasa el mensaje a la pantalla de Conversaciones, UNA sola vez (ver conversaciones.js). No viaja en la acción:
 * quedaría guardado en la dirección y volvería a aparecer al recargar. */
export const CLAVE_MENSAJE_PARA_EL_CHAT = "dcasa.sofia.mensaje_para_el_chat";
const VIGENCIA_DEL_MENSAJE = 2 * 60 * 1000;
/** Cuánto se queda la tarjeta resuelta diciendo lo que pasó antes de cerrarse (y cuánto tarda en cerrarse). */
export const MS_HECHA = 2500;
export const MS_CERRAR = 350;

/** Los tipos, en el orden en que se atienden: nombre corto para el filtro e ícono. */
export const TIPOS = [
    { clave: "contestar", nombre: "Contestarle", icono: "fa-reply" },
    { clave: "vence", nombre: "Cotización vence", icono: "fa-hourglass-half" },
    { clave: "escribir", nombre: "Escribirle", icono: "fa-comment-o" },
    { clave: "pedir_datos", nombre: "Pedir sus datos", icono: "fa-id-card-o" },
    { clave: "guardar_datos", nombre: "Guardar sus datos", icono: "fa-address-card-o" },
    { clave: "llamar", nombre: "Llamarlo", icono: "fa-phone" },
    { clave: "asignar", nombre: "Darle vendedora", icono: "fa-user-plus" },
    { clave: "sincronizar", nombre: "Poner su vendedora", icono: "fa-exchange" },
    { clave: "guardar_correo", nombre: "Guardar su correo", icono: "fa-envelope-o" },
];
const TIPO = Object.fromEntries(TIPOS.map((t) => [t.clave, t]));

/** Las secciones, de lo más urgente a lo que puede esperar (los nombres vienen del servidor). */
const PRIORIDADES = [3, 2, 1];

const BOTONES = {
    chat: { texto: "Abrir el chat", conMensaje: "Abrir el chat con este mensaje", icono: "fa-comments" },
    enviar: { texto: "Enviar ya", icono: "fa-paper-plane" },
    tarea: { texto: "Crear tarea", icono: "fa-calendar-check-o" },
    guardar: { texto: "Guardar en su ficha", icono: "fa-check" },
    responder: { texto: "Guardar y responderle", icono: "fa-comments" },
    asignar: { texto: "Asignar", icono: "fa-user-plus" },
};

export const SIN_VENDEDORA = "__sin__";
export const TODAS = "todas";

export const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
    "Noviembre", "Diciembre"];
const DIAS = Array.from({ length: 31 }, (_, i) => i + 1);

/** «Guarda sus datos»: lo que se ve en los campos de la tarjeta (el cumpleaños «MM-DD» en día y mes). */
export function camposEditables(campos) {
    const [mes, dia] = (campos.cumple || "").split("-");
    return {
        nombre: campos.nombre || "",
        correo: campos.correo || "",
        dia: dia ? String(Number(dia)) : "",
        mes: mes ? String(Number(mes)) : "",
    };
}

/** Lo que se manda al servidor: solo los datos que Sofía propuso; vacío = no guardar ese dato. */
export function camposParaGuardar(propuestos, editados) {
    const salida = {};
    if ("nombre" in propuestos) {
        salida.nombre = editados.nombre.trim();
    }
    if ("correo" in propuestos) {
        salida.correo = editados.correo.trim();
    }
    if ("cumple" in propuestos) {
        const dos = (n) => String(n).padStart(2, "0");
        salida.cumple = editados.dia && editados.mes ? `${dos(editados.mes)}-${dos(editados.dia)}` : "";
    }
    return salida;
}

/** «03-12» → «12 de marzo». */
export function cumpleLegible(cumple) {
    const [mes, dia] = (cumple || "").split("-").map(Number);
    return mes && dia ? `${dia} de ${MESES[mes - 1].toLowerCase()}` : "";
}

/** ¿La propuesta es de esta vendedora? (``SIN_VENDEDORA``: las que no son de nadie, menos las de repartir). */
export function esDe(propuesta, para) {
    if (para === TODAS) {
        return true;
    }
    if (para === SIN_VENDEDORA) {
        return !propuesta.para_id && propuesta.grupo !== "repartir";
    }
    return String(propuesta.para_id) === para;
}

/** Los filtros por tipo con su conteo: solo los tipos que hay (y el elegido, aunque ya no quede ninguno). */
export function filtrosPorTipo(propuestas, elegido) {
    const cuenta = {};
    for (const p of propuestas) {
        cuenta[p.tipo] = (cuenta[p.tipo] || 0) + 1;
    }
    const conocidos = TIPOS.filter((t) => cuenta[t.clave] || t.clave === elegido)
        .map((t) => ({ ...t, cuantas: cuenta[t.clave] || 0 }));
    const otros = Object.keys(cuenta).filter((clave) => !TIPO[clave])
        .map((clave) => ({ clave, nombre: clave, icono: "fa-lightbulb-o", cuantas: cuenta[clave] }));
    return [{ clave: TODAS, nombre: "Todo", icono: "fa-th-list", cuantas: propuestas.length }, ...conocidos, ...otros];
}

/** Para Gerencia: cada vendedora con lo que tiene pendiente (y «Sin vendedora» si hay). */
export function filtrosPorVendedora(propuestas, elegida) {
    const vistas = new Map();
    let sinVendedora = 0;
    for (const p of propuestas) {
        if (p.para_id) {
            const clave = String(p.para_id);
            const antes = vistas.get(clave) || { clave, nombre: p.para, cuantas: 0 };
            antes.cuantas++;
            vistas.set(clave, antes);
        } else if (p.grupo !== "repartir") {
            sinVendedora++;
        }
    }
    const lista = [...vistas.values()].sort((a, b) => a.nombre.localeCompare(b.nombre));
    if (sinVendedora || elegida === SIN_VENDEDORA) {
        lista.push({ clave: SIN_VENDEDORA, nombre: "Sin vendedora", cuantas: sinVendedora });
    }
    return [{ clave: TODAS, nombre: "Todo el equipo", cuantas: propuestas.length }, ...lista];
}

/** Las secciones de la lista, de lo más urgente a lo que puede esperar (sin las vacías). */
export function secciones(propuestas) {
    const salida = [];
    for (const prioridad of PRIORIDADES) {
        const de = propuestas.filter((p) => (PRIORIDADES.includes(p.prioridad) ? p.prioridad : 1) === prioridad);
        if (de.length) {
            salida.push({ prioridad, nombre: de[0].prioridad_nombre || "", propuestas: de });
        }
    }
    return salida;
}

export class SofiaPanel extends Component {
    static template = "dcasa_sofia.Panel";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.meses = MESES;
        this.dias = DIAS;
        this.cumpleLegible = cumpleLegible;
        /** Lo que Sofía proponía cuando se llenaron los campos de cada tarjeta (si una revisión lo cambia, se ponen
         * los datos nuevos en vez de dejar los viejos). */
        this.camposBase = {};
        /** Lo que ya se resolvió en esta pantalla: una revisión que empezó antes no lo vuelve a poner. */
        this.resueltas = new Set();
        this.relojes = new Set();
        this.state = useState({
            datos: null,
            cargando: true,
            revisando: false,
            error: null,
            tipo: TODAS,
            para: TODAS,
            textos: {},
            campos: {},
            editando: {},
            hechas: {},
            ocupada: null,
            enCurso: null,
        });
        onMounted(() => this.empezar());
        onWillUnmount(() => {
            for (const reloj of this.relojes) {
                clearTimeout(reloj);
            }
        });
    }

    /** Lo que ya está pendiente se ve enseguida; desde «Organizar con Sofía», después revisa (con su aviso). */
    async empezar() {
        await this.cargar();
        if (this.props.action?.params?.analizar) {
            await this.analizar();
        }
    }

    async cargar() {
        this.state.cargando = true;
        try {
            this.poner(await this.orm.call(MODELO, "panel", []));
        } catch (error) {
            this.state.error = mensajeDeError(error);
        } finally {
            this.state.cargando = false;
        }
    }

    async analizar() {
        if (this.state.revisando) {
            return;
        }
        this.state.revisando = true;
        try {
            this.poner(await this.orm.call(MODELO, "analizar", []));
        } catch (error) {
            this.notification.add(mensajeDeError(error), { type: "warning" });
            if (!this.state.datos) {
                await this.cargar();
            }
        } finally {
            this.state.revisando = false;
            this.state.cargando = false;
        }
    }

    /** Pone los datos nuevos sin perder lo que alguien estaba editando (un mensaje o los datos para su ficha). */
    poner(datos) {
        datos.propuestas = datos.propuestas.filter((p) => !this.resueltas.has(p.id));
        const textos = {};
        const campos = {};
        const editando = {};
        for (const p of datos.propuestas) {
            textos[p.id] = p.id in this.state.textos ? this.state.textos[p.id] : p.mensaje;
            if (this.state.editando[p.id]) {
                editando[p.id] = true;
            }
            if (p.tipo === "guardar_datos") {
                const base = JSON.stringify(p.campos || {});
                const igual = this.state.campos[p.id] && this.camposBase[p.id] === base;
                campos[p.id] = igual ? this.state.campos[p.id] : camposEditables(p.campos || {});
                this.camposBase[p.id] = base;
            }
        }
        this.state.textos = textos;
        this.state.campos = campos;
        this.state.editando = editando;
        this.state.hechas = {};
        this.state.datos = datos;
        this.state.error = null;
    }

    get d() {
        return this.state.datos;
    }

    get esGerencia() {
        return !!this.d?.es_gerencia;
    }

    /** Las que siguen pendientes (sin las que se acaban de resolver y se están cerrando). */
    get vivas() {
        return (this.d?.propuestas || []).filter((p) => !(p.id in this.state.hechas));
    }

    get filtrosTipo() {
        return filtrosPorTipo(this.vivas.filter((p) => !this.esGerencia || esDe(p, this.state.para)), this.state.tipo);
    }

    get filtrosVendedora() {
        const tipo = this.state.tipo;
        return filtrosPorVendedora(this.vivas.filter((p) => tipo === TODAS || p.tipo === tipo), this.state.para);
    }

    /** Lo que se ve con los filtros (con las resueltas en su lugar mientras dicen lo que pasó). */
    get propuestas() {
        const { tipo, para } = this.state;
        return (this.d?.propuestas || []).filter((p) => (tipo === TODAS || p.tipo === tipo)
            && (!this.esGerencia || esDe(p, para)));
    }

    get secciones() {
        return secciones(this.propuestas).map((s) => ({
            ...s, cuantas: s.propuestas.filter((p) => !(p.id in this.state.hechas)).length,
        }));
    }

    /** «Revisó hoy a las 2:05 p. m. (la pidió Ana)» (o «(revisión de la mañana)»). */
    get ultimaRevision() {
        const ultima = this.d?.ultima;
        if (!ultima) {
            return "";
        }
        let cuando = ultima.hace || "";
        const fecha = ultima.cuando ? new Date(ultima.cuando) : null;
        if (fecha && !isNaN(fecha) && ["hoy", "ayer"].includes(cuando)) {
            cuando += ` a las ${fecha.toLocaleTimeString("es-PA", { hour: "numeric", minute: "2-digit" })}`;
        }
        const quien = ultima.quien ? `la pidió ${ultima.quien}` : (ultima.origen || "").toLowerCase();
        // Sin plantillas `…` anidadas: el minificador de Odoo (rjsmin) se come los espacios de la de adentro.
        return "Revisó " + cuando + (quien ? " (" + quien + ")" : "");
    }

    /** Lo que dice la pantalla cuando el filtro ya no tiene nada (lo demás sigue ahí). */
    get textoFiltroVacio() {
        const tipo = this.state.tipo !== TODAS ? (TIPO[this.state.tipo] || { nombre: this.state.tipo }).nombre : "";
        const persona = this.esGerencia && this.state.para !== TODAS
            ? this.filtrosVendedora.find((f) => f.clave === this.state.para)?.nombre || "" : "";
        if (tipo && persona) {
            return `No queda nada de «${tipo}» para ${persona}.`;
        }
        if (tipo) {
            return `No queda nada de «${tipo}».`;
        }
        return persona ? `${persona} no tiene nada pendiente.` : "No queda nada aquí.";
    }

    /** Cuántas quedan por sección, para el resumen de arriba (con el filtro de vendedora, sin el de tipo). */
    get resumen() {
        const de = this.vivas.filter((p) => !this.esGerencia || esDe(p, this.state.para));
        return secciones(de).map((s) => ({ prioridad: s.prioridad, nombre: s.nombre, cuantas: s.propuestas.length }));
    }

    get omitidas() {
        return Object.values(this.d?.omitidas || {}).reduce((total, n) => total + n, 0);
    }

    tipo(propuesta) {
        return TIPO[propuesta.tipo] || { nombre: propuesta.tipo_nombre, icono: "fa-lightbulb-o" };
    }

    boton(propuesta, accion, indice) {
        const base = BOTONES[accion] || { texto: accion, icono: "fa-check" };
        let texto = base.texto;
        if (accion === "chat" && propuesta.mensaje) {
            texto = base.conMensaje;
        } else if (accion === "asignar" && propuesta.destino) {
            texto = `Asignar a ${propuesta.destino}`;
        } else if (accion === "tarea" && propuesta.tipo === "llamar") {
            texto = "Crear tarea: llamarlo";
        } else if (accion === "guardar" && propuesta.acciones.includes("responder")) {
            texto = "Solo guardar";
        }
        // La primera es la principal (grande); las demás, al lado y más discretas.
        return { ...base, texto, clase: indice === 0 ? "btn-primary o_sofia_principal" : "btn-outline-primary" };
    }

    /** Cuántas líneas necesita la caja del mensaje para verse completo (sin pasar de 12). */
    filas(texto) {
        const lineas = (texto || "").split("\n").reduce((total, linea) => total + Math.max(1, Math.ceil(linea.length / 70)), 0);
        return Math.min(12, Math.max(3, lineas));
    }

    editable(propuesta) {
        return !!propuesta.mensaje && propuesta.acciones.some((a) => ["chat", "enviar", "tarea"].includes(a));
    }

    cambiado(propuesta) {
        return (this.state.textos[propuesta.id] ?? "") !== (propuesta.mensaje ?? "");
    }

    editar(propuesta) {
        this.state.editando[propuesta.id] = true;
    }

    dejarDeEditar(propuesta) {
        delete this.state.editando[propuesta.id];
    }

    /** Las resueltas que están diciendo lo que pasó se van ya: con otro filtro no tendrían lugar. */
    soltarHechas() {
        const ids = Object.keys(this.state.hechas).map(Number);
        if (ids.length) {
            this.d.propuestas = this.d.propuestas.filter((p) => !ids.includes(p.id));
            this.state.hechas = {};
        }
    }

    elegirTipo(clave) {
        this.soltarHechas();
        this.state.tipo = clave;
    }

    elegirPersona(clave) {
        this.soltarHechas();
        this.state.para = clave;
    }

    verTodo() {
        this.elegirTipo(TODAS);
        this.state.para = TODAS;
    }

    /** La tarjeta se queda en su lugar, del mismo alto, diciendo lo que pasó; después se cierra despacio. */
    resuelta(propuesta, texto, clase, ev) {
        this.resueltas.add(propuesta.id);
        delete this.state.textos[propuesta.id];
        delete this.state.campos[propuesta.id];
        delete this.state.editando[propuesta.id];
        const tarjeta = ev?.target?.closest?.(".o_sofia_tarjeta");
        const alto = tarjeta ? Math.round(tarjeta.getBoundingClientRect().height) : 0;
        this.state.hechas[propuesta.id] = { texto, clase, alto, cerrando: false };
        this.despues(MS_HECHA, () => {
            if (this.state.hechas[propuesta.id]) {
                this.state.hechas[propuesta.id].cerrando = true;
                this.despues(MS_CERRAR, () => this.quitar(propuesta));
            }
        });
    }

    despues(ms, fn) {
        const reloj = setTimeout(() => {
            this.relojes.delete(reloj);
            fn();
        }, ms);
        this.relojes.add(reloj);
    }

    quitar(propuesta) {
        this.resueltas.add(propuesta.id);
        if (this.d) {
            this.d.propuestas = this.d.propuestas.filter((p) => p.id !== propuesta.id);
        }
        delete this.state.textos[propuesta.id];
        delete this.state.campos[propuesta.id];
        delete this.state.editando[propuesta.id];
        delete this.state.hechas[propuesta.id];
    }

    async aplicar(propuesta, accion, ev) {
        if (this.state.ocupada) {
            return;
        }
        this.state.ocupada = propuesta.id;
        this.state.enCurso = accion;
        try {
            const texto = propuesta.mensaje ? this.state.textos[propuesta.id] ?? "" : null;
            const extra = { texto };
            if (propuesta.tipo === "guardar_datos" && this.state.campos[propuesta.id]) {
                extra.campos = camposParaGuardar(propuesta.campos || {}, this.state.campos[propuesta.id]);
            }
            const respuesta = await this.orm.call(MODELO, "aplicar", [propuesta.id, accion], extra);
            // «Abrir el chat con este mensaje» deja el texto; «Guardar y responderle» pide a Juan un borrador.
            if ((respuesta.texto || respuesta.sugerir) && respuesta.conversacion_id) {
                try {
                    window.sessionStorage.setItem(CLAVE_MENSAJE_PARA_EL_CHAT, JSON.stringify({
                        conversacion_id: respuesta.conversacion_id,
                        texto: respuesta.texto || "",
                        sugerir: !!respuesta.sugerir,
                        vence: Date.now() + VIGENCIA_DEL_MENSAJE,
                    }));
                } catch {
                    // Sin almacenamiento del navegador el chat abre igual, sin el mensaje escrito.
                }
            }
            if (respuesta.accion) {
                // Se va a otra pantalla (el chat): el aviso la acompaña.
                this.quitar(propuesta);
                this.notification.add(respuesta.resultado, { type: respuesta.ya_no_hace_falta ? "warning" : "success" });
                await this.action.doAction(respuesta.accion);
            } else {
                this.resuelta(propuesta, respuesta.resultado, respuesta.ya_no_hace_falta ? "o_aviso" : "o_listo", ev);
            }
        } catch (error) {
            this.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.state.ocupada = null;
            this.state.enCurso = null;
        }
    }

    /** «Descartar» como siempre: un toque, sin preguntar; la tarjeta dice que se descartó antes de irse. */
    async descartar(propuesta, ev) {
        if (this.state.ocupada) {
            return;
        }
        this.state.ocupada = propuesta.id;
        this.state.enCurso = "descartar";
        try {
            const respuesta = await this.orm.call(MODELO, "descartar", [propuesta.id]);
            this.resuelta(propuesta, respuesta.resultado, "o_descartada", ev);
        } catch (error) {
            this.notification.add(mensajeDeError(error), { type: "danger" });
        } finally {
            this.state.ocupada = null;
            this.state.enCurso = null;
        }
    }

    abrirOportunidad(propuesta) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "crm.lead",
            res_id: propuesta.lead_id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("dcasa_sofia.panel", SofiaPanel);
