import { cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, pulsarMarca, test } from '../infraestructura';

/**
 * El relleno DINÁMICO de azotea (0147): arenilla de espesor variable según las bajadas pluviales y plantilla de mortero de 5 cm.
 *
 *  1. Control de obra, sobre el plano: agrega el relleno de azotea a una zona de 32 m² (escala calibrada), coloca DOS bajadas con la herramienta Punto, ve que el
 *     relleno pasa a dos capas (arenilla por m³ con el concepto propuesto EJ-830 y mortero por m² con ALB-03014), que el visor muestra las bajadas, las líneas de pendiente
 *     generadas y los hilos de nivel PUNTEADOS, traza una línea de pendiente con la herramienta Línea (que reemplaza a la generada), la quita y quita una bajada.
 *  2. Lo que cada bajada drena suma el área (nada se cuenta dos veces) y la pendiente de la zona cambia el volumen.
 *  3. Sin escala calibrada no hay cantidades ni guías; al calibrar aparecen.
 *  4. Costos lee sin editar y propone la arenilla (EJ-830, clave provisional, sin precio); Control de obra la autoriza y el catálogo no cambia. El compactado mide
 *     su volumen por el factor de abundamiento.
 *
 * Los conceptos EJ-830 y EJ-810 tienen clave fija y la base se comparte entre corridas y procesos: el spec no supone que estén sin proponer. El spec no crea castillos:
 * el rango 15.0 de `altoPropio` queda reservado para él por si lo hiciera (infraestructura.ts).
 */

const ROLES_D = ['control', 'costos'] as const;
const CUARTO = 'POLYGON((0 -4, 6 -4, 6 0, 0 0, 0 -4))'; // 24 m² con 1 unidad = 1 m
const SUBZONA = 'POLYGON((6 -4, 8 -4, 8 0, 6 0, 6 -4))'; // 8 m²

type Llamada = Parameters<typeof llamarApi>[0];
type Bajada = { id: string; trazo_id: string; linea_trazo_id: string | null; rotulo: string | null };
type Calculado = {
  escala_definida: boolean;
  rellenos: {
    id: string;
    modo: string;
    area_m2: number;
    volumen_m3: number;
    bajadas: Bajada[];
    conceptos: { concepto: { clave: string }; cantidad: number; unidad: string; propuesta: { estado: string } | null }[];
    dinamico: { estado: string; bajadas: { id: string; area_m2: number | null }[]; error_relativo: number | null; guias: { tipo: string; origen: string }[] } | null;
  }[];
};

async function prepararZona(request: Llamada, prefijo: string, { calibrar = true }: { calibrar?: boolean } = {}) {
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
    nombre: 'Azotea con bajadas',
    archivo_url: 'planos/azotea-dinamica.dwg',
  });
  const nombre = `Azotea ${sufijo}`;
  const zona = await llamarApi<{ id: string }>(request, 'control', 'POST', `/planos/${plano.id}/zonas-de-losa`, {
    nombre,
    altura_libre_m: '3.00',
    espesor_m: '0.12',
    uso_de_losa: 'azotea',
  });
  const poligonos: string[] = [];
  for (const wkt of [CUARTO, SUBZONA]) {
    const t = await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1, fuente: 'pdf', geometria_wkt: wkt, enlaces: [],
    });
    await llamarApi(request, 'control', 'PUT', `/trazos/${t.trazo_id}/losa`, { zona_id: zona.id });
    poligonos.push(t.trazo_id);
  }
  if (calibrar) await llamarApi(request, 'control', 'PUT', `/planos/${plano.id}/escala`, { punto_a: [0, 0], punto_b: [4, 0], distancia_m: '4' });
  const relleno = await llamarApi<{ id: string }>(request, 'control', 'POST', `/zonas-de-losa/${zona.id}/rellenos`, {
    elemento_clave: 'REL-AZOTEA',
    compensar_espesores: false,
  });
  return { obra, actividad: actividad!, plano, zona, nombre, relleno, poligonos };
}

const calculo = (request: Llamada, rol: 'control' | 'costos', zonaId: string) =>
  llamarApi<Calculado>(request, rol, 'GET', `/zonas-de-losa/${zonaId}/rellenos/calculo`);

