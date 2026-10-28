import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Empalme de versiones del plano (Fase 2).
 *
 *  1. En la versión 2 se enciende «Empalmar la versión anterior»: los trazos de la versión 1 se ven de fantasma.
 *  2. Se alinea con un desfase, se elige un fantasma con un clic y se trae con «Traer el elegido».
 *  3. El trazo se repite en la versión 2 (corrido, con su hueco y su enlace) y la cantidad **no se duplica**.
 *  4. El fantasma desaparece, y el enlace del trazo viejo ya no es vigente (queda como evidencia).
 *  5. «Traer todos» pasa el resto.
 *
 * Es una obra nueva por corrida.
 */

const ROLES_ZA = ['control'] as const;

interface Feature {
  id: string;
  geometry: { type: string; coordinates: number[][][] };
  properties: { enlaces: { vigente: boolean }[] };
}

test.describe('Cuantificador · empalme de versiones', () => {
  test.skip(!hayRoles(...ROLES_ZA), motivoSinRoles(...ROLES_ZA));
  test.setTimeout(150_000);

  test('la versión anterior se ve de fantasma y sus trazos se traen sin duplicar lo medido', async ({ page, request }) => {
    const clave = `EMP-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave,
    });
    await llamarApi(request, 'control', 'POST', `/obras/${obra.id}/generar`, { modo_pago: 'destajo' });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const v1 = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Planta baja',
      archivo_url: 'planos/pb-v1.dwg',
      version: 1,
    });
    const v2 = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Planta baja',
      archivo_url: 'planos/pb-v2.dwg',
      version: 2,
    });
    const area = (x: number) => `POLYGON((${x} 0, ${x + 10} 0, ${x + 10} 10, ${x} 10, ${x} 0))`;
    const enlace = { actividad_id: actividad!.id, medida: 'area', factor: '1' };
    const trazoV1 = (x: number) =>
      llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${v1.id}/trazos`, {
        version_plano: 1,
        fuente: 'dwg',
        geometria_wkt: area(x),
        enlaces: [enlace],
      });
    const a = await trazoV1(0);
    await llamarApi(request, 'control', 'POST', `/trazos/${a.trazo_id}/huecos`, {
      geometria_wkt: 'POLYGON((2 2, 4 2, 4 4, 2 4, 2 2))',
    });
    await trazoV1(30);
    const trazos = async (plano: string) =>
      (await llamarApi<{ features: Feature[] }>(request, 'control', 'GET', `/planos/${plano}/trazos`)).features;
    const cantidad = async () => {
      const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
        request,
        'control',
        'GET',
        `/obras/${obra.id}/cuantificacion`,
      );
      return Number(nodos.find((n) => n.nodo_id === actividad!.id)?.cantidad_medida ?? 0);
    };
    const total = await cantidad(); // 96 (con el hueco) + 100
    expect(total).toBe(196);

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${v2.id}`);
    const funciones = page.getByRole('toolbar', { name: 'Funciones' });

    // --- 1. El fantasma de la versión anterior ---------------------------------------------------------
    await funciones.getByRole('button', { name: 'Empalmar la versión anterior' }).click();
    const fantasmas = page.locator('[data-fantasma-id]');
    await expect(fantasmas).toHaveCount(2);
    const panel = page.getByRole('region', { name: 'Opciones del empalme de versiones' });
    await expect(panel).toContainText('Traer todos (2)');

    // La transparencia se ajusta.
    await panel.getByLabel('Transparencia del fantasma').fill('30');
    await expect(page.getByTestId('empalme')).toHaveCSS('opacity', '0.3');

    // --- 2. Alinear y traer el elegido ----------------------------------------------------------------
    await panel.getByLabel('Desfase X').fill('5');
    await fantasmas.first().locator('path').first().click({ force: true });
    await panel.getByRole('button', { name: 'Traer el elegido' }).click();
    await expect(page.getByRole('status')).toContainText('Trazo traído');

    // --- 3. Se repitió en la versión 2, corrido, y no se duplicó lo medido -------------------------------
    await expect.poll(async () => (await trazos(v2.id)).length).toBe(1);
    const nuevo = (await trazos(v2.id))[0]!;
    const xs = nuevo.geometry.coordinates[0]!.map((p) => p[0]!);
    expect(Math.min(...xs)).toBe(5);
    await expect.poll(cantidad).toBe(total);

    // --- 4. El fantasma se fue y el enlace viejo ya no es vigente -----------------------------------------
    await expect(fantasmas).toHaveCount(1);
    const viejos = await trazos(v1.id);
    const sinVigentes = viejos.filter((t) => t.properties.enlaces.every((e) => !e.vigente));
    expect(sinVigentes).toHaveLength(1);

    // --- 5. Traer todos -----------------------------------------------------------------------------------
    await panel.getByRole('button', { name: /Traer todos/ }).click();
    await expect.poll(async () => (await trazos(v2.id)).length).toBe(2);
    await expect(fantasmas).toHaveCount(0);
    await expect.poll(cantidad).toBe(total);
  });
});
