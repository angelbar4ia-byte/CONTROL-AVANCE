import { cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, pulsarMarca, test } from '../infraestructura';

/**
 * Matriz de conceptos de la losa (fase 2 de las zonas de losa): a partir de una zona de losa se calculan el concreto, la cimbra y el acero de la
 * losa y de sus trabes, contratrabes y nervaduras, y los conceptos que paga cada parte.
 *
 *  1. Control de obra abre la matriz de una zona (dos polígonos de losa: 24 m² y una subzona de 8 m² de 20 cm), agrega una trabe a mano, la pasa
 *     a «paga su concepto por ml» (aparece su concepto de colado y cimbra por ml con clave provisional), cambia la losa a nervada, y mide una
 *     contratrabe con una LÍNEA dibujada en el plano (la longitud deriva de la línea y sigue a la escala del plano).
 *  2. Costos lee la matriz sin poder editarla, propone los conceptos que faltan y Control de obra los autoriza; el catálogo no cambia y no hay precios.
 *  3. En la biblioteca (Losas) la tarjeta de la losa calcula con las áreas y los elementos que se capturan, y la tarjeta de una trabe propone su
 *     colado y cimbra por ml con el destajo por ml sin importe (D8).
 *
 * Los conceptos nuevos tienen claves fijas (EJ-800, EJ-703…) y la base se comparte entre corridas y procesos: el spec no supone que estén sin
 * proponer; comprueba que cada uno quede propuesto o autorizado.
 */

const ROLES_M = ['control', 'costos'] as const;
const CUARTO = 'POLYGON((0 -4, 6 -4, 6 0, 0 0, 0 -4))'; // 24 m² con la escala sin calibrar (1 unidad = 1 m)
const SUBZONA = 'POLYGON((6 -4, 8 -4, 8 0, 6 0, 6 -4))'; // 8 m²

type Trazo = { id: string; geometry: { type: string; coordinates: number[][] }; properties: { grosor_m?: string | null } };

async function prepararZona(request: Parameters<typeof llamarApi>[0], prefijo: string) {
  const sufijo = Date.now().toString(36).toUpperCase();
  const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
  const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
  const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
    cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
    prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
    clave: `${prefijo}-${sufijo}`,
  });
  const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
  const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
    nombre: 'PB con losa',
    archivo_url: 'planos/matriz-de-losa.dwg',
  });
  const nombre = `Entrepiso ${sufijo}`;
  const zona = await llamarApi<{ id: string }>(request, 'control', 'POST', `/planos/${plano.id}/zonas-de-losa`, {
    nombre,
    altura_libre_m: '3.00',
    espesor_m: '0.12',
  });
  for (const [wkt, extra] of [[CUARTO, {}], [SUBZONA, { espesor_m: '0.20' }]] as const) {
    const t = await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1, fuente: 'pdf', geometria_wkt: wkt, enlaces: [],
    });
    await llamarApi(request, 'control', 'PUT', `/trazos/${t.trazo_id}/losa`, { zona_id: zona.id, ...extra });
  }
  return { obra, actividad: actividad!, plano, zona, nombre };
}