async function ponerBajada(request: Llamada, planoId: string, rellenoId: string, wkt: string): Promise<Bajada> {
  const t = await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${planoId}/trazos`, {
    version_plano: 1, fuente: 'pdf', geometria_wkt: wkt, enlaces: [],
  });
  return llamarApi<Bajada>(request, 'control', 'POST', `/rellenos-de-zona/${rellenoId}/bajadas`, { trazo_id: t.trazo_id });
}

test.describe('Cuantificador · relleno dinámico de azotea', () => {
  test.skip(!hayRoles(...ROLES_D), motivoSinRoles(...ROLES_D));
  test.setTimeout(240_000);

  test('Control de obra: coloca dos bajadas en el plano, ve arenilla y mortero, las guías punteadas, traza una línea de pendiente y quita una bajada', async ({ page, request }) => {
    const { obra, actividad, plano, zona, nombre, relleno, poligonos } = await prepararZona(request, 'RD');

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaEl = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaEl.getByRole('button', { name: `Rellenos de ${nombre}` }).click();
    const panel = zonaEl.getByTestId('rellenos-de-la-zona');
    const fila = panel.locator('[data-relleno-de-la-zona="REL-AZOTEA"]');
    await expect(fila).toHaveAttribute('data-modo', 'uniforme');
    await expect(panel.getByText(/Sin bajadas: el relleno es parejo/)).toBeVisible();

    // El plano ya enmarcó la zona: se elige el polígono (Seleccionar) y se espera a que su marca no se mueva antes de dibujar sobre el lienzo.
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    await pulsarMarca(page, page.locator(`[data-trazo-id="${poligonos[0]}"]`));
    await expect(page.getByText('Trazo elegido')).toBeVisible();

    // Dos bajadas con la herramienta Punto (el relleno la activa): cada clic en el plano es una bajada pluvial.
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await panel.getByRole('button', { name: 'Colocar bajada pluvial del relleno 1' }).click();
    for (const [n, fx] of [[1, 0.25], [2, 0.75]] as const) {
      const c = await cajaEstable(page, lienzo);
      await page.mouse.click(c.x + c.width * fx, c.y + c.height * 0.5);
      await expect.poll(async () => (await calculo(request, 'control', zona.id)).rellenos[0]!.bajadas.length).toBe(n);
    }
    await page.keyboard.press('Escape');

    // El relleno pasó a dos capas: arenilla de espesor variable (EJ-830, m³) y mortero de 5 cm (ALB-03014, m²), con su método y error.
    const c1 = await calculo(request, 'control', zona.id);
    const r1 = c1.rellenos[0]!;
    expect(r1.modo).toBe('bajadas');
    expect(r1.area_m2).toBeCloseTo(32, 5);
    expect(r1.volumen_m3).toBeGreaterThan(32 * 0.05); // más que 5 cm parejos: la pendiente sube el espesor lejos de la bajada
    expect(r1.volumen_m3).toBeLessThan(32 * 0.2);
    const porClave = Object.fromEntries(r1.conceptos.map((k) => [k.concepto.clave, k]));
    expect(porClave['ALB-03014']!.cantidad).toBeCloseTo(32, 5);
    expect(porClave['EJ-830']!.cantidad).toBeCloseTo(r1.volumen_m3, 6);
    expect(porClave['EJ-830']!.unidad).toBe('m³');
    // Lo que drena cada bajada suma el área: nada se cuenta dos veces.
    expect(r1.dinamico!.bajadas.reduce((t, b) => t + (b.area_m2 ?? 0), 0)).toBeCloseTo(32, 4);
    expect(r1.dinamico!.error_relativo!).toBeLessThan(0.001);
    await expect(fila).toHaveAttribute('data-modo', 'bajadas');
    await expect(fila.getByTestId('relleno-de-la-zona-resumen')).toContainText(`${r1.volumen_m3.toFixed(3)} m³ de EJ-830`);
    await expect(fila.getByTestId('relleno-de-la-zona-resumen')).toContainText('32.00 m² de ALB-03014');
    await expect(fila.getByTestId('relleno-dinamico')).toContainText('mortero de 5.0 cm = 1.600 m³');
    await expect(fila.getByTestId('relleno-dinamico-metodo')).toContainText('Integral numérica determinista');
    await expect(fila.getByTestId('bajada-del-relleno')).toHaveCount(2);
    await expect(fila.getByText(/EJ-830 · propuesto/)).toBeVisible();

    // El visor muestra las bajadas, una línea de pendiente generada por bajada y los hilos de nivel PUNTEADOS.
    await expect(page.getByTestId('bajada-de-relleno')).toHaveCount(2);
    await expect(page.getByTestId('linea-de-pendiente')).toHaveCount(2);
    await expect(page.getByTestId('linea-de-pendiente').first()).toHaveAttribute('data-origen', 'generada');
    const hilos = page.getByTestId('hilo-de-nivel');
    await expect.poll(async () => hilos.count()).toBeGreaterThan(2);
    expect(await hilos.first().locator('polyline').evaluate((e) => getComputedStyle(e).strokeDasharray)).not.toBe('none');

    // La pendiente de la zona cambia el volumen (sin pendiente, 5 cm parejos: 1.600 m³).
    await fila.getByLabel('Pendiente de la zona del relleno 1').fill('0');
    await fila.getByRole('button', { name: 'Guardar los parámetros del relleno 1' }).click();
    await expect(fila.getByTestId('relleno-de-la-zona-resumen')).toContainText('1.600 m³ de EJ-830');
    await expect(page.getByTestId('hilo-de-nivel')).toHaveCount(0); // sin pendiente no hay niveles que marcar
    await fila.getByLabel('Pendiente de la zona del relleno 1').fill('2');
    await fila.getByRole('button', { name: 'Guardar los parámetros del relleno 1' }).click();
    await expect(fila.getByTestId('relleno-de-la-zona-resumen')).toContainText(`${r1.volumen_m3.toFixed(3)} m³ de EJ-830`);

    // Una línea de pendiente trazada con la herramienta Línea (dos clics) reemplaza a la generada de esa bajada.
    await fila.getByRole('button', { name: 'Trazar la línea de pendiente de la bajada 1 del relleno 1' }).click();
    // Las opciones de la herramienta Línea se abren sobre el plano: se pliegan para que los clics caigan en el lienzo.
    const cabeza = page.locator('.opciones__cabeza[aria-expanded="true"]');
    if ((await cabeza.count()) > 0) await cabeza.first().click();
    const trazo = await cajaEstable(page, lienzo);
    await page.mouse.click(trazo.x + trazo.width * 0.75, trazo.y + trazo.height * 0.4);
    await page.mouse.click(trazo.x + trazo.width * 0.25, trazo.y + trazo.height * 0.5);
    await expect.poll(async () => (await calculo(request, 'control', zona.id)).rellenos[0]!.bajadas[0]!.linea_trazo_id).not.toBeNull();
    await expect(fila.getByTestId('bajada-del-relleno').first()).toHaveAttribute('data-linea', 'trazada');
    await expect(page.getByTestId('linea-de-pendiente').filter({ has: page.locator('.is-trazada') })).toHaveCount(1);
    // Quitar la línea devuelve la dirección generada.
    await fila.getByRole('button', { name: 'Quitar la línea de la bajada 1 del relleno 1' }).click();
    await expect.poll(async () => (await calculo(request, 'control', zona.id)).rellenos[0]!.bajadas[0]!.linea_trazo_id).toBeNull();
    await expect(page.getByTestId('linea-de-pendiente').filter({ has: page.locator('.is-trazada') })).toHaveCount(0);

    // Quitar una bajada deja la otra drenando todo; quitar la última devuelve el relleno parejo de siempre.
    await fila.getByRole('button', { name: 'Quitar la bajada 2 del relleno 1' }).click();
    await expect.poll(async () => (await calculo(request, 'control', zona.id)).rellenos[0]!.bajadas.length).toBe(1);
    await expect(page.getByTestId('bajada-de-relleno')).toHaveCount(1);
    const unica = (await calculo(request, 'control', zona.id)).rellenos[0]!;
    expect(unica.dinamico!.bajadas[0]!.area_m2).toBeCloseTo(32, 4);
    expect(unica.volumen_m3).toBeGreaterThan(r1.volumen_m3); // una sola bajada: más recorrido, más espesor
    await fila.getByRole('button', { name: 'Quitar la bajada 1 del relleno 1' }).click();
    await expect(fila).toHaveAttribute('data-modo', 'uniforme');
    await expect(page.getByTestId('guias-de-relleno')).toHaveCount(0);
    expect((await calculo(request, 'control', zona.id)).rellenos[0]!.volumen_m3).toBeCloseTo(32 * 0.09, 5);
    expect(relleno.id).toBeTruthy();
  });

  test('sin escala calibrada el relleno con bajadas no da cantidades ni guías; al calibrar aparecen', async ({ page, request }) => {
    const { obra, actividad, plano, zona, nombre, relleno } = await prepararZona(request, 'RS', { calibrar: false });
    await ponerBajada(request, plano.id, relleno.id, 'POINT(0 -4)');

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaEl = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaEl.getByRole('button', { name: `Rellenos de ${nombre}` }).click();
    const fila = zonaEl.getByTestId('rellenos-de-la-zona').locator('[data-relleno-de-la-zona="REL-AZOTEA"]');
    await expect(fila.getByTestId('relleno-dinamico')).toHaveAttribute('data-estado', 'sin_escala');
    await expect(fila.getByTestId('relleno-dinamico')).toContainText('calibrar la escala');
    await expect(fila.getByTestId('relleno-de-la-zona-resumen')).toContainText('0.000 m³ de EJ-830');
    await expect(page.getByTestId('hilo-de-nivel')).toHaveCount(0);
    const sin = (await calculo(request, 'control', zona.id)).rellenos[0]!;
    expect(sin.volumen_m3).toBe(0);
    expect(sin.conceptos.every((k) => k.cantidad === 0)).toBe(true);

    await llamarApi(request, 'control', 'PUT', `/planos/${plano.id}/escala`, { punto_a: [0, 0], punto_b: [4, 0], distancia_m: '4' });
    await page.reload();
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaDeNuevo = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaDeNuevo.getByRole('button', { name: `Rellenos de ${nombre}` }).click();
    const filaDeNuevo = zonaDeNuevo.getByTestId('rellenos-de-la-zona').locator('[data-relleno-de-la-zona="REL-AZOTEA"]');
    await expect(filaDeNuevo.getByTestId('relleno-dinamico')).toHaveAttribute('data-estado', 'calculado');
    await expect.poll(async () => page.getByTestId('hilo-de-nivel').count()).toBeGreaterThan(0);
  });

  test('Costos lee sin editar y propone la arenilla; Control de obra la autoriza y el catálogo no cambia; el compactado mide su volumen por el factor', async ({ page, request }) => {
    const { obra, actividad, plano, zona, nombre, relleno } = await prepararZona(request, 'RK');
    await ponerBajada(request, plano.id, relleno.id, 'POINT(0 -4)');
    await llamarApi(request, 'control', 'POST', `/zonas-de-losa/${zona.id}/rellenos`, { elemento_clave: 'REL-COMPACTADO', espesor_m: 0.2, factor_abundamiento: 1.25 });

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'costos');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const zonaEl = page.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').filter({ hasText: nombre });
    await zonaEl.getByRole('button', { name: `Rellenos de ${nombre}` }).click();
    const panel = zonaEl.getByTestId('rellenos-de-la-zona');
    const azotea = panel.locator('[data-relleno-de-la-zona="REL-AZOTEA"]');
    await expect(azotea.getByTestId('bajada-del-relleno')).toHaveCount(1);

    // Costos lee: no coloca ni quita bajadas, no cambia parámetros.
    await expect(panel.getByRole('button', { name: /Colocar bajada pluvial/ })).toHaveCount(0);
    await expect(panel.getByRole('button', { name: /Quitar la bajada/ })).toHaveCount(0);
    await expect(panel.getByLabel('Pendiente de la zona del relleno 1')).toBeDisabled();

    // Propone los conceptos nuevos (la arenilla EJ-830 y el compactado EJ-810; si otra corrida ya los propuso, el botón no aparece).
    const proponer = panel.getByRole('button', { name: /^Proponer (los conceptos nuevos|el concepto de la arenilla|el concepto del relleno compactado)/ });
    if (await proponer.isVisible()) await proponer.click();
    await expect(azotea.getByText(/EJ-830 · propuesto \((pendiente|autorizada)\)/)).toBeVisible();
    await expect(azotea.getByText('ALB-03014 · del catálogo')).toBeVisible();

    // Control de obra autoriza lo que quede pendiente (por la API, con su token); el catálogo no cambia: nadie creó un concepto.
    const pendientes = await llamarApi<{ id: string; concepto_clave: string }[]>(request, 'control', 'GET', '/propuestas-de-estructura/pendientes');
    for (const p of pendientes.filter((x) => x.concepto_clave === 'EJ-830' || x.concepto_clave === 'EJ-810')) {
      await llamarApi(request, 'control', 'POST', `/propuestas-de-estructura/${p.id}/autorizar`);
    }
    const c = await calculo(request, 'costos', zona.id);
    const arenilla = c.rellenos.find((r) => r.modo === 'bajadas')!.conceptos.find((k) => k.concepto.clave === 'EJ-830')!;
    expect(arenilla.propuesta!.estado).toBe('autorizada');
    const compactado = c.rellenos.find((r) => r.id !== relleno.id)!;
    expect(compactado.volumen_m3).toBeCloseTo(32 * 0.2, 5);
    expect(compactado.conceptos[0]!.cantidad).toBeCloseTo(32 * 0.2 * 1.25, 5); // volumen compactado × factor de abundamiento
    expect(compactado.conceptos[0]!.unidad).toBe('m³');
  });
});
