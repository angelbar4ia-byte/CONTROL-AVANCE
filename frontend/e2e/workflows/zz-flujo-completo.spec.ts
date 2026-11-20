import { altoPropio, cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, pulsarMarca, solicitarApi, test } from '../infraestructura';

/**
 * El flujo completo de punta a punta (Ola 5, cierre): lo que se pasó del mockup a la app, recorrido como lo haría Control de obra y Costos.
 *
 *  1. Zonas de losa (3.00 y 4.20) creadas y dibujadas desde el panel; un muro que las cruza se lee por tramos; un muro en el límite se traza
 *     UNA vez a 4.20 y «Aplicar al muro» le pone enrase y altura por cara; la superficie no cambia. La fachada por bandas reparte la cara
 *     exterior (panel = servidor) y los castillos no se restan como vanos.
 *  2. Plantilla de confinado por prototipo (varios castillos con regla) y plantilla «muros y cadena»: el muro pasa de una a otra y de vuelta
 *     conservando la medición, los vanos y el acabado, y sin contar dos veces los castillos sembrados.
 *  3. Elementos de la biblioteca: bastones con gancho (el largo capturado incluye los ganchos), trabes por ml y sillar amarillo de 19 cm.
 *  4. Autorización: Costos propone (elemento, concepto nuevo y versión) y solo Control de obra autoriza.
 *
 * Una base ya usada no lo estorba: cada prueba crea su obra y su plano, y los castillos nuevos llevan un alto propio (rango 8.0 y 8.1 en
 * `infraestructura.ts`, que la firma anti-duplicados M-29 pide único).
 */

const ROLES_FLUJO = ['control', 'costos'] as const;

type Api = Parameters<typeof llamarApi>[0];
interface Trazo {
  id: string;
  geometry: { type: string; coordinates: unknown };
  properties: { losa_zona_id?: string | null };
}
interface Elemento {
  clave: string;
}
interface Vano {
  id: string;
  tipo: string;
  elemento_uid: string | null;
}
interface Fachada {
  bandas: { banda: string; neto_m2: string }[];
  vanos_m2: string;
  neto_m2: string;
  muros_sin_cara_exterior: { trazo_id: string }[];
}

