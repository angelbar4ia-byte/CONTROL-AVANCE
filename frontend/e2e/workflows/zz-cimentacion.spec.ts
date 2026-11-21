import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * La cimentación de la Fase 4b: el uso «cimentación» de la losa y el muro de cimentación con cotas de desplante, en el panel de zonas del plano.
 *
 *  1. Control de obra pone la zona en uso «cimentación»: la matriz usa el concreto CON-00001 (TD 200) y el concepto nuevo propuesto EJ-802, sin cimbra por m².
 *  2. Un cimiento (muro de cimentación de piedra medido con una línea del plano) toma su altura de las cotas: desplante −0.80 m y corona en el piso de la zona (0.00) son 0.80 m
 *     de altura y 5.32 m³ en 10 m (concepto MCT-01011 del catálogo). Se cambia el desplante a un punto de nivel exterior, se corona a mano, se ponen dos caras y dentellón, se
 *     asigna a un espacio y se quita. Nada de esto toca la matriz de la losa.
 *  3. Costos lee los cimientos sin poder editarlos. Si la corona queda por debajo del desplante el cimiento dice por qué sin romper el panel.
 *
 * Los cimientos se crean por la API (la línea del plano se elige en el visor, que otros specs ya cubren); el spec no crea castillos: el rango 14.0 de `altoPropio` queda
 * reservado para él por si lo hiciera (infraestructura.ts).
 */

const ROLES_C = ['control', 'costos'] as const;

async function prepararCimentacion(request: Parameters<typeof llamarApi>[0], prefijo: string) {
  const sufijo = `${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`.toUpperCase(); // único aun con varias repeticiones en el mismo milisegundo
  const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
  const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
  const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
    cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
    prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
    clave: `${prefijo}-${sufijo}`,
  });
  const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
  const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, { nombre: 'Cimentación', archivo_url: 'planos/cimentacion.dwg' });
  const nombre = `Cimentación ${sufijo}`;
  const zona = await llamarApi<{ id: string }>(request, 'control', 'POST', `/planos/${plano.id}/zonas-de-losa`, {
    nombre,
    altura_libre_m: '0.50',
    espesor_m: '0.14',
  });
  const trazo = async (wkt: string) =>
    (await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, { version_plano: 1, fuente: 'pdf', geometria_wkt: wkt, enlaces: [] })).trazo_id;
  const poligono = await trazo('POLYGON((0 -4, 6 -4, 6 0, 0 0, 0 -4))');
  await llamarApi(request, 'control', 'PUT', `/trazos/${poligono}/losa`, { zona_id: zona.id });
  const linea = await trazo('LINESTRING(0 2, 10 2)'); // 10 unidades de plano = 10 m con la escala sin calibrar
  const punto = await trazo('POINT(3 3)');
  await llamarApi(request, 'control', 'PUT', `/trazos/${punto}/nivel-exterior`, { cota_m: '-1.20', rotulo: 'Desplante norte' });
  return { obra, actividad: actividad!, plano, zona, nombre, linea, punto };
}

type Cimiento = { id: string; cota_desplante_m: number | null; cota_corona_m: number | null; punto_nivel_id: string | null; caras: number; dentellon: boolean; espacio_id: string | null };

