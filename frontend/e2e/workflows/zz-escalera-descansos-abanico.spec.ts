import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, solicitarApi, test } from '../infraestructura';

/**
 * La escalera con descansos propios y escalones de abanico (Fase 4d, migración 0148), en el panel de zonas del plano.
 *
 *  1. Control de obra, en una escalera de dos rampas, pone un descanso propio de 180° (el ancho transversal por omisión es el doble del de la escalera: 1.20 × 2.40 = 2.88 m²)
 *     y un grupo de 3 escalones de abanico. Los 18 peldaños del desnivel no cambian (3 de abanico + 15 rectos); las piezas de EST-01510 son 15 + 5.40 = 20.40 y no 23.40. El radio
 *     de la línea de huella nace en 0.35 m, se edita y la huella en la línea se recalcula. Quitar el abanico y el descanso devuelve la escalera de siempre.
 *  2. Lo que no vale se rechaza con su motivo y no se guarda (abanico que no cabe, descanso fuera de las rampas, polígono que ya es una losa).
 *  3. Costos lee descansos y abanicos sin poder cambiarlos.
 *
 * Cada prueba arma su propia obra (base limpia: nada depende de lo que dejó otra corrida) y es de un solo uso. El spec no crea castillos: el rango 16.0 de `altoPropio`
 * queda reservado para él por si lo hiciera (infraestructura.ts). Se repite ×10 en paralelo sin choques: nada compite por el mismo concepto ni por el mismo plano.
 */

const ROLES_E = ['control', 'costos'] as const;

async function prepararZona(request: Parameters<typeof llamarApi>[0], prefijo: string) {
  const sufijo = `${Date.now().toString(36)}${Math.floor(Math.random() * 1296).toString(36)}`.toUpperCase(); // único aun con varias repeticiones en el mismo milisegundo
  const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
  const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
  const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
    cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
    prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
    clave: `${prefijo}-${sufijo}`,
  });
  const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
  const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, { nombre: 'PB con abanico', archivo_url: 'planos/abanico.dwg' });
  const nombre = `Planta baja ${sufijo}`;
  const zona = await llamarApi<{ id: string }>(request, 'control', 'POST', `/planos/${plano.id}/zonas-de-losa`, { nombre, altura_libre_m: '3.00', espesor_m: '0.12' });
  const escalera = await llamarApi<{ id: string }>(request, 'control', 'POST', `/zonas-de-losa/${zona.id}/escaleras`, { rampas: 2 });
  return { obra, actividad: actividad!, plano, zona, escalera, nombre };
}

async function abrirPanel(page: Parameters<typeof entrarComo>[0], ids: { obra: { id: string }; actividad: { id: string }; plano: { id: string } }, nombre: string) {
  await page.setViewportSize({ width: 1280, height: 1400 });
  await page.goto(`/cuantificador?obra=${ids.obra.id}&plano=${ids.plano.id}&actividad=${ids.actividad.id}`);
  await page.getByRole('tab', { name: /Trazos/ }).click();
  const zonaEl = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
  await zonaEl.getByRole('button', { name: `Escaleras de ${nombre}` }).click();
  return zonaEl.getByTestId('escaleras-de-la-zona');
}

type Fila = { descansos: { posicion: number; giro_grados: number; largo_m: number | null; ancho_m: number | null; espesor_m: number | null }[]; abanicos: { posicion: number; escalones: number; radio_huella_m: number }[] };

