// Los clientes de Odoo con su caché, compartidos por todas las conversaciones de un mismo isolate:
// la configuración (60 s) y la lista de herramientas (5 min) se piden una vez, no una por mensaje.

import { CargadorConfig, type Config } from "../config";
import type { Env } from "../env";
import { CargadorHerramientas, OdooCliente, type DefHerramienta } from "./cliente";

let cliente: OdooCliente | undefined;
let config: CargadorConfig | undefined;
let herramientas: CargadorHerramientas | undefined;

export function odooDe(env: Env): OdooCliente {
  cliente ??= new OdooCliente(env.DCASA, env.JUAN_ODOO_TOKEN ?? "");
  return cliente;
}

export function obtenerConfig(env: Env): Promise<Config> {
  config ??= new CargadorConfig(() => odooDe(env).config());
  return config.obtener();
}

export function obtenerHerramientas(env: Env): Promise<DefHerramienta[]> {
  herramientas ??= new CargadorHerramientas(() => odooDe(env).herramientas());
  return herramientas.obtener();
}

/** Solo para las pruebas: olvida lo guardado. */
export function olvidarCaches(): void {
  cliente = undefined;
  config = undefined;
  herramientas = undefined;
}
