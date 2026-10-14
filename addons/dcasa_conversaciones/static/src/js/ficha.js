/**
 * La ficha del cliente (al lado del hilo en pantallas amplias; encima, a pedido, en las demás): quién es, si es Socio (solo lectura), asignación, etiquetas,
 * oportunidades, compras, seguimiento, notas y «qué sabe el bot de esta persona».
 */
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { esCelular } from "./preferencias";
import { colorDeEtiqueta, cuando, dolares, hora, iniciales, iconoDeCanal, numero } from "./utilidades";

export class FichaCliente extends Component {
    static template = "dcasa_conversaciones.Ficha";
    static props = { almacen: Object };

    setup() {
        this.almacen = useState(this.props.almacen);
        this.action = useService("action");
        this.local = useState({ copiado: false, creando: false });
        this.colorDeEtiqueta = colorDeEtiqueta;
        this.dolares = dolares;
        this.numero = numero;
        this.iniciales = iniciales;
        this.iconoDeCanal = iconoDeCanal;
        this.hora = hora;
        this.cuando = (iso) => cuando(iso, this.almacen.ahora);
    }

    get f() {
        return this.almacen.ficha;
    }

    get idsDeEtiquetas() {
        return (this.almacen.conversacion?.etiquetas || []).map((e) => e.id);
    }

    /** Las etiquetas que ya tiene pero están inactivas (se conservan; no se pueden volver a poner). */
    get etiquetasInactivas() {
        const activas = new Set(this.almacen.etiquetas.map((e) => e.id));
        return (this.almacen.conversacion?.etiquetas || []).filter((e) => !activas.has(e.id));
    }

    alternarEtiqueta(id) {
        const ids = new Set(this.idsDeEtiquetas);
        if (ids.has(id)) {
            ids.delete(id);
        } else {
            ids.add(id);
        }
        this.almacen.ponerEtiquetas([...ids]);
    }

    alAsignar(ev) {
        this.almacen.asignar(Number(ev.target.value) || null);
    }

    get seguimiento() {
        const s = this.f?.seguimiento;
        if (!s) {
            return null;
        }
        if (s.pendiente) {
            return { texto: `Seguimiento n.º ${s.enviados + 1} en camino: ya se le pidió al asistente.`, cancelar: false };
        }
        if (s.proximo) {
            return {
                texto: `Seguimiento ${s.enviados + 1} de ${s.maximo} pendiente para ${this.cuando(s.proximo)}.`,
                cancelar: true,
            };
        }
        if (s.enviados) {
            return { texto: `Se enviaron ${s.enviados} de ${s.maximo} seguimientos.`, cancelar: false };
        }
        return { texto: "Sin seguimiento programado.", cancelar: false };
    }

    cancelarSeguimiento() {
        this.almacen.cancelarSeguimiento();
    }

    async crearOportunidad() {
        this.local.creando = true;
        try {
            await this.almacen.crearOportunidad();
        } finally {
            this.local.creando = false;
        }
    }

    abrir(modelo, id, nombre) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: nombre,
            res_model: modelo,
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    abrirContacto() {
        if (this.f.cliente.id) {
            this.abrir("res.partner", this.f.cliente.id, this.f.cliente.nombre);
        }
    }

    async copiarCelular() {
        try {
            await navigator.clipboard.writeText(this.f.cliente.celular);
            this.local.copiado = true;
            setTimeout(() => (this.local.copiado = false), 1800);
        } catch {
            /* sin permiso para copiar: no pasa nada */
        }
    }

    volver() {
        this.almacen.cerrarFicha();
    }

    /** Esc cierra la ficha y el foco vuelve al botón «Cliente» (en celular, la flecha ya hace de «volver»). */
    alTeclear(ev) {
        if (ev.key === "Escape" && this.almacen.fichaAbierta && !esCelular()) {
            ev.stopPropagation();
            this.almacen.cerrarFicha();
            document.querySelector(".o_dcj_boton_ficha")?.focus();
        }
    }
}
