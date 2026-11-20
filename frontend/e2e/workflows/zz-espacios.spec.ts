import { cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, pulsarMarca, solicitarApi, test } from '../infraestructura';

/**
 * La capa «espacio» (0143): el cuarto o área donde se asignan zonas de losa, muros y elementos.
 *
 *  1. Control de obra crea los espacios de la obra (Recámara 1 y Baño) desde el panel, asigna un polígono de losa a la recámara y un elemento de la
 *     matriz al baño; la matriz de la zona se reparte por espacio (la suma es el total de la zona) y dice por qué cada concepto aún no cuenta.
 *  2. Un muro se asigna a un espacio y se COMPARTE entre dos con su reparto (mitad y mitad por omisión, o un %): el muro se traza una vez y el
 *     servidor reparte su cantidad sin contarla dos veces. Quitarle el espacio lo devuelve a como estaba.
 *  3. Costos lee los espacios y las asignaciones sin poder cambiarlos.
 *
 * El spec no crea castillos ni conceptos: el rango 11.0 de `altoPropio` queda reservado para él por si lo hiciera (infraestructura.ts).
 * Las cantidades que llegan a las partidas del árbol las cubre `test_espacios_endtoend.py` (con árbol, partidas y actividades armadas en la base).
 */

const ROLES_E = ['control', 'costos'] as const;
const CUARTO_A = 'POLYGON((0 -4, 6 -4, 6 0, 0 0, 0 -4))'; // 24 m² con la escala sin calibrar (1 unidad = 1 m)
const CUARTO_B = 'POLYGON((6 -4, 9 -4, 9 0, 6 0, 6 -4))'; // 12 m²
const MURO = 'LINESTRING(0 -12, 8 -12)'; // un muro de 8 m, lejos de las losas para que ninguna marca lo tape

type Trazo = { id: string; geometry: { type: string }; properties: { espacio_id?: string | null; espacio_comparte_id?: string | null; espacio_reparto_pct?: string | null } };
type Asignacion = { espacio_id: string | null; espacio_comparte_id: string | null; reparto_pct: string | null; reparto: { espacio_id: string; fraccion: string }[] };

async function prepararObra(request: Parameters<typeof llamarApi>[0], prefijo: string) {
  const sufijo = `${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`.toUpperCase(); // único aun con varias repeticiones en el mismo milisegundo
  const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
  const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
  const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
    cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
    prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
    clave: `${prefijo}-${sufijo}`,
  });
  const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
  const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
    nombre: 'PB con espacios',
    archivo_url: 'planos/espacios.dwg',
  });
  const nombre = `Entrepiso ${sufijo}`;
  const zona = await llamarApi<{ id: string }>(request, 'control', 'POST', `/planos/${plano.id}/zonas-de-losa`, {
    nombre,
    altura_libre_m: '3.00',
    espesor_m: '0.12',
  });
  const losas: string[] = [];
  for (const wkt of [CUARTO_A, CUARTO_B]) {
    const t = await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1, fuente: 'pdf', geometria_wkt: wkt, enlaces: [],
    });
    await llamarApi(request, 'control', 'PUT', `/trazos/${t.trazo_id}/losa`, { zona_id: zona.id });
    losas.push(t.trazo_id);
  }
  const muro = await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
    version_plano: 1, fuente: 'pdf', geometria_wkt: MURO, grosor_m: '0.15', alineacion: 'centro', enlaces: [],
  });
  return { obra, actividad: actividad!, plano, zona, nombre, losas, muro: muro.trazo_id };
}

