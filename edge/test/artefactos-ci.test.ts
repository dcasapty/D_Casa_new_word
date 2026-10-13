/**
 * El espacio de artefactos de GitHub Actions es limitado: cada despliegue guarda una copia de la imagen (~420 MB) y, si se
 * llena, el siguiente despliegue falla al subirla («Artifact storage quota has been hit»). Estas pruebas cuidan que:
 *   - la copia de la imagen dure poco (1 día) y siga siendo obligatoria (un fallo al subirla SÍ debe frenar el despliegue);
 *   - lo que es solo diagnóstico (registros) nunca ponga la ejecución en rojo y dure poco;
 *   - el botón de limpieza sea solo a mano, con ensayo por defecto y con los permisos mínimos.
 */
import { describe, expect, it } from "vitest";
import ci from "../../.github/workflows/ci.yml?raw";
import limpiar from "../../.github/workflows/limpiar-artefactos.yml?raw";
import upMedia from "../../.github/workflows/up-media.yml?raw";

/** El paso (`      - …`) que contiene `marca`, hasta el siguiente paso. */
function paso(yaml: string, marca: string): string {
  const lineas = yaml.split("\n");
  const donde = lineas.findIndex((l) => l.includes(marca));
  expect(donde, `no existe «${marca}»`).toBeGreaterThan(-1);
  let inicio = donde;
  while (inicio > 0 && !/^ {6}- /.test(lineas[inicio])) inicio--;
  let fin = donde + 1;
  while (fin < lineas.length && !/^ {6}- /.test(lineas[fin]) && !/^ {0,5}\S/.test(lineas[fin])) fin++;
  return lineas.slice(inicio, fin).join("\n");
}

describe("copias de la imagen en el espacio de GitHub", () => {
  it("en ci.yml la copia de la imagen dura 1 día y su subida sigue siendo obligatoria", () => {
    const imagen = paso(ci, "name: imagen-odoo-${{ github.sha }}");
    expect(imagen).toContain("retention-days: 1");
    expect(imagen).toContain("if-no-files-found: error");
    expect(imagen).not.toContain("continue-on-error");
  });

  it("en up-media.yml la copia de la imagen también dura 1 día y es obligatoria", () => {
    const imagen = paso(upMedia, "name: imagen-odoo-${{ needs.procesar.outputs.commit }}");
    expect(imagen).toContain("retention-days: 1");
    expect(imagen).toContain("if-no-files-found: error");
    expect(imagen).not.toContain("continue-on-error");
  });

  it("los registros de diagnóstico no ponen la ejecución en rojo y duran poco", () => {
    for (const nombre of ["name: simulacro-restauracion", "name: odoo-test-log"]) {
      const registros = paso(ci, nombre);
      expect(registros, nombre).toContain("continue-on-error: true");
      const dias = /retention-days: (\d+)/.exec(registros);
      expect(dias, `${nombre}: sin retention-days`).not.toBeNull();
      expect(Number(dias![1]), nombre).toBeLessThanOrEqual(7);
    }
  });

  it("la prueba de la limpieza corre en el CI", () => {
    expect(ci).toContain(".github/scripts/probar_limpieza_artefactos.sh");
  });
});

describe("el botón «Limpiar copias temporales»", () => {
  it("es solo a mano y ensaya por defecto", () => {
    const disparos = /\non:\n((?:[ \t]+.*\n|[ \t]*\n)+)/.exec(limpiar);
    expect(disparos).not.toBeNull();
    expect(disparos![1]).toContain("workflow_dispatch:");
    expect(disparos![1]).not.toContain("push:");
    expect(disparos![1]).not.toContain("schedule:");
    expect(disparos![1]).not.toContain("pull_request");
    expect(disparos![1]).toMatch(/borrar:[\s\S]*?default: "false"/);
  });

  it("tiene los permisos mínimos: leer el código y borrar artefactos de Actions", () => {
    const permisos = /\npermissions:\n((?: {2}.*\n)+)/.exec(limpiar);
    expect(permisos).not.toBeNull();
    expect(permisos![1].trim().split("\n").map((l) => l.trim()).sort()).toEqual(["actions: write", "contents: read"]);
  });

  it("solo llama al script de limpieza, que se limita a las copias «imagen-odoo-»", () => {
    expect(limpiar).toContain("run: .github/scripts/limpiar_artefactos.sh");
    expect(limpiar).not.toMatch(/PREFIJO/);
    expect(limpiar.match(/uses: /g) ?? []).toHaveLength(1);
  });
});