async function nuevaObra(request: Api, prefijo: string) {
  const sufijo = Date.now().toString(36).toUpperCase();
  const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
  const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
  const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
    cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
    prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
    clave: `${prefijo}-${sufijo}`,
  });
  const actividades = await llamarApi<{ id: string; unidad?: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
  const actividad = actividades.find((a) => (a.unidad ?? '').toLowerCase().replace('²', '2') === 'm2') ?? actividades[0]!;
  const nuevoPlano = async (nombre: string) => {
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, { nombre, archivo_url: `planos/${prefijo}-${nombre}.dwg` });
    const trazo = (wkt: string, extra: Record<string, unknown> = {}) =>
      llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, { version_plano: 1, fuente: 'pdf', geometria_wkt: wkt, enlaces: [], ...extra });
    const trazos = async () => (await llamarApi<{ features: Trazo[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)).features;
    return { plano, trazo, trazos };
  };
  const cantidad = async () => {
    const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/cuantificacion`);
    return Number(nodos.find((n) => n.nodo_id === actividad.id)?.cantidad_medida ?? 0);
  };
  return { obra, actividad, nuevoPlano, cantidad, sufijo };
}

/** Crea el elemento si no existe (otro spec pudo crearlo a la vez: basta con que exista). */
async function asegurar(request: Api, existentes: Set<string>, clave: string, cuerpo: Record<string, unknown>) {
  if (existentes.has(clave)) return;
  try {
    await llamarApi(request, 'control', 'POST', '/elementos-parametricos', { clave, nombre: `Elemento ${clave}`, ...cuerpo });
  } catch (e) {
    const ahora = await llamarApi<Elemento[]>(request, 'control', 'GET', '/elementos-parametricos');
    if (!ahora.some((x) => x.clave === clave)) throw e;
  }
}

const netos = (f: Fachada) => Object.fromEntries(f.bandas.map((b) => [b.banda, Number(b.neto_m2)]));

test.describe('Cuantificador · el flujo completo, de punta a punta', () => {
  test.skip(!hayRoles(...ROLES_FLUJO), motivoSinRoles(...ROLES_FLUJO));
  test.setTimeout(240_000);

  test('zonas de losa, muro por tramos y por cara, y fachada por bandas', async ({ page, browser, request }) => {
    const { obra, actividad, nuevoPlano, cantidad } = await nuevaObra(request, 'FZ');
    const { plano, trazo, trazos } = await nuevoPlano('PB con desniveles');

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = await cajaEstable(page, lienzo);
    const clic = (fx: number, fy: number) => page.mouse.click(c.x + c.width * fx, c.y + c.height * fy);

    // --- 1. Las zonas y sus losas, desde el panel -----------------------------------------------------------------------------------
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const panel = page.getByTestId('zonas-de-losa');
    const nuevaZona = async (nombre: string, altura: string, espesor: string) => {
      await panel.getByRole('button', { name: 'Nueva zona' }).click();
      await panel.getByLabel('Nombre de la zona').fill(nombre);
      await panel.getByLabel('Altura libre (m)').fill(altura);
      await panel.getByLabel('Espesor de la losa (m)').fill(espesor);
      await panel.getByRole('button', { name: 'Guardar zona' }).click();
      await expect(panel.getByTestId('zona-de-losa').filter({ hasText: nombre })).toBeVisible();
    };
    await nuevaZona('Entrepiso 3.00', '3.00', '0.12');
    await nuevaZona('Entrepiso 4.20', '4.20', '0.20');
    await expect(panel.getByTestId('zona-de-losa').first()).toContainText('+3.00 m');
    const dibujarLosa = async (zona: string, x1: number, x2: number) => {
      await panel.getByTestId('zona-de-losa').filter({ hasText: zona }).getByRole('button', { name: 'Dibujar losa' }).click();
      await clic(x1, 0.2);
      await clic(x2, 0.5);
      await expect.poll(async () => (await trazos()).filter((t) => t.properties.losa_zona_id).length).toBeGreaterThan(0);
      await page.keyboard.press('Escape');
    };
    await dibujarLosa('Entrepiso 3.00', 0.5, 0.7);
    await dibujarLosa('Entrepiso 4.20', 0.7, 0.9);
    await expect.poll(async () => (await trazos()).filter((t) => t.properties.losa_zona_id).length).toBe(2);
    const zonas = (await llamarApi<{ zonas: { losas: unknown[] }[] }>(request, 'control', 'GET', `/planos/${plano.id}/zonas-de-losa`)).zonas;
    expect(zonas.map((z) => z.losas.length)).toEqual([1, 1]);

    // --- 2. Un muro dibujado cruza el límite: dos tramos dentro del mismo trazo -------------------------------------------------------
    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    await page.getByRole('button', { name: '0.15 m' }).click();
    await clic(0.55, 0.27);
    await clic(0.85, 0.27);
    await expect.poll(async () => (await trazos()).filter((t) => t.geometry.type === 'LineString').length).toBe(1);
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    await page.getByRole('list', { name: 'Todos los trazos del plano' }).getByRole('listitem').filter({ hasText: /Muro/ }).click();
    const detalle = page.getByTestId('zona-del-muro');
    await expect(detalle.getByTestId('tramo-de-zona')).toHaveCount(2);
    await expect(detalle.getByTestId('tramo-de-zona').nth(0)).toContainText('3.00 m');
    await expect(detalle.getByTestId('tramo-de-zona').nth(1)).toContainText('4.20 m');
    await expect(detalle.getByTestId('muro-por-partir')).toContainText('2 tramos dentro del mismo trazo');
    expect((await trazos()).filter((t) => t.geometry.type === 'LineString')).toHaveLength(1); // no se partió el trazo

    // --- 3. Un muro en el límite, trazado UNA vez a 4.20: altura por cara y enrase --------------------------------------------------
    const rectas = (await trazos()).filter((t) => t.properties.losa_zona_id);
    const xs = rectas.flatMap((t) => (t.geometry.coordinates as number[][][])[0]!.map((p) => p[0]!));
    const limite = [...new Set(xs)].sort((a, b) => a - b)[1]!;
    const ys = (rectas[0]!.geometry.coordinates as number[][][])[0]!.map((p) => p[1]!);
    const enLimite = await trazo(`LINESTRING(${limite} ${Math.max(...ys)}, ${limite} ${Math.min(...ys)})`, {
      grosor_m: '0.15', alineacion: 'centro', capa: 'Muro del límite',
      enlaces: [{ medida: 'longitud', factor: '1', actividad_id: actividad.id, conversion: { modo: 'area', mide: 'cara2', cara: 'int', lado: 'der', alt: 4.2 } }],
    });
    const antes = await cantidad();
    await page.reload();
    await page.getByRole('tab', { name: /Trazos/ }).click();
    await page.getByRole('list', { name: 'Todos los trazos del plano' }).getByRole('listitem').filter({ hasText: 'Muro del límite' }).click();
    const partes = detalle.getByTestId('parte-por-cara');
    await expect(partes).toHaveCount(2);
    await expect(partes.nth(0)).toContainText('Cuerpo 0.00 m–3.00 m');
    await expect(partes.nth(1)).toContainText('Enrase 3.00 m–4.20 m');
    await detalle.getByRole('button', { name: 'Aplicar al muro' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'con enrase y altura por cara' })).toBeVisible();
    const muro = await llamarApi<{ partes: { rol: string; desde_m: string; hasta_m: string }[] }>(request, 'control', 'GET', `/trazos/${enLimite.trazo_id}/muro`);
    expect(muro.partes.map((p) => [p.rol, Number(p.desde_m), Number(p.hasta_m)])).toEqual([['cuerpo', 0, 3], ['enrase', 3, 4.2]]);
    expect(await cantidad()).toBeCloseTo(antes, 2); // la altura por cara solo reparte interior y exterior: la superficie no cambia
    await expect(detalle.getByRole('button', { name: 'Aplicar al muro' })).toHaveCount(0);

    // --- 4. La fachada por bandas: la cara exterior del cuarto de 4.20 ------------------------------------------------------------
    // Plano aparte con coordenadas conocidas (dos cuartos de 6 × 4 m); el borde de arriba del de 4.20 mira afuera con su cara A.
    const dos = await nuevoPlano('Dos cuartos');
    for (const [nombre, altura, espesor, wkt] of [
      ['Entrepiso 3.00', '3.00', '0.12', 'POLYGON((0 -4, 6 -4, 6 0, 0 0, 0 -4))'],
      ['Entrepiso 4.20', '4.20', '0.20', 'POLYGON((6 -4, 12 -4, 12 0, 6 0, 6 -4))'],
    ] as const) {
      const z = await llamarApi<{ id: string }>(request, 'control', 'POST', `/planos/${dos.plano.id}/zonas-de-losa`, { nombre, altura_libre_m: altura, espesor_m: espesor });
      const losa = await dos.trazo(wkt);
      await llamarApi(request, 'control', 'PUT', `/trazos/${losa.trazo_id}/losa`, { zona_id: z.id });
    }
    await dos.trazo('LINESTRING(6 -4, 12 -4)', { grosor_m: '0.15', alineacion: 'centro' });
    // Dos castillos colocados en un muro de fachada A: la fachada no los resta como vanos (corrección de la 196).
    const fachadaA = await dos.trazo('LINESTRING(0 10, 5 10)', { grosor_m: '0.15', alineacion: 'centro' });
    await llamarApi(request, 'control', 'PUT', `/trazos/${fachadaA.trazo_id}/muro/clasificacion`, { tipo: 'con_cadena', ubicacion: 'fachada_a' });
    await llamarApi(request, 'control', 'PUT', `/trazos/${fachadaA.trazo_id}/muro`, { altura_m: '4.5', caras: 2 });
    for (const [clave, posicion] of [['K-1', '1'], ['K-2', '4']] as const) {
      await llamarApi(request, 'control', 'POST', `/trazos/${fachadaA.trazo_id}/vanos`, { clave, tipo: 'castillo', ancho_m: '0.15', alto_m: '3', posicion_m: posicion });
    }
    const fachada = await llamarApi<Fachada>(request, 'control', 'GET', `/planos/${dos.plano.id}/fachada-por-bandas`);
    expect(netos(fachada)).toEqual({ baja: 18 + 15, media: 7.2 + 6, resto: 1.5 }); // 3.00 + 4.20 de la zona, y la fachada A por su altura real
    expect(Number(fachada.vanos_m2)).toBe(0);

    await page.goto(`/cuantificador?obra=${obra.id}&plano=${dos.plano.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const bandas = page.locator('[data-fachada-por-bandas]');
    await expect(bandas.locator('[data-fachada-banda="baja"] [data-neto]')).toHaveText('33.00');
    await expect(bandas.locator('[data-fachada-banda="media"] [data-neto]')).toHaveText('13.20');
    await expect(bandas.locator('[data-fachada-banda="resto"] [data-neto]')).toHaveText('1.50');
    await expect(bandas.locator('[data-fachada-total] [data-neto]')).toHaveText('47.70');
    await expect(bandas.locator('[data-fachada-nota-vanos]')).toContainText('se restan todos menos los castillos');

    // Costos ve las zonas pero no las edita (otra sesión: la de Control de obra sigue abierta).
    const costos = await browser.newPage();
    await entrarComo(costos, 'costos');
    await costos.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await costos.getByRole('tab', { name: /Trazos/ }).click();
    await expect(costos.getByTestId('zonas-de-losa').getByTestId('zona-de-losa').first()).toBeVisible();
    await expect(costos.getByTestId('zonas-de-losa').getByRole('button', { name: 'Nueva zona' })).toHaveCount(0);
    await costos.close();
  });

  test('plantillas de confinado y de muros y cadena: el muro cambia conservando medición, vanos y acabado', async ({ page, request }) => {
    const { obra, actividad, nuevoPlano, sufijo } = await nuevaObra(request, 'FP');
    const { plano, trazo } = await nuevoPlano('Muros por prototipo');
    const existentes = new Set((await llamarApi<Elemento[]>(request, 'control', 'GET', '/elementos-parametricos')).map((e) => e.clave));
    for (const [n, k] of ['K-1', 'K-2', 'K-3', 'K-6', 'K-7'].entries()) {
      await asegurar(request, existentes, k, { tipo: 'castillo', parametros: { largo: 0.4 + n / 1000, ancho: 0.15 } });
    }
    for (const [n, k] of ['CE-1', 'CE-2'].entries()) {
      await asegurar(request, existentes, k, { tipo: 'lineal', categoria: 'cadenas', subcategoria: 'cerramiento', parametros: { ancho: 0.4 + n / 1000, alto: 0.2 } });
    }
    const partes = [{ nombre: 'Cuerpo', desde_m: '0', hasta_m: '3', rol: 'cuerpo' }];
    // Confinado de un prototipo con VARIOS castillos, cada uno con su regla; y la 2, «muros y cadena», con plano estructural.
    const nombreConfinado = `Oro PB flujo ${sufijo}`;
    const confinado = await llamarApi<{ id: string }>(request, 'control', 'POST', '/muro-plantillas', {
      nombre: nombreConfinado, tipo: 'confinado', material: 'tabique_rojo', ubicacion: 'interior', prototipo: 'oro_401', planta: 'PB', por_confirmar: true, partes,
      elementos: [
        { ref: 'K-1', regla: 'total', total_m: '126', base_m2: '286' },
        { ref: 'K-2', regla: 'por_ml', piezas_por_ml: '0.4' },
        { ref: 'K-3', regla: 'extremos' },
        { ref: 'CE-1' },
      ],
    });
    const conCadena = await llamarApi<{ id: string }>(request, 'control', 'POST', '/muro-plantillas', {
      nombre: `Muros y cadena flujo ${sufijo}`, tipo: 'con_cadena', material: 'tabique_rojo', ubicacion: 'interior', partes, elementos: [{ ref: 'CE-1' }],
    });
    const muro = (
      await trazo('LINESTRING(0 0, 10 0)', {
        grosor_m: '0.15', alineacion: 'centro',
        enlaces: [{ medida: 'longitud', factor: '1', actividad_id: actividad.id, conversion: { modo: 'area', mide: 'eje' } }],
      })
    ).trazo_id;
    await llamarApi(request, 'control', 'PUT', `/trazos/${muro}/muro/plantilla`, { plantilla_id: confinado.id });
    const acabado = {
      interior: { gris: true, blanca: true, pintura: false },
      fachada: { gris: true, blanca: false, pintura: false },
    };
    const clasificacion = () => llamarApi<{ plantilla_id: string | null; tipo: string; acabado: unknown }>(request, 'control', 'GET', `/trazos/${muro}/muro/clasificacion`);
    const vanos = () => llamarApi<Vano[]>(request, 'control', 'GET', `/trazos/${muro}/vanos`);
    const colocacion = () =>
      llamarApi<{ area_usada: string; area_neta_m2: string; elementos: { ref: string; regla: string | null; piezas_estimadas: string; piezas_sembradas: string; piezas_contadas: string }[] }>(
        request, 'control', 'GET', `/trazos/${muro}/muro/plantilla/colocacion`,
      );
    const medida = async () => {
      const todos = await llamarApi<{ features: { id: string; properties: { enlaces: { cantidad: string; vigente: boolean }[] } }[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`);
      return Number(todos.features.find((f) => f.id === muro)!.properties.enlaces.find((e) => e.vigente)!.cantidad);
    };
    await page.setViewportSize({ width: 1400, height: 1100 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad.id}`);
    await page.getByRole('toolbar', { name: 'Herramientas de trazo' }).getByRole('button', { name: 'Seleccionar', exact: true }).click();
    await cajaEstable(page, page.getByRole('img', { name: 'Plano con sus trazos' }));
    await pulsarMarca(page, page.locator('.visor__trazo').first());
    const selector = page.getByLabel('Plantilla de muro', { exact: true });
    await expect(selector).toHaveValue(confinado.id);
    // La puerta y el acabado entran con el muro ya elegido (la puerta cubre el trazo y estorbaría al pulsarlo).
    await llamarApi(request, 'control', 'PUT', `/trazos/${muro}/muro/clasificacion`, { tipo: 'confinado', material: 'tabique_rojo', ubicacion: 'interior', acabado });
    await llamarApi(request, 'control', 'POST', `/trazos/${muro}/vanos`, { clave: 'P-01', tipo: 'puerta', ancho_m: '1', alto_m: '2', posicion_m: '5' });
    // Con la puerta ya colocada el muro es neto: 30 − 2 = 28 m²; K-1 «total del prototipo»: 126 × 28 ÷ 286 ÷ 3.00 = 4.11 piezas.
    const inicial = await colocacion();
    expect([inicial.area_usada, Number(inicial.area_neta_m2)]).toEqual(['neto', 28]);
    const k1 = inicial.elementos.find((e) => e.ref === 'K-1')!;
    expect([k1.regla, Number(k1.piezas_estimadas)]).toEqual(['total', expect.closeTo(4.112, 3)]);
    expect(inicial.elementos.find((e) => e.ref === 'K-2')!.regla).toBe('por_ml');
    expect(inicial.elementos.find((e) => e.ref === 'K-3')!.regla).toBe('extremos');
    const m0 = await medida();
    expect(m0).toBeCloseTo(28, 2);

    const cambio = page.getByRole('region', { name: 'Cambiar de plantilla' });

    // --- A «muros y cadena»: dice qué cambia y conserva medición, vano y acabado ------------------------------------------------------
    await selector.selectOption(conCadena.id);
    await expect(cambio.locator('[data-cambia="tipo"]')).toContainText('con_cadena');
    await expect(cambio.locator('[data-elemento="K-1"]')).toHaveAttribute('data-efecto', 'deja');
    await expect(cambio.getByTestId('acabado-se-conserva')).toHaveAttribute('data-conserva', 'si');
    await expect(cambio).toContainText('1 vano');
    await cambio.getByRole('button', { name: 'Cambiar de plantilla' }).click();
    await expect.poll(async () => (await clasificacion()).plantilla_id).toBe(conCadena.id);
    await expect(selector).toHaveValue(conCadena.id);
    expect((await clasificacion()).acabado).toEqual(acabado);
    expect(await vanos()).toHaveLength(1);
    expect(await medida()).toBeCloseTo(m0, 3);

    // --- Con plano estructural los castillos se siembran uno por uno, cada uno de su K ------------------------------------------------
    const alta = page.getByRole('group', { name: 'Colocar un vano' });
    await alta.getByLabel('Tipo de vano').selectOption('castillo');
    await alta.getByLabel('Castillo que se coloca (tipo K)').selectOption('K-2');
    await alta.getByRole('button', { name: 'Colocar', exact: true }).click();
    await expect.poll(async () => (await vanos()).length).toBe(2);
    await alta.getByLabel('Castillo que se coloca (tipo K)').selectOption('K-7');
    await alta.getByRole('button', { name: 'Colocar', exact: true }).click();
    await expect.poll(async () => (await vanos()).length).toBe(3);
    expect((await vanos()).filter((v) => v.tipo === 'castillo').map((v) => v.elemento_uid).sort()).toEqual(['K-2', 'K-7']);
    const sembrados = await medida();
    expect(sembrados).toBeLessThan(m0); // los castillos a mano restan de los m² del muro

    // --- De vuelta al confinado: se conservan, sin contarlos dos veces -------------------------------------------------------------------
    await selector.selectOption(confinado.id);
    await expect(cambio.getByTestId('castillos-sembrados')).toContainText('2 castillos ya sembrados');
    await expect(cambio).toContainText('dos veces');
    await expect(cambio.getByTestId('acabado-se-conserva')).toHaveAttribute('data-conserva', 'si');
    await cambio.getByRole('button', { name: 'Cambiar de plantilla' }).click();
    await expect.poll(async () => (await clasificacion()).plantilla_id).toBe(confinado.id);
    await expect(selector).toHaveValue(confinado.id);
    expect(await vanos()).toHaveLength(3);
    expect(await medida()).toBeCloseTo(sembrados, 3);
    expect((await clasificacion()).acabado).toEqual(acabado);
    const vuelta = await colocacion();
    const k2 = vuelta.elementos.find((e) => e.ref === 'K-2')!;
    expect(Number(k2.piezas_sembradas)).toBe(1);
    // Lo sembrado no se cuenta otra vez: estimadas − sembradas (sin bajar de cero).
    expect(Number(k2.piezas_contadas)).toBeCloseTo(Math.max(0, Number(k2.piezas_estimadas) - 1), 3);
  });

  test('bastones con gancho, trabes y sillar, y la autorización de Costos a Control de obra', async ({ page, browser, request }) => {
    const { obra, nuevoPlano, sufijo } = await nuevaObra(request, 'FE');
    const { plano } = await nuevoPlano('Elementos');
    const url = `/cuantificador?obra=${obra.id}&plano=${plano.id}`;
    await page.setViewportSize({ width: 1400, height: 1100 });
    await entrarComo(page, 'control');
    await page.goto(url);
    const pestanas = page.getByRole('tablist', { name: 'Panel lateral' });
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();
    const biblioteca = page.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    const area = page.getByRole('region', { name: 'Elementos', exact: true });

    // --- Bastones: el largo capturado INCLUYE los dos ganchos de 12 diámetros; el escalón se nombra por el tramo recto -----------------
    await biblioteca.getByRole('button', { name: /^BA-1\b/ }).click();
    const baston = area.getByRole('article', { name: /BA-1/ });
    await baston.getByLabel('Longitud de trazo').fill('10');
    await baston.getByLabel('Largo del bastón en centímetros').fill('142.86');
    await expect(baston.getByTestId('baston-piezas')).toContainText('41 bastones');
    await expect(baston.getByTestId('baston-gancho')).toContainText('2 × 11.43 cm = 22.86 cm por bastón');
    await expect(baston.getByTestId('baston-recto')).toContainText('Tramo recto 1.20 m');
    await expect(baston.getByRole('region', { name: 'Concepto que lo paga' })).toHaveAttribute('data-concepto-elegido', 'AUX-02010');
    await baston.getByLabel('Largo del bastón en centímetros').fill('700');
    await expect(baston.getByTestId('baston-corte')).toContainText('2 × 4.0 m'); // más de 6 m: dos piezas con traslape
    await baston.getByLabel('Largo del bastón en centímetros').fill('142.86');

    // --- Trabes por ml, con el colado y la cimbra por registrar (sin destajo inventado) ------------------------------------------------
    await biblioteca.getByRole('button', { name: /^T-1-15x25\b/ }).click();
    const trabe = area.getByRole('article', { name: /T-1-15x25/ });
    await expect(trabe.getByTestId('ee-seccion')).toContainText('15 × 25 cm (ancho × peralte)');
    await expect(trabe.getByTestId('ee-concreto')).toContainText('0.0394 m³ por metro');
    await expect(trabe.getByRole('region', { name: 'Colado, cimbra y destajo' })).toHaveAttribute('data-camino', 'por_registrar');
    await expect(trabe.getByTestId('ee-sin-destajo')).toContainText('no trae destajo');

    // --- Sillar amarillo de 19 cm: pieza real, concepto del catálogo y conciliación ----------------------------------------------------
    await biblioteca.getByRole('button', { name: /^BAP-01010\b/ }).click();
    const sillar = area.getByRole('article', { name: /BAP-01010/ });
    await expect(sillar.getByTestId('sillar-espesor')).toContainText('19.0 cm');
    await expect(sillar.getByTestId('sillar-mano-de-obra')).toContainText('MOE-02016');
    await expect(sillar.getByTestId('sillar-concepto')).toContainText('BAP-01010 · del catálogo');
    await expect(sillar.locator('[data-conciliacion="BAP-01010"] tr[data-marca="≠"]')).toHaveCount(2); // el catálogo no se edita: se muestra la diferencia

    // --- Costos propone un elemento y un concepto nuevo; solo Control de obra los autoriza ----------------------------------------------
    const clave = `KF-${sufijo}`.slice(0, 20);
    const elemento = await llamarApi<{ id: string; estado_autorizacion: string }>(request, 'costos', 'POST', '/elementos-parametricos', {
      clave, nombre: 'Castillo del flujo', tipo: 'castillo', parametros: { alto: altoPropio(8) },
    });
    expect(elemento.estado_autorizacion).toBe('pendiente');
    const claveNueva = `EJF-${sufijo}`.slice(0, 20);
    await llamarApi(request, 'costos', 'POST', `/elementos-parametricos/${elemento.id}/conceptos-por-contexto`, {
      clave_propuesta: claveNueva, descripcion: 'Castillo de entrepiso del flujo', unidad: 'ml', toma: { concreto: true },
    });
    // Costos no autoriza: ni el botón en la tarjeta del bastón ni la API.
    const costos = await browser.newPage();
    await entrarComo(costos, 'costos');
    await costos.goto(url);
    await costos.getByRole('tab', { name: /^Trazos/ }).click();
    await costos.getByRole('button', { name: `Ver ${clave}` }).click();
    const tarjetaCostos = costos.locator(`[data-autorizacion-del-elemento="${clave}"]`);
    await expect(tarjetaCostos.locator('[data-estado-de-autorizacion]')).toHaveAttribute('data-estado-de-autorizacion', 'pendiente');
    await expect(tarjetaCostos.getByRole('button', { name: 'Autorizar y crear v1' })).toHaveCount(0);
    await costos.close();
    expect((await solicitarApi(request, 'costos', 'POST', `/elementos-parametricos/${elemento.id}/autorizar`, {})).ok()).toBe(false);

    await page.getByRole('tab', { name: /^Trazos/ }).click();
    await page.getByRole('button', { name: `Ver ${clave}` }).click();
    const tarjeta = page.locator(`[data-autorizacion-del-elemento="${clave}"]`);
    await tarjeta.getByRole('button', { name: 'Autorizar y crear v1' }).click();
    await expect(tarjeta.locator('[data-estado-de-autorizacion]')).toHaveAttribute('data-estado-de-autorizacion', 'autorizado');
    await expect(tarjeta.locator('[data-version-del-elemento]')).toHaveText('v1');
    const fila = page.locator(`[data-concepto-por-contexto="${claveNueva}"]`);
    await expect(fila).toContainText('No cuenta en el presupuesto hasta autorizarse');
    await fila.getByRole('button', { name: 'Autorizar concepto' }).click();
    await expect(fila).toHaveAttribute('data-estado', 'autorizado');
    expect(await llamarApi<unknown[]>(request, 'control', 'GET', `/elementos-parametricos/${elemento.id}/conceptos`)).toHaveLength(1);
  });
});