test.describe('Cuantificador · capa «espacio»', () => {
  test.skip(!hayRoles(...ROLES_E), motivoSinRoles(...ROLES_E));
  test.setTimeout(240_000);

  test('Control de obra: crea espacios, asigna una losa y un elemento, y la matriz se reparte por espacio; un muro se asigna y se comparte sin contarse dos veces', async ({ page, request }) => {
    const { obra, actividad, plano, zona, nombre, losas, muro } = await prepararObra(request, 'ES');
    const trazos = async () => (await llamarApi<{ features: Trazo[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)).features;
    const asignacion = async () => llamarApi<Asignacion>(request, 'control', 'GET', `/trazos/${muro}/espacio`);

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const panelEspacios = page.getByTestId('espacios-de-la-obra');
    await expect(panelEspacios).toContainText('Esta obra no tiene espacios.');

    // 1 · Los espacios de la obra, desde el panel.
    for (const [nombreDelEspacio, tipo] of [['Recámara 1', 'recamara'], ['Baño', 'bano']] as const) {
      await panelEspacios.getByLabel('Nombre del espacio', { exact: true }).fill(nombreDelEspacio);
      await panelEspacios.getByLabel('Tipo de espacio', { exact: true }).selectOption(tipo);
      await panelEspacios.getByRole('button', { name: 'Agregar espacio' }).click();
      await expect(panelEspacios.locator(`[data-espacio="${nombreDelEspacio}"]`)).toBeVisible();
    }
    await expect(panelEspacios.getByTestId('espacio')).toHaveCount(2);
    const espacios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/espacios`);
    const recamara = espacios.find((e) => e.nombre === 'Recámara 1')!;
    const bano = espacios.find((e) => e.nombre === 'Baño')!;

    // Un nombre repetido se rechaza con el aviso del servidor y no duplica el espacio.
    await panelEspacios.getByLabel('Nombre del espacio', { exact: true }).fill(' recámara 1 ');
    await panelEspacios.getByRole('button', { name: 'Agregar espacio' }).click();
    await expect(page.getByText(/Ya hay un espacio llamado/).first()).toBeVisible({ timeout: 15_000 });
    await expect(panelEspacios.getByTestId('espacio')).toHaveCount(2);

    // El polígono de 24 m² es la losa de la recámara: se elige en el plano y se asigna en su detalle.
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    await pulsarMarca(page, page.locator(`g.visor__trazo[data-trazo-id="${losas[0]}"]`), { fx: 0.3, fy: 0.5 });
    const detalleLosa = page.getByTestId('espacio-del-trazo');
    await expect(detalleLosa).toContainText('Espacio de la losa');
    await detalleLosa.getByLabel('Espacio del trazo').selectOption({ label: 'Recámara 1' });
    await expect(detalleLosa.getByTestId('reparto-del-trazo')).toContainText('Cuenta en: Recámara 1 100 %.');
    await expect(detalleLosa.getByLabel('Muro compartido con')).toHaveCount(0); // una losa no se comparte
    await expect(panelEspacios.locator('[data-espacio="Recámara 1"]')).toContainText('1 losa');
    await expect.poll(async () => (await trazos()).find((t) => t.id === losas[0])!.properties.espacio_id).toBe(recamara.id);

    // La matriz de la zona: un elemento nace en el baño y la matriz se reparte por espacio (la suma es la zona).
    const zonaEl = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaEl.getByRole('button', { name: `Matriz de conceptos de ${nombre}` }).click();
    const matriz = zonaEl.getByTestId('matriz-de-la-zona');
    await expect(matriz.getByTestId('matriz-resumen')).toContainText('Área 36.00 m²');
    await matriz.getByLabel('Elemento por agregar', { exact: true }).selectOption('T-1-15x25');
    await matriz.getByLabel('Cantidad del elemento', { exact: true }).fill('10');
    await matriz.getByLabel('Espacio del elemento por agregar', { exact: true }).selectOption({ label: 'Baño' });
    await matriz.getByRole('button', { name: 'Agregar elemento' }).click();
    await expect(matriz.getByTestId('elemento-de-la-zona')).toHaveCount(1);
    await expect(matriz.getByLabel('Espacio de T-1-15x25')).toHaveValue(bano.id);
    await expect(panelEspacios.locator('[data-espacio="Baño"]')).toContainText('1 elemento');

    const porEspacio = matriz.getByTestId('matriz-por-espacio');
    await expect(porEspacio).toBeVisible({ timeout: 15_000 }); // la matriz se recalcula en el servidor tras agregar el elemento
    await expect(porEspacio.locator('tr[data-espacio="Baño"][data-concepto="AUX-00008"]')).toContainText('10.00 ml');
    // La losa (24 m²) de la recámara y la otra (12 m², sin espacio): el concepto de la losa va por espacio, nunca repetido.
    await expect(porEspacio.locator('tr[data-espacio="Recámara 1"]')).toContainText('24.00 m²');
    await expect(porEspacio.locator('tr[data-espacio="sin espacio"]')).toContainText('12.00 m²');
    // Lo que no está en el árbol o no tiene espacio no cuenta, y lo dice (sin inventar partidas ni conceptos).
    await expect(porEspacio.locator('tr[data-espacio="sin espacio"]').first().locator('.badge')).toContainText('sin espacio');
    const m = await llamarApi<{ area_m2: number; por_espacio: { espacio_id: string | null; area_m2: number; conceptos: { resolucion: { cuenta: boolean } }[] }[] }>(
      request, 'control', 'GET', `/zonas-de-losa/${zona.id}/matriz`,
    );
    expect(m.por_espacio.reduce((s, g) => s + g.area_m2, 0)).toBeCloseTo(m.area_m2, 6);
    expect(m.por_espacio.some((g) => g.conceptos.some((c) => c.resolucion.cuenta))).toBe(false); // el árbol del E2E no trae esas partidas

    // 2 · Un muro: se elige en el plano y se asigna a la recámara.
    await pulsarMarca(page, page.locator(`g.visor__trazo[data-trazo-id="${muro}"]`));
    const detalle = page.getByTestId('espacio-del-trazo');
    await expect(detalle).toContainText('Espacio del muro');
    await expect(detalle.getByTestId('reparto-del-trazo')).toContainText('Sin espacio: cuenta como siempre.');
    await detalle.getByLabel('Espacio del trazo').selectOption({ label: 'Recámara 1' });
    await expect(detalle.getByTestId('reparto-del-trazo')).toContainText('Cuenta en: Recámara 1 100 %.');

    // Se comparte con el baño: mitad y mitad (el muro cuenta una sola vez entre los dos).
    await detalle.getByLabel('Muro compartido con').selectOption({ label: 'Baño' });
    await expect(detalle.getByTestId('reparto-del-trazo')).toContainText('Cuenta en: Recámara 1 50 % · Baño 50 %.');
    await expect
      .poll(async () => {
        const a = await asignacion();
        return a.reparto.map((p) => `${p.espacio_id}:${Number(p.fraccion)}`).join('|');
      })
      .toBe(`${recamara.id}:0.5|${bano.id}:0.5`);

    // Con un reparto: 30 % de la recámara y 70 % del baño; un valor que no vale no se manda.
    await detalle.getByLabel('Reparto del espacio principal en por ciento').fill('100');
    await detalle.getByRole('button', { name: 'Guardar reparto' }).click();
    await expect(page.getByText(/va de más de 0 a menos de 100/).first()).toBeVisible();
    expect(Number((await asignacion()).reparto[0]!.fraccion)).toBe(0.5);
    await detalle.getByLabel('Reparto del espacio principal en por ciento').fill('30');
    await detalle.getByRole('button', { name: 'Guardar reparto' }).click();
    await expect(detalle.getByTestId('reparto-del-trazo')).toContainText('Cuenta en: Recámara 1 30 % · Baño 70 %.');
    const a = await asignacion();
    expect(a.reparto.map((p) => Number(p.fraccion))).toEqual([0.3, 0.7]);
    expect(a.reparto.reduce((s, p) => s + Number(p.fraccion), 0)).toBe(1); // el muro suma una sola vez
    await expect(panelEspacios.locator('[data-espacio="Recámara 1"]')).toContainText('1 muro');
    await expect(panelEspacios.locator('[data-espacio="Baño"]')).toContainText('1 muro');

    // Las propiedades del trazo en el plano traen la asignación.
    const propiedades = (await trazos()).find((t) => t.id === muro)!.properties;
    expect([propiedades.espacio_id, propiedades.espacio_comparte_id, Number(propiedades.espacio_reparto_pct)]).toEqual([recamara.id, bano.id, 30]);

    // Se deja de compartir y se le quita el espacio: el muro queda como estaba.
    await detalle.getByLabel('Muro compartido con').selectOption({ label: 'No se comparte' });
    await expect(detalle.getByTestId('reparto-del-trazo')).toContainText('Cuenta en: Recámara 1 100 %.');
    await detalle.getByLabel('Espacio del trazo').selectOption({ label: 'Sin espacio' });
    await expect(detalle.getByTestId('reparto-del-trazo')).toContainText('Sin espacio: cuenta como siempre.');
    expect((await asignacion()).reparto).toEqual([]);

    // Borrar un espacio suelta lo que tenía asignado.
    await panelEspacios.getByRole('button', { name: 'Borrar el espacio Recámara 1' }).click();
    await expect(panelEspacios.locator('[data-espacio="Recámara 1"]')).toHaveCount(0);
    await expect.poll(async () => (await trazos()).find((t) => t.id === losas[0])!.properties.espacio_id ?? null).toBeNull();
    // Y el lienzo sigue intacto: la caja del plano no cambió de lugar por los paneles.
    expect((await cajaEstable(page, page.getByRole('img', { name: 'Plano con sus trazos' })).then((c) => c.width)) > 0).toBe(true);
  });

  test('Costos lee los espacios y las asignaciones sin poder cambiarlos', async ({ page, request }) => {
    const { obra, actividad, plano, losas, muro } = await prepararObra(request, 'EC');
    const recamara = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/espacios`, { nombre: 'Recámara 1', tipo: 'recamara' });
    const bano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/espacios`, { nombre: 'Baño', tipo: 'bano' });
    await llamarApi(request, 'control', 'PUT', `/trazos/${muro}/espacio`, { espacio_id: recamara.id, espacio_comparte_id: bano.id });
    await llamarApi(request, 'control', 'PUT', `/trazos/${losas[0]}/espacio`, { espacio_id: recamara.id });

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'costos');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const panelEspacios = page.getByTestId('espacios-de-la-obra');
    await expect(panelEspacios.getByTestId('espacio')).toHaveCount(2);
    await expect(panelEspacios.locator('[data-espacio="Recámara 1"]')).toContainText('1 muro');
    await expect(panelEspacios).toContainText('Solo Control de obra los edita.');
    await expect(panelEspacios.getByRole('group', { name: 'Nuevo espacio' })).toHaveCount(0);
    await expect(panelEspacios.getByRole('button', { name: /^Borrar el espacio/ })).toHaveCount(0);

    await page.getByRole('toolbar', { name: 'Herramientas de trazo' }).getByRole('button', { name: 'Seleccionar', exact: true }).click();
    await pulsarMarca(page, page.locator(`g.visor__trazo[data-trazo-id="${muro}"]`));
    const detalle = page.getByTestId('espacio-del-trazo');
    await expect(detalle.getByTestId('reparto-del-trazo')).toContainText('Cuenta en: Recámara 1 50 % · Baño 50 %.');
    await expect(detalle.getByLabel('Espacio del trazo')).toBeDisabled();
    await expect(detalle.getByLabel('Muro compartido con')).toBeDisabled();
    await expect(detalle.getByRole('button', { name: 'Guardar reparto' })).toHaveCount(0);

    // Costos tampoco escribe por la API: solo Control de obra asigna y edita los espacios.
    const r = await solicitarApi(request, 'costos', 'PUT' as never, `/trazos/${muro}/espacio`, {});
    expect(r.status()).toBe(403);
  });
});
