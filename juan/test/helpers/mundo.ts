// Un mundo completo para probar el motor de UNA conversación: SQLite de Node, reloj manual,
// Odoo falso, canal falso y un modelo guionado. Todo pasa por el código real del motor.
import { CargadorConfig } from "../../src/config";
import { CargadorHerramientas } from "../../src/odoo/cliente";
import type { Env } from "../../src/env";
import type { Entrante } from "../../src/canales/tipos";
import { MotorConversacion, type DepsMotor } from "../../src/motor/conversacion";
import { AlmacenGlobal } from "../../src/motor/global";
import { mesDelNegocio } from "../../src/config";
import type { Uso } from "../../src/motor/precios";
import { CanalFalso } from "./canalFalso";
import { modeloGuionado, type ModeloGuionado, type PasoDelGuion } from "./modeloGuionado";
import { OdooFalso } from "./odooFalso";
import { crearSqlNode } from "./sqlNode";
import type { CanalId } from "../../src/canales/tipos";
import type { LanguageModel } from "ai";
import type { ProveedorIa, SeleccionDeModelo } from "../../src/motor/proveedores";

/** Viernes 9 de octubre de 2026, 10:00 en Panamá (UTC-5). */
export const AHORA_INICIAL = Date.parse("2026-10-09T15:00:00Z");

export interface OpcionesMundo {
  canal?: CanalId;
  idExterno?: string;
  config?: Record<string, unknown>;
  topeDiario?: number;
  urlPublica?: string;
  transcribir?: DepsMotor["transcribir"];
  mirarImagen?: DepsMotor["mirarImagen"];
  /** Proveedores de IA con clave (por defecto solo Anthropic). */
  proveedores?: ProveedorIa[];
  /** Un Odoo compartido con otras conversaciones (para probar que no se mezclan). */
  odoo?: OdooFalso;
  /** Para pruebas con un servidor falso: arma el modelo real del proveedor. Si no, se usa el guion. */
  fabrica?: (sel: SeleccionDeModelo) => LanguageModel;
}

export function crearMundo(op: OpcionesMundo = {}) {
  const canalId = op.canal ?? "whatsapp_qr";
  const idExterno = op.idExterno ?? "50760261919";
  let t = AHORA_INICIAL;
  let alarma: number | null = null;
  const odoo = op.odoo ?? new OdooFalso();
  if (op.config) odoo.rawConfig = { ...(odoo.rawConfig as object), ...op.config };
  const canal = new CanalFalso(canalId);
  const sqlGlobal = new AlmacenGlobal(crearSqlNode());
  const idsDeModelo: string[] = [];
  const selecciones: SeleccionDeModelo[] = [];
  const cargadorConfig = new CargadorConfig(() => odoo.config(), () => t);
  const cargadorHerramientas = new CargadorHerramientas(() => odoo.herramientas(), () => t);
  const mundo = {
    odoo,
    canal,
    gastoGlobal: sqlGlobal,
    idsDeModelo,
    /** Cada vez que el motor pidió un modelo: proveedor, modelo y nivel. */
    selecciones,
    /** Qué proveedores tienen clave ahora (se puede cambiar en la prueba). */
    proveedores: (op.proveedores ?? ["anthropic"]) as ProveedorIa[],
    /** El modelo que usarán TODOS los turnos (se cambia con `guion`). */
    modelo: modeloGuionado([{ texto: "(sin guion)" }]) as ModeloGuionado,
    registros: [] as { nivel: string; mensaje: string }[],
    fallosDeGlobal: false,
    ahora: () => t,
    alarmaProgramada: () => alarma,
    guion(pasos: PasoDelGuion[], id?: string): ModeloGuionado {
      mundo.modelo = modeloGuionado(pasos, id);
      return mundo.modelo;
    },
    entrante,
    escribir,
    pasar,
    conversar,
    motor: undefined as unknown as MotorConversacion,
    deps: undefined as unknown as DepsMotor,
    config: undefined as unknown as () => Promise<import("../../src/config").Config>,
    gastoDelMes() {
      return sqlGlobal.gastoMes(mesDelNegocio("America/Panama", t)).usd;
    },
  };

  let n = 0;
  function entrante(texto: string | undefined, extra: Partial<Entrante> = {}): Entrante {
    n++;
    return {
      canal: canalId,
      id_externo: idExterno,
      id_mensaje: `wamid-${n}`,
      nombre: "Karen",
      celular: canalId.startsWith("whatsapp") ? idExterno : undefined,
      texto,
      adjuntos: [],
      ts: t,
      ...extra,
    };
  }

  const deps: DepsMotor = {
    sql: crearSqlNode(),
    env: {} as Env,
    ahora: () => t,
    fijarAlarma: async (ts) => {
      alarma = ts;
    },
    odoo,
    config: () => cargadorConfig.obtener(),
    herramientas: () => cargadorHerramientas.obtener(),
    canal: () => canal,
    modelo: (sel) => {
      idsDeModelo.push(sel.modelo);
      selecciones.push(sel);
      return op.fabrica ? op.fabrica(sel) : mundo.modelo;
    },
    proveedoresDisponibles: () => mundo.proveedores,
    global: {
      gastoMes: async (mes) => {
        if (mundo.fallosDeGlobal) throw new Error("global caído");
        return sqlGlobal.gastoMes(mes).usd;
      },
      registrarGasto: async (mes: string, modelo: string, uso: Uso, usd: number, estimado: boolean) => {
        sqlGlobal.registrarGasto(mes, modelo, uso, usd, estimado);
      },
      guardarSalud: async (clave: string, json: string) => {
        sqlGlobal.guardarSalud(clave, JSON.parse(json), t);
      },
    },
    dormir: async () => {},
    uuid: (() => {
      let u = 0;
      return () => `00000000-0000-4000-8000-${String(++u).padStart(12, "0")}`;
    })(),
    bufferMs: 15_000,
    topeDiario: op.topeDiario,
    urlPublica: op.urlPublica,
    urlSitio: "https://dcasapty.com",
    secretoDeMedios: "secreto-de-prueba",
    transcribir: op.transcribir,
    mirarImagen: op.mirarImagen,
    log: (nivel, mensaje) => {
      mundo.registros.push({ nivel, mensaje });
    },
  };
  mundo.config = () => cargadorConfig.obtener();
  mundo.deps = deps;
  mundo.motor = new MotorConversacion(deps);

  /** Adelanta el reloj, disparando las alarmas que vayan venciendo (como haría Cloudflare). */
  async function pasar(ms: number) {
    const fin = t + ms;
    for (let i = 0; i < 100; i++) {
      if (alarma === null || alarma > fin) break;
      t = Math.max(t, alarma);
      alarma = null;
      await mundo.motor.alarma();
    }
    t = fin;
  }

  async function escribir(texto: string | undefined, extra: Partial<Entrante> = {}) {
    return mundo.motor.ingest(entrante(texto, extra));
  }

  /** Un mensaje del cliente, la ráfaga de 15 s y la respuesta. */
  async function conversar(texto: string, extra: Partial<Entrante> = {}) {
    const r = await escribir(texto, extra);
    await pasar(16_000);
    return r;
  }

  return mundo;
}

export type Mundo = ReturnType<typeof crearMundo>;
