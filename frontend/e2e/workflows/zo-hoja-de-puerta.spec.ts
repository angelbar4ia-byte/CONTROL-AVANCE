import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * La hoja de una puerta (D-632, D-637): al elegir la puerta en el plano su detalle trae «Hoja» —de qué lado abre, en qué
 * extremo van las bisagras y cuánto está abierta— y se guarda al pulsar. Es dibujo y especificación: no cambia lo que
 * descuenta. Cambiar la hoja se deshace con Ctrl+Z.
 */

const ROLES_ZO = ['control'] as const;

type VanoEnPlano = { id: string; lado_hoja: number; bisagra: number; apertura_grados: number };

test.describe('Cuantificador · hoja de la puerta', () => {
  test.skip(!hayRoles(...ROLES_ZO), motivoSinRoles(...ROLES_ZO));
  test.setTimeout(120_000);

  test('la hoja se cambia desde el detalle de la puerta y se deshace', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `HOJ-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Puerta',
      archivo_url: 'planos/puerta.dwg',
    });
    const trazo = await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'pdf',
      geometria_wkt: 'LINESTRING(0 0, 10 0)',
      enlaces: [{ medida: 'longitud', factor: '1', actividad_id: actividad!.id }],
    });
    await llamarApi(request, 'control', 'POST', `/trazos/${trazo.trazo_id}/vanos`, {
      clave: 'P-01', tipo: 'puerta', ancho_m: '0.9', alto_m: '2.1', antepecho_m: '0', piezas: 1, posicion_m: '5',
    });
    const hoja = async () => (await llamarApi<VanoEnPlano[]>(request, 'control', 'GET', `/planos/${plano.id}/vanos`))[0]!;
    expect(await hoja()).toMatchObject({ lado_hoja: 1, apertura_grados: 90 });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const vano = (await page.locator('[data-vano-id] .visor__vano-zona').first().boundingBox())!;
    await page.mouse.click(vano.x + vano.width / 2, vano.y + vano.height / 2);
    const detalle = page.getByRole('group', { name: 'Elemento colocado' });
    await expect(detalle).toBeVisible();

    await detalle.getByRole('button', { name: 'Abre al otro lado' }).click();
    await expect.poll(async () => (await hoja()).lado_hoja).toBe(-1);
    await detalle.getByRole('button', { name: 'Bisagra izquierda' }).click();
    await expect.poll(async () => (await hoja()).bisagra).toBe(-1);
    await detalle.getByRole('button', { name: '45°' }).click();
    await expect.poll(async () => (await hoja()).apertura_grados).toBe(45);

    // Ctrl+Z devuelve la apertura anterior.
    await page.keyboard.press('Control+z');
    await expect.poll(async () => (await hoja()).apertura_grados).toBe(90);
  });

  test('una puerta se borra con Supr y con la herramienta Borrar, y se deshace', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `BOR-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Puertas',
      archivo_url: 'planos/puertas.dwg',
    });
    const trazo = await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'pdf',
      geometria_wkt: 'LINESTRING(0 0, 10 0)',
      enlaces: [{ medida: 'longitud', factor: '1', actividad_id: actividad!.id }],
    });
    await llamarApi(request, 'control', 'POST', `/trazos/${trazo.trazo_id}/vanos`, {
      clave: 'P-01', tipo: 'puerta', ancho_m: '0.9', alto_m: '2.1', antepecho_m: '0', piezas: 1, posicion_m: '5',
    });
    const vanos = async () => (await llamarApi<VanoEnPlano[]>(request, 'control', 'GET', `/planos/${plano.id}/vanos`)).length;
    expect(await vanos()).toBe(1);

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const centro = async () => {
      const caja = (await page.locator('[data-vano-id] .visor__vano-zona').first().boundingBox())!;
      return [caja.x + caja.width / 2, caja.y + caja.height / 2] as const;
    };

    // --- 1. Seleccionar la puerta y pulsar Supr ---------------------------------------------------------------------
    const [x1, y1] = await centro();
    await page.mouse.click(x1, y1);
    await expect(page.getByRole('group', { name: 'Elemento colocado' })).toBeVisible();
    await page.keyboard.press('Delete');
    await expect.poll(vanos).toBe(0);
    await page.keyboard.press('Control+z');
    await expect.poll(vanos).toBe(1);

    // --- 2. La herramienta Borrar quita la puerta, no el muro ---------------------------------------------------------
    await page.getByRole('toolbar', { name: 'Herramientas de trazo' }).getByRole('button', { name: 'Borrar', exact: true }).click();
    const [x2, y2] = await centro();
    await page.mouse.click(x2, y2);
    await expect.poll(vanos).toBe(0);
    await expect(page.locator('.visor__trazo')).toHaveCount(1); // el muro sigue
    await expect(page.getByRole('dialog', { name: /Borrar trazo/ })).toHaveCount(0);
  });
});