test.describe('Cuantificador · escalera con descansos y escalones de abanico', () => {
  test.skip(!hayRoles(...ROLES_E), motivoSinRoles(...ROLES_E));
  test.setTimeout(240_000);

  test('Control de obra pone un descanso propio y un abanico: los peldaños no se duplican, las piezas suman y el radio se edita', async ({ page, request }) => {
    const z = await prepararZona(request, 'EA');
    const filas = async () => llamarApi<Fila[]>(request, 'control', 'GET', `/zonas-de-losa/${z.zona.id}/escaleras`);
    await entrarComo(page, 'control');
    const panel = await abrirPanel(page, z, z.nombre);
    const escalera = panel.locator('[data-escalera-de-la-zona]').first();
    const resumen = escalera.getByTestId('escalera-de-la-zona-resumen');
    await expect(resumen).toContainText('18 peldaños');
    await expect(resumen).toContainText('18.00 pza de EST-01510');
    await expect(resumen).toContainText('descanso 1.44 m²'); // el implícito de siempre: sin filas propias nada cambió

    // Un descanso propio de 180°: sin medidas toma 1.20 de largo por el doble del ancho (2.40) = 2.88 m².
    await escalera.getByRole('button', { name: 'Agregar un descanso a la escalera 1' }).click();
    await escalera.getByLabel('Giro del descanso 1 de la escalera 1').selectOption('180');
    await escalera.getByRole('button', { name: 'Guardar los descansos de la escalera 1' }).click();
    const detalle = escalera.getByRole('table', { name: 'Detalle de los descansos (escalera 1)' });
    await expect(detalle.locator('tr[data-posicion="1"]')).toHaveAttribute('data-origen', 'dimensiones');
    await expect(detalle).toContainText('2.88 m²');
    await expect(resumen).toContainText('descanso 2.88 m²');
    await expect(escalera.getByText(/EJ-820 · propuesto/)).toBeVisible();
    await expect.poll(async () => (await filas())[0]?.descansos[0]?.giro_grados).toBe(180);

    // Con espesor propio el concreto del descanso lo usa: 2.88 m² × 15 cm = 0.432 m³.
    await escalera.getByLabel('Espesor del descanso 1 de la escalera 1').fill('0.15');
    await escalera.getByRole('button', { name: 'Guardar los descansos de la escalera 1' }).click();
    await expect(detalle).toContainText('0.432 m³');

    // Tres escalones de abanico: siguen siendo 18 peldaños (3 + 15), no 21; las piezas de EST-01510 son 15 + 5.40 = 20.40.
    await escalera.getByRole('button', { name: 'Agregar un abanico a la escalera 1' }).click();
    await escalera.getByRole('button', { name: 'Guardar los abanicos de la escalera 1' }).click();
    const abanico = escalera.getByTestId('abanico-resumen-1');
    await expect(abanico).toContainText('3 de abanico + 15 rectos = 18 peldaños');
    await expect(abanico).toContainText('5.40 pza de EST-01510');
    await expect(resumen).toContainText('18 peldaños');
    await expect(resumen).toContainText('3 de abanico y 15 rectos');
    await expect(resumen).toContainText('20.40 pza de EST-01510');
    const tabla = escalera.getByRole('table', { name: 'Detalle de los abanicos (escalera 1)' });
    await expect(tabla).toContainText('32.5 cm (a 35 cm del borde interior)'); // radio por omisión 0.35 m
    await expect(tabla).toContainText('85.9°');
    await expect(panel.getByTestId('escaleras-resumen')).toContainText('3 de abanico');
    await expect.poll(async () => (await filas())[0]?.abanicos[0]?.radio_huella_m).toBe(0.35);

    // El radio de la línea de huella es un supuesto editable: a 40 cm del borde interior el fondo es de 35 cm.
    await escalera.getByLabel('Radio de la línea de huella del abanico 1 de la escalera 1').fill('0.4');
    await escalera.getByRole('button', { name: 'Guardar los abanicos de la escalera 1' }).click();
    await expect(tabla).toContainText('35.0 cm (a 40 cm del borde interior)');

    // La conciliación incluye el concreto del abanico por escalón y las rampas siguen con sus 15 peldaños rectos.
    await expect(escalera.getByTestId('conciliacion-de-la-escalera')).toBeVisible();
    await expect(escalera.getByRole('table', { name: 'Detalle por rampa (escalera 1)' })).toContainText('8');

    // Quitar el abanico y el descanso devuelve la escalera de siempre.
    await escalera.getByRole('button', { name: 'Quitar el abanico 1 de la escalera 1' }).click();
    await escalera.getByRole('button', { name: 'Guardar los abanicos de la escalera 1' }).click();
    await expect(resumen).not.toContainText('de abanico');
    await expect(resumen).toContainText('18.00 pza de EST-01510');
    await escalera.getByRole('button', { name: 'Quitar el descanso 1 de la escalera 1' }).click();
    await escalera.getByRole('button', { name: 'Guardar los descansos de la escalera 1' }).click();
    await expect(resumen).toContainText('descanso 1.44 m²');
    await expect.poll(async () => (await filas())[0]?.descansos.length).toBe(0);
    await expect.poll(async () => (await filas())[0]?.abanicos.length).toBe(0);
  });

  test('lo que no vale se rechaza con su motivo y no se guarda', async ({ request }) => {
    const z = await prepararZona(request, 'EV');
    // Los escalones de abanico forman parte de los peldaños del desnivel: 12 de 18 dejan 6 rectos y 4 rampas piden 8.
    await llamarApi(request, 'control', 'PUT', `/escaleras-de-zona/${z.escalera.id}`, { rampas: 4 });
    const noCabe = await solicitarApi(request, 'control', 'PUT', `/escaleras-de-zona/${z.escalera.id}/abanicos`, {
      abanicos: [{ posicion: 1, escalones: 12, ancho_interior_m: 0.15, ancho_exterior_m: 0.75 }],
    });
    expect(noCabe.status()).toBe(422);
    expect(await noCabe.text()).toContain('no caben');
    // Un descanso que cae fuera de las rampas (posición 4 con 4 rampas: solo hay tres descansos).
    const fuera = await solicitarApi(request, 'control', 'PUT', `/escaleras-de-zona/${z.escalera.id}/descansos`, { descansos: [{ posicion: 4 }] });
    expect(fuera.status()).toBe(422);
    // Un polígono que ya es una losa no puede ser un descanso (contaría su área dos veces).
    const losa = await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${z.plano.id}/trazos`, {
      version_plano: 1, fuente: 'pdf', geometria_wkt: 'POLYGON((30 30, 34 30, 34 34, 30 34, 30 30))', enlaces: [],
    });
    await llamarApi(request, 'control', 'PUT', `/trazos/${losa.trazo_id}/losa`, { zona_id: z.zona.id });
    const esLosa = await solicitarApi(request, 'control', 'PUT', `/escaleras-de-zona/${z.escalera.id}/descansos`, { descansos: [{ posicion: 1, trazo_id: losa.trazo_id }] });
    expect(esLosa.status()).toBe(422);
    expect(await esLosa.text()).toContain('ya es una losa');
    const filas = await llamarApi<Fila[]>(request, 'control', 'GET', `/zonas-de-losa/${z.zona.id}/escaleras`);
    expect(filas[0]!.descansos).toHaveLength(0);
    expect(filas[0]!.abanicos).toHaveLength(0);
  });

  test('Costos lee los descansos y los abanicos sin poder cambiarlos', async ({ page, request }) => {
    const z = await prepararZona(request, 'EL');
    await llamarApi(request, 'control', 'PUT', `/escaleras-de-zona/${z.escalera.id}/descansos`, { descansos: [{ posicion: 1, giro_grados: 90 }] });
    await llamarApi(request, 'control', 'PUT', `/escaleras-de-zona/${z.escalera.id}/abanicos`, {
      abanicos: [{ posicion: 0, escalones: 3, ancho_interior_m: 0.15, ancho_exterior_m: 0.75 }],
    });
    await entrarComo(page, 'costos');
    const panel = await abrirPanel(page, z, z.nombre);
    const escalera = panel.locator('[data-escalera-de-la-zona]').first();
    await expect(escalera.getByTestId('abanico-resumen-1')).toContainText('3 de abanico + 15 rectos = 18 peldaños');
    await expect(escalera.getByLabel('Giro del descanso 1 de la escalera 1')).toBeDisabled();
    await expect(escalera.getByLabel('Escalones del abanico 1 de la escalera 1')).toBeDisabled();
    await expect(escalera.getByRole('button', { name: /^Guardar los descansos/ })).toHaveCount(0);
    await expect(escalera.getByRole('button', { name: /^Guardar los abanicos/ })).toHaveCount(0);
    await expect(escalera.getByRole('button', { name: /^Quitar el abanico/ })).toHaveCount(0);
    const rechazo = await solicitarApi(request, 'costos', 'PUT', `/escaleras-de-zona/${z.escalera.id}/abanicos`, { abanicos: [] });
    expect(rechazo.status()).toBe(403);
  });
});
