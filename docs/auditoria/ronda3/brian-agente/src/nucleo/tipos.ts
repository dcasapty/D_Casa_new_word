/**
 * Formato neutro de Brian (mismo espíritu que addons/dcasa_brian/models/proveedores.py:3-18).
 * Ningún tipo de aquí depende de Cloudflare: el núcleo se prueba en Node.
 */

export interface ImagenNeutra {
  mimetype: string;
  datos: string; // base64
}

export interface LlamadaHerramienta {
  id: string;
  nombre: string;
  argumentos: Record<string, unknown>;
}

export type MensajeNeutro =
  | { rol: "user"; texto: string; imagenes?: ImagenNeutra[] }
  | {
      rol: "assistant";
      texto: string;
      llamadas?: LlamadaHerramienta[];
      /** Bloques crudos del proveedor que respondió; se reenvían SIN tocar si se vuelve a él
       *  (Claude 5.5 ata los bloques de pensamiento a la conversación: editar el historial da 400). */
      crudo?: { proveedor: string; contenido: unknown };
    }
  | { rol: "tool"; llamadaId: string; nombre: string; texto: string; error?: boolean };

/** Esquema JSON que viaja al modelo (contrato común con r3-brian-habilidades). */
export interface EsquemaHerramienta {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export type Esfuerzo = "minimal" | "low" | "medium" | "high";

export interface Solicitud {
  modelo: string;
  /** Prefijo ESTABLE: no lleva hora, nombre ni pantalla (eso va en un mensaje de usuario). */
  sistema: string;
  herramientas: EsquemaHerramienta[];
  mensajes: MensajeNeutro[];
  maxTokens: number;
  esfuerzo?: Esfuerzo;
  /** Metadatos para AI Gateway (cf-aig-metadata, máx. 5 entradas). */
  metadatos?: Record<string, string>;
}

export interface Uso {
  /** Tokens de entrada SIN caché (los que se cobran a precio completo). */
  entrada: number;
  salida: number;
  cacheLectura: number;
  cacheEscritura: number;
}

export type Fin = "fin" | "herramientas" | "limite" | "rechazo";

export interface Respuesta {
  texto: string;
  llamadas: LlamadaHerramienta[];
  fin: Fin;
  uso: Uso;
  proveedor: string;
  modelo: string;
  crudo?: unknown;
}

export interface Proveedor {
  readonly id: string;
  chatear(solicitud: Solicitud, senal?: AbortSignal): Promise<Respuesta>;
}

export class ErrorProveedor extends Error {
  constructor(
    mensaje: string,
    readonly reintentable: boolean,
    readonly estado?: number,
  ) {
    super(mensaje);
    this.name = "ErrorProveedor";
  }
}

export type FetchLike = (url: string, init: RequestInit) => Promise<Response>;

export interface Persona {
  id: string;
  nombre: string;
  rol: "duena" | "gerencia" | "vendedora";
  /** Áreas que su perfil permite (catálogo, clientes, ventas, contabilidad…). */
  areas: string[];
}