test.describe('Cuantificador · cimentación con cotas de desplante', () => {
  test.skip(!hayRoles(...ROLES_C), motivoSinRoles(...ROLES_C));
  test.setTimeout(240_000);

  test('Control de obra: la zona en uso cimentación usa CON-00001 con su concepto propuesto y su sección de cimientos', async ({ page, request }) => {
    const { obra, actividad, plano, zona, nombre } = await prepararCimentacion(request, 'CU');
    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaEl = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaEl.getByRole('button', { name: `Matriz de conceptos de ${nombre}` }).click();
    const matriz = zonaEl.getByTestId('matriz-de-la-zona');
    await matriz.getByLabel('Uso de la losa de la zona').selectOption('cimentacion');
    await expect(matriz.getByTestId('matriz-resumen')).toContainText('CON-00001');
    await expect(matriz.getByTestId('matriz-resumen')).toContainText('cimbra 0.00 m²');
    await expect(matriz.getByText(/EJ-802/).first()).toBeVisible();
    await expect.poll(async () => (await llamarApi<{ uso: string }>(request, 'control', 'GET', `/zonas-de-losa/${zona.id}/matriz`)).uso).toBe('cimentacion');
  });

  test('Control de obra: un cimiento toma su altura de las cotas, su desplante de un punto de nivel, se asigna a un espacio y se quita', async ({ page, request }) => {
    const { obra, actividad, plano, zona, nombre, linea, punto } = await prepararCimentacion(request, 'CC');
    const cimientos = async () => llamarApi<Cimiento[]>(request, 'control', 'GET', `/zonas-de-losa/${zona.id}/cimientos`);
    await llamarApi(request, 'control', 'POST', `/zonas-de-losa/${zona.id}/cimientos`, { trazo_id: linea, cota_desplante_m: -0.8 });

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaEl = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaEl.getByRole('button', { name: `Cimientos de ${nombre}` }).click();
    const panel = zonaEl.getByTestId('cimientos-de-la-zona');
    const cimiento = panel.locator('[data-cimiento-de-la-zona]').first();
    const resumen = cimiento.getByTestId('cimiento-de-la-zona-resumen');
    await expect(resumen).toContainText('Desplante -0.80 m (tecleada)');
    await expect(resumen).toContainText('altura 0.80 m');
    await expect(resumen).toContainText('5.320 m³ de MCT-01011'); // 0.532 m³ por metro × 10 m
    await expect(cimiento.getByText(/MCT-01011 · del catálogo/)).toBeVisible();

    // El desplante de un punto de nivel exterior (-1.20 m): altura 1.20 m; con corona a mano, dos caras y dentellón el volumen cambia.
    await cimiento.getByLabel('Cota de desplante del cimiento 1').fill('');
    await cimiento.getByLabel('Punto de nivel del cimiento 1').selectOption(punto);
    await cimiento.getByRole('button', { name: 'Guardar el cimiento 1' }).click();
    await expect(resumen).toContainText('Desplante -1.20 m (de un punto de nivel exterior)');
    await expect(resumen).toContainText('altura 1.20 m');
    await cimiento.getByLabel('Cota de la corona del cimiento 1').fill('0.80');
    await cimiento.getByLabel('Caras del cimiento 1').selectOption('2');
    await cimiento.getByRole('button', { name: 'Guardar el cimiento 1' }).click();
    await expect(resumen).toContainText('corona 0.80 m (tecleada)');
    await expect(resumen).toContainText('altura 2.00 m'); // 0.80 − (−1.20)
    await cimiento.getByLabel('Dentellón del cimiento 1').check();
    await cimiento.getByRole('button', { name: 'Guardar el cimiento 1' }).click();
    await expect.poll(async () => (await cimientos())[0]?.dentellon).toBe(true);
    expect((await cimientos())[0]).toMatchObject({ caras: 2, cota_corona_m: 0.8, punto_nivel_id: punto });

    // Asignarlo a un espacio: su concepto se resuelve en ese espacio.
    const espacio = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/espacios`, { nombre: 'Cimiento norte', tipo: 'otro' });
    await page.reload();
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaDeNuevo = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaDeNuevo.getByRole('button', { name: `Cimientos de ${nombre}` }).click();
    const panel2 = zonaDeNuevo.getByTestId('cimientos-de-la-zona');
    await panel2.getByLabel('Espacio del cimiento 1').selectOption(espacio.id);
    await expect.poll(async () => (await cimientos())[0]?.espacio_id).toBe(espacio.id);
    const filas = panel2.getByRole('table', { name: 'Lo que paga el cimiento de cada espacio' }).locator('tr[data-espacio="Cimiento norte"][data-concepto="MCT-01011"]');
    await expect(filas).toHaveCount(1);
    await expect(filas).not.toHaveAttribute('data-estado-de-partida', 'sin_espacio');

    // El cimiento y la losa no cuentan lo mismo: la matriz de la losa no se enteró.
    const matriz = await llamarApi<{ conceptos: { concepto: { clave: string } }[] }>(request, 'control', 'GET', `/zonas-de-losa/${zona.id}/matriz`);
    expect(matriz.conceptos.map((c) => c.concepto.clave)).not.toContain('MCT-01011');

    await panel2.getByRole('button', { name: 'Quitar el cimiento 1' }).click();
    await expect(panel2.locator('[data-cimiento-de-la-zona]')).toHaveCount(0);
    await expect.poll(async () => (await cimientos()).length).toBe(0);
  });

  test('Costos lee los cimientos sin editarlos y una corona por debajo del desplante dice por qué', async ({ page, request }) => {
    const { obra, actividad, plano, zona, nombre, linea } = await prepararCimentacion(request, 'CE');
    const c = await llamarApi<{ id: string }>(request, 'control', 'POST', `/zonas-de-losa/${zona.id}/cimientos`, { trazo_id: linea, cota_desplante_m: -0.8 });

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'costos');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaEl = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaEl.getByRole('button', { name: `Cimientos de ${nombre}` }).click();
    const panel = zonaEl.getByTestId('cimientos-de-la-zona');
    await expect(panel.locator('[data-cimiento-de-la-zona]')).toHaveCount(1);
    await expect(panel.getByLabel('Cota de desplante del cimiento 1')).toBeDisabled();
    await expect(panel.getByLabel('Espacio del cimiento 1')).toBeDisabled();
    await expect(panel.getByRole('button', { name: /^Quitar el cimiento/ })).toHaveCount(0);

    // Control de obra baja la corona por debajo del desplante (por la API): el cimiento no se calcula y lo dice.
    await llamarApi(request, 'control', 'PUT', `/cimientos-de-zona/${c.id}`, { trazo_id: linea, cota_desplante_m: -0.8, cota_corona_m: -1.5 });
    await page.reload();
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaDeNuevo = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaDeNuevo.getByRole('button', { name: `Cimientos de ${nombre}` }).click();
    await expect(zonaDeNuevo.locator('[data-cimiento-de-la-zona]')).toHaveAttribute('data-con-error', 'si');
    await expect(zonaDeNuevo.getByTestId('cimiento-error')).toContainText('por encima del desplante');
  });
});