test.describe('Cuantificador · matriz de conceptos de la losa', () => {
  test.skip(!hayRoles(...ROLES_M), motivoSinRoles(...ROLES_M));
  test.setTimeout(240_000);

  test('Control de obra: elementos a mano, pago propio, losa nervada y una línea del plano que mide una contratrabe', async ({ page, request }) => {
    const { obra, actividad, plano, zona, nombre } = await prepararZona(request, 'ML');
    const trazos = async () => (await llamarApi<{ features: Trazo[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)).features;

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const panel = page.getByTestId('zonas-de-losa');
    const zonaEl = panel.getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaEl.getByRole('button', { name: `Matriz de conceptos de ${nombre}` }).click();
    const matriz = zonaEl.getByTestId('matriz-de-la-zona');

    // La matriz mide los dos polígonos de la zona: 24 m² y la subzona de 8 m² de 20 cm; sin escala calibrada, 1 unidad = 1 m.
    await expect(matriz.getByTestId('matriz-resumen')).toContainText('Área 32.00 m²');
    await expect(matriz.getByTestId('matriz-resumen')).toContainText('CON-00003'); // entrepiso
    await expect(matriz.getByTestId('matriz-resumen')).toContainText('cimbra 32.00 m²');
    await expect(matriz.getByText(/no tiene escala calibrada/)).toBeVisible();
    await expect(matriz.locator('[data-concepto="EJ-800"]')).toBeVisible(); // el concepto de la losa por m² (provisional)
    await expect(matriz.getByTestId('matriz-sin-mano-de-obra')).toContainText('Sin precios');

    // Una trabe a mano: su acero lo paga su auxiliar del catálogo y la losa sigue pagando su concreto y su cimbra.
    await matriz.getByLabel('Elemento por agregar').selectOption('T-1-15x25');
    await matriz.getByLabel('Cantidad del elemento').fill('10');
    await matriz.getByRole('button', { name: 'Agregar elemento' }).click();
    await expect(matriz.getByTestId('elemento-de-la-zona')).toHaveCount(1);
    await expect(matriz.getByTestId('elemento-de-la-zona')).toContainText('10.00 ml');
    await expect(matriz.locator('[data-concepto="AUX-00008"][data-parte="acero"]')).toContainText('10.00 ml');
    await expect(matriz.locator('[data-parte="colado"]')).toHaveCount(0);

    // Con pago propio, su colado y cimbra los paga su concepto por ml (clave provisional, sin precio): propuesto o autorizado, nunca «sin concepto».
    await matriz.getByLabel('Pago de T-1-15x25').selectOption('propio');
    const colado = matriz.locator('[data-concepto="EJ-703"][data-parte="colado"]');
    await expect(colado).toContainText('10.00 ml');
    await expect(colado).toContainText(/clave provisional|propuesto|autorizado/);
    await expect(matriz.getByRole('table', { name: 'Conceptos de la matriz de la zona' }).locator('tr[data-concepto]')).toHaveCount(3);

    // La losa nervada: solo la capa de compresión de 5 cm; el concepto por m² es el de la nervada.
    await matriz.getByLabel('Tipo de losa de la zona').selectOption('nervada');
    await expect(matriz.getByTestId('matriz-resumen')).toContainText('concreto de la losa 1.680 m³');
    await expect(matriz.locator('[data-concepto="EJ-801"]')).toBeVisible();
    await expect(matriz.locator('[data-concepto="EJ-800"]')).toHaveCount(0);
    await expect(zonaEl).toContainText('Losa nervada · entrepiso');

    // Una LÍNEA dibujada en el plano mide una contratrabe: su longitud deriva de la línea, no se teclea.
    const c = await cajaEstable(page, lienzo);
    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    await page.mouse.click(c.x + c.width * 0.1, c.y + c.height * 0.72);
    await page.mouse.click(c.x + c.width * 0.3, c.y + c.height * 0.94);
    await expect.poll(async () => (await trazos()).filter((t) => t.geometry.type === 'LineString').length).toBe(1);
    const linea = (await trazos()).find((t) => t.geometry.type === 'LineString')!;
    const [[x1, y1], [x2, y2]] = linea.geometry.coordinates as [[number, number], [number, number]];
    const largoEnElPlano = Math.hypot(x2 - x1, y2 - y1);
    await page.keyboard.press('Escape');
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    await pulsarMarca(page, page.locator(`g.visor__trazo[data-trazo-id="${linea.id}"]`));
    const detalle = page.getByTestId('elemento-de-losa-de-la-linea');
    await expect(detalle).toBeVisible();
    await detalle.getByLabel('Elemento de losa de la línea').selectOption('CT1-15x25');
    await detalle.getByLabel('Pago del elemento de la línea').selectOption('propio');
    await detalle.getByRole('button', { name: 'Medir con esta línea' }).click();
    await expect(matriz.getByTestId('elemento-de-la-zona')).toHaveCount(2);
    const contratrabe = matriz.locator('[data-elemento="CT1-15x25"]');
    await expect(contratrabe).toContainText('de la línea del plano');
    await expect
      .poll(async () => {
        const lista = await llamarApi<{ elemento_clave: string; origen: string; cantidad: number; trazo_id: string | null }[]>(request, 'control', 'GET', `/zonas-de-losa/${zona.id}/elementos`);
        const e = lista.find((x) => x.elemento_clave === 'CT1-15x25');
        return e !== undefined && e.origen === 'trazo' && e.trazo_id === linea.id && Math.abs(e.cantidad - largoEnElPlano) < 0.01;
      })
      .toBe(true);

    // Al calibrar la escala (2 m por unidad de plano) el área escala con el cuadrado y la línea mide el doble, sin tocar el elemento.
    await llamarApi(request, 'control', 'PUT', `/planos/${plano.id}/escala`, { punto_a: [0, 0], punto_b: [4, 0], distancia_m: '8' });
    await page.reload();
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaDeNuevo = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaDeNuevo.getByRole('button', { name: `Matriz de conceptos de ${nombre}` }).click();
    const matriz2 = zonaDeNuevo.getByTestId('matriz-de-la-zona');
    await expect(matriz2.getByTestId('matriz-resumen')).toContainText('Área 128.00 m²');
    await expect(matriz2.getByText(/no tiene escala calibrada/)).toHaveCount(0);
    const lista = await llamarApi<{ elemento_clave: string; cantidad: number }[]>(request, 'control', 'GET', `/zonas-de-losa/${zona.id}/elementos`);
    expect(lista.find((e) => e.elemento_clave === 'CT1-15x25')!.cantidad).toBeCloseTo(largoEnElPlano * 2, 1);

    // Quitar un elemento lo saca de la matriz.
    await matriz2.getByRole('button', { name: 'Quitar T-1-15x25 de la matriz' }).click();
    await expect(matriz2.getByTestId('elemento-de-la-zona')).toHaveCount(1);
  });

  test('Costos lee la matriz sin editarla y propone los conceptos; Control de obra los autoriza y el catálogo no cambia', async ({ page, request }) => {
    const { obra, actividad, plano, zona, nombre } = await prepararZona(request, 'MR');
    // La trabe T-22p-12x20 es de este spec: su concepto de colado por ml (EJ-769) lo proponen aquí.
    await llamarApi(request, 'control', 'POST', `/zonas-de-losa/${zona.id}/elementos`, { elemento_clave: 'T-22p-12x20', cantidad: 12, pago: 'propio' });

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'costos');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaEl = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaEl.getByRole('button', { name: `Matriz de conceptos de ${nombre}` }).click();
    const matriz = zonaEl.getByTestId('matriz-de-la-zona');
    await expect(matriz.getByTestId('matriz-resumen')).toContainText('Área 32.00 m²');

    // Costos lee: no agrega, no quita y no cambia el pago ni el tipo.
    await expect(matriz.getByRole('group', { name: 'Agregar un elemento a la zona' })).toHaveCount(0);
    await expect(matriz.getByRole('button', { name: /^Quitar / })).toHaveCount(0);
    await expect(matriz.getByLabel('Pago de T-22p-12x20')).toBeDisabled();
    await expect(matriz.getByLabel('Tipo de losa de la zona')).toBeDisabled();
    await expect(zonaEl.getByRole('button', { name: 'Editar' })).toHaveCount(0);

    // Propone lo que falta (si otra corrida ya lo propuso, no hay nada que proponer: el botón no aparece).
    const proponer = matriz.getByRole('button', { name: /^Proponer los conceptos que faltan/ });
    if (await proponer.isVisible()) {
      await proponer.click();
    }
    const provisionales = matriz.locator('tr[data-concepto^="EJ-"]');
    await expect(provisionales).toHaveCount(2); // el concepto de la losa (EJ-800) y el colado por ml de la trabe (EJ-769)
    await expect.poll(async () => (await provisionales.evaluateAll((filas) => filas.map((f) => f.getAttribute('data-estado')))).every((e) => e === 'pendiente' || e === 'autorizada')).toBe(true);

    // Control de obra autoriza lo que quede pendiente (por la API, con su token); Costos no puede (la tarjeta no le ofrece «Autorizar»).
    const pendientes = await llamarApi<{ id: string; concepto_clave: string }[]>(request, 'control', 'GET', '/propuestas-de-estructura/pendientes');
    for (const p of pendientes.filter((x) => ['EJ-800', 'EJ-769'].includes(x.concepto_clave))) {
      await llamarApi(request, 'control', 'POST', `/propuestas-de-estructura/${p.id}/autorizar`);
    }
    await page.reload();
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaDeNuevo = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaDeNuevo.getByRole('button', { name: `Matriz de conceptos de ${nombre}` }).click();
    await expect(zonaDeNuevo.locator('tr[data-concepto="EJ-769"]')).toHaveAttribute('data-estado', 'autorizada');
    await expect(zonaDeNuevo.locator('tr[data-concepto="EJ-800"]')).toHaveAttribute('data-estado', 'autorizada');
    await expect(zonaDeNuevo.locator('tr[data-concepto="EJ-769"]')).toContainText('autorizado · versión');
  });

  test('la biblioteca: la tarjeta de la losa y el colado y cimbra por ml de una trabe, con su destajo sin importe', async ({ page, request }) => {
    const { obra, plano } = await prepararZona(request, 'MB');
    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tablist', { name: 'Panel lateral' }).getByRole('tab', { name: /^Elementos/ }).click();
    const area = page.getByRole('region', { name: 'Elementos', exact: true });
    const biblioteca = page.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    await expect(biblioteca.getByRole('button', { name: /^Losas \d+$/ })).toBeVisible();
    await expect(biblioteca.getByRole('button', { name: /Losas macizas/ })).toBeVisible();
    await expect(biblioteca.getByRole('button', { name: /Losas nervadas/ })).toBeVisible();

    // La losa maciza: 100 m² de 12 cm con una trabe que paga su concepto por ml.
    await biblioteca.getByRole('button', { name: /^LOSA-MACIZA\b/ }).click();
    const losa = area.getByRole('article', { name: /LOSA-MACIZA/ });
    await expect(losa.getByTestId('losa-area')).toContainText('Área 100.00 m²');
    await expect(losa.getByTestId('losa-concreto')).toContainText('12.600 m³');
    await expect(losa.getByTestId('losa-parrilla')).toContainText('AUX-06010');
    await losa.getByRole('button', { name: 'Agregar un elemento' }).click();
    await losa.getByLabel('Elemento 1', { exact: true }).selectOption('T-3-15x25');
    await losa.getByLabel('Cantidad del elemento 1').fill('20');
    await expect(losa.getByRole('region', { name: 'Conceptos de la matriz' }).locator('[data-concepto="AUX-00001"]')).toContainText('20.00 ml');
    await losa.getByLabel('Pago del elemento 1').selectOption('propio');
    await expect(losa.getByRole('region', { name: 'Conceptos de la matriz' }).locator('[data-concepto="EJ-701"]')).toContainText('propuesto · clave provisional');
    await expect(losa.getByTestId('losa-sin-mano-de-obra')).toContainText('Sin precios');
    await expect(losa.getByRole('region', { name: 'Pendientes por confirmar' })).toContainText('Q49');

    // Control de obra propone el concepto de la losa (si ya lo propuso otra corrida, el botón no aparece) y queda autorizado.
    const bloque = losa.getByRole('region', { name: 'Concepto nuevo de la losa' });
    const proponerLosa = bloque.getByRole('button', { name: 'Proponer el concepto de la losa' });
    if (await proponerLosa.isVisible()) await proponerLosa.click();
    await expect(bloque.locator('[data-concepto-propuesto="EJ-800"]')).toHaveAttribute('data-estado-propuesta', /pendiente|autorizada/);

    // La trabe: el colado y cimbra por ml con su clave provisional y el destajo por ml sin importe; nada de precios.
    await biblioteca.getByRole('button', { name: /^T-3-15x25\b/ }).click();
    const trabe = area.getByRole('article', { name: /T-3-15x25/ });
    const camino = trabe.getByRole('region', { name: 'Colado, cimbra y destajo' });
    await expect(camino).toHaveAttribute('data-camino', 'por_registrar');
    await expect(camino.getByTestId('ee-destajo-por-ml')).toContainText('EJ-701-MO');
    await expect(camino.getByTestId('ee-destajo-por-ml')).toContainText('sin importe');
    const proponerColado = camino.getByRole('button', { name: 'Proponer el colado y cimbra por ml' });
    if (await proponerColado.isVisible()) await proponerColado.click();
    await expect(camino.locator('[data-concepto-propuesto="EJ-701"]')).toHaveAttribute('data-estado-propuesta', /pendiente|autorizada/);
    expect(await camino.innerText()).not.toMatch(/\$/);
  });
});
