import { cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Zonas de losa, Fase 1: Control de obra define dos zonas (3.00 y 4.20) y dibuja sus losas sobre el plano; un muro que las cruza se
 * lee en tramos con su altura, uno en el límite lleva enrase y una altura por cara; un punto de nivel exterior fija el suelo de la
 * cara exterior. Costos solo lee. Lo que ya estaba trazado no se mueve.
 */

const ROLES_Z = ['control', 'costos'] as const;

type Trazo = { id: string; geometry: { type: string; coordinates: unknown }; properties: { losa_zona_id?: string | null; nivel_exterior_m?: string | null; rotulo?: string | null } };

test.describe('Cuantificador · zonas de losa', () => {
  test.skip(!hayRoles(...ROLES_Z), motivoSinRoles(...ROLES_Z));
  test.setTimeout(180_000);

  test('dos zonas, sus losas, un muro que cruza el límite, el enrase y el punto de nivel exterior', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `ZL-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'PB con desniveles',
      archivo_url: 'planos/zonas.dwg',
    });
    const trazos = async () => (await llamarApi<{ features: Trazo[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)).features;

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = await cajaEstable(page, lienzo);
    const clic = (fx: number, fy: number) => page.mouse.click(c.x + c.width * fx, c.y + c.height * fy);

    // Las zonas se crean en el panel de la pestaña Trazos.
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

    // «Dibujar losa»: el rectángulo que se traza nace como losa de la zona (sin pedir concepto ni cajón).
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
    await expect(page.getByTestId('etiquetas')).toContainText('Losa · Entrepiso 3.00');
    const zonas = (await llamarApi<{ zonas: { id: string; nombre: string; losas: unknown[] }[] }>(request, 'control', 'GET', `/planos/${plano.id}/zonas-de-losa`)).zonas;
    expect(zonas.map((z) => z.losas.length)).toEqual([1, 1]);

    // Un muro (línea con grosor) que cruza el límite entre las dos losas: se lee en dos tramos con su altura.
    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    await page.getByRole('button', { name: '0.15 m' }).click();
    await clic(0.55, 0.27);
    await clic(0.85, 0.27);
    await expect.poll(async () => (await trazos()).filter((t) => t.geometry.type === 'LineString').length).toBe(1);
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    // El muro queda dentro de las losas (un clic ahí elegiría la losa): se elige desde la lista de trazos.
    await page.getByRole('list', { name: 'Todos los trazos del plano' }).getByRole('listitem').filter({ hasText: /Muro/ }).click();
    const detalle = page.getByTestId('zona-del-muro');
    await expect(detalle).toBeVisible();
    await expect(detalle.getByTestId('tramo-de-zona')).toHaveCount(2);
    await expect(detalle.getByTestId('tramo-de-zona').nth(0)).toContainText('3.00 m');
    await expect(detalle.getByTestId('tramo-de-zona').nth(1)).toContainText('4.20 m');
    await expect(detalle.getByTestId('muro-por-partir')).toBeVisible();
    // Un muro que cruza zonas cuenta por tramos dentro del mismo trazo: se puede aplicar (no se parte el trazo).
    await expect(detalle.getByRole('button', { name: 'Aplicar al muro' })).toBeVisible();

    // Un muro sobre el límite (a lo largo del lado compartido): enrase de 3.00 a 4.20 y una altura por cara, vía API.
    const rectas = (await trazos()).filter((t) => t.properties.losa_zona_id);
    const xs = rectas.flatMap((t) => (t.geometry.coordinates as number[][][])[0]!.map((p) => p[0]!));
    const ordenadas = [...new Set(xs)].sort((a, b) => a - b);
    const limite = ordenadas[1]!;
    const ys = (rectas[0]!.geometry.coordinates as number[][][])[0]!.map((p) => p[1]!);
    const frontera = await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'pdf',
      geometria_wkt: `LINESTRING(${limite} ${Math.max(...ys)}, ${limite} ${Math.min(...ys)})`,
      enlaces: [],
    });
    const r = await llamarApi<{ tramos: { enrase: { desde_m: string; hasta_m: string } | null; lado_a: { altura_m: string; zona: string }; lado_b: { altura_m: string; zona: string } }[] }>(
      request, 'control', 'GET', `/trazos/${frontera.trazo_id}/zonas-de-losa`,
    );
    const t = r.tramos[0]!;
    expect(t.enrase).not.toBeNull();
    expect([Number(t.enrase!.desde_m), Number(t.enrase!.hasta_m)]).toEqual([3, 4.2]);
    expect([t.lado_a.altura_m, t.lado_b.altura_m].map(Number).sort()).toEqual([3, 4.2]);

    // Punto de nivel exterior: con su cota y su rótulo, colocado con la herramienta Punto.
    await panel.getByLabel('Cota del punto de nivel').fill('-0.30');
    await panel.getByLabel('Rótulo del punto de nivel').fill('Banqueta');
    await panel.getByRole('button', { name: 'Colocar punto de nivel exterior' }).click();
    await clic(0.6, 0.8);
    await expect.poll(async () => (await trazos()).filter((x) => x.properties.nivel_exterior_m != null).length).toBe(1);
    await page.keyboard.press('Escape');
    await expect(panel.getByTestId('punto-de-nivel')).toContainText('Banqueta');
    await expect(panel.getByTestId('punto-de-nivel')).toContainText('−0.30 m');
  });

  test('un muro bajo una sola losa muestra su altura y caras, y «Aplicar al muro» la fija sin tocar lo demás', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `ZA-${sufijo}`,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, { nombre: 'P', archivo_url: 'planos/za.dwg' });
    const zona = await llamarApi<{ id: string }>(request, 'control', 'POST', `/planos/${plano.id}/zonas-de-losa`, { nombre: 'Sala 3.00', altura_libre_m: '3', espesor_m: '0.12' });
    const nuevo = (wkt: string, grosor = false) =>
      llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
        version_plano: 1, fuente: 'pdf', geometria_wkt: wkt, enlaces: [], ...(grosor ? { grosor_m: '0.15', alineacion: 'centro' } : {}),
      });
    const losa = await nuevo('POLYGON((0 -4, 6 -4, 6 0, 0 0, 0 -4))');
    await llamarApi(request, 'control', 'PUT', `/trazos/${losa.trazo_id}/losa`, { zona_id: zona.id });
    // En el borde (y = 0): la losa queda a la izquierda del sentido de dibujo (cara A), por fuera no hay losa (cara B).
    const muro = await nuevo('LINESTRING(1 0, 5 0)', true);

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    await page.getByRole('list', { name: 'Todos los trazos del plano' }).getByRole('listitem').filter({ hasText: /Muro/ }).click();
    const detalle = page.getByTestId('zona-del-muro');
    await expect(detalle.getByTestId('tramo-de-zona')).toHaveCount(1);
    await expect(detalle.getByTestId('tramo-de-zona')).toContainText('3.00 m');
    await expect(detalle.getByTestId('tramo-de-zona')).toContainText('interior');
    await expect(detalle.getByTestId('tramo-de-zona')).toContainText('exterior');
    await detalle.getByRole('button', { name: 'Aplicar al muro' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Altura de la zona aplicada' })).toBeVisible();
    const m = await llamarApi<{ altura_m: string | null }>(request, 'control', 'GET', `/trazos/${muro.trazo_id}/muro`);
    expect(Number(m.altura_m)).toBe(3);
  });

  /** Una obra con un plano, dos zonas (3.00 y 4.20) y una losa por zona: 3.00 de x 0 a 6 y 4.20 de x 6 a 12 (y de -4 a 0). */
  async function dosCuartos(request: Parameters<typeof llamarApi>[0], prefijo: string) {
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
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, { nombre: 'PB', archivo_url: `planos/${prefijo}.dwg` });
    for (const [nombre, altura, espesor, wkt] of [
      ['Entrepiso 3.00', '3.00', '0.12', 'POLYGON((0 -4, 6 -4, 6 0, 0 0, 0 -4))'],
      ['Entrepiso 4.20', '4.20', '0.20', 'POLYGON((6 -4, 12 -4, 12 0, 6 0, 6 -4))'],
    ] as const) {
      const z = await llamarApi<{ id: string }>(request, 'control', 'POST', `/planos/${plano.id}/zonas-de-losa`, { nombre, altura_libre_m: altura, espesor_m: espesor });
      const losa = await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, { version_plano: 1, fuente: 'pdf', geometria_wkt: wkt, enlaces: [] });
      await llamarApi(request, 'control', 'PUT', `/trazos/${losa.trazo_id}/losa`, { zona_id: z.id });
    }
    const muro = (wkt: string, conversion: Record<string, unknown>) =>
      llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
        version_plano: 1, fuente: 'pdf', geometria_wkt: wkt, grosor_m: '0.15', alineacion: 'centro',
        enlaces: [{ medida: 'longitud', factor: '1', actividad_id: actividad.id, conversion }],
      });
    const cantidad = async () => {
      const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/cuantificacion`);
      return Number(nodos.find((n) => n.nodo_id === actividad.id)?.cantidad_medida ?? 0);
    };
    return { obra, plano, actividad, muro, cantidad };
  }

  test('un muro en el límite 3.00/4.20, trazado una vez a 4.20, se aplica desde la pantalla con altura por cara y enrase', async ({ page, request }) => {
    const { obra, plano, muro, cantidad } = await dosCuartos(request, 'ZB');
    // Dibujado hacia arriba sobre el límite (x = 6): la cara A (izquierda) mira a la losa de 3.00, la B a la de 4.20.
    const limite = await muro('LINESTRING(6 0, 6 -4)', { modo: 'area', mide: 'cara2', cara: 'int', lado: 'der', alt: 4.2 });
    expect(await cantidad()).toBeCloseTo(33.6, 2);

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    await page.getByRole('list', { name: 'Todos los trazos del plano' }).getByRole('listitem').filter({ hasText: /Muro/ }).click();
    const detalle = page.getByTestId('zona-del-muro');
    await expect(detalle.getByTestId('tramo-de-zona')).toHaveCount(1);
    // La vista previa: el cuerpo es interior por las dos caras; el enrase es exterior del lado de la losa baja e interior del de la alta.
    const partes = detalle.getByTestId('parte-por-cara');
    await expect(partes).toHaveCount(2);
    await expect(partes.nth(0)).toContainText('Cuerpo 0.00 m–3.00 m · A interior · B interior');
    await expect(partes.nth(1)).toContainText('Enrase 3.00 m–4.20 m · A exterior · B interior');
    await expect(detalle.getByTestId('muro-por-partir')).toHaveCount(0);
    await detalle.getByRole('button', { name: 'Aplicar al muro' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'con enrase y altura por cara' })).toBeVisible();

    const m = await llamarApi<{ partes: { rol: string; desde_m: string; hasta_m: string; cara_a: string; cara_b: string }[] }>(request, 'control', 'GET', `/trazos/${limite.trazo_id}/muro`);
    expect(m.partes.map((p) => [p.rol, Number(p.desde_m), Number(p.hasta_m), p.cara_a, p.cara_b])).toEqual([
      ['cuerpo', 0, 3, 'interior', 'interior'],
      ['enrase', 3, 4.2, 'exterior', 'interior'],
    ]);
    // La superficie no cambia (4 m × 4.20 × 2 caras): la altura por cara solo reparte interior y exterior.
    expect(await cantidad()).toBeCloseTo(33.6, 2);
    // Con la altura ya fijada en el muro, la zona ya no tiene qué aplicar.
    await expect(detalle.getByRole('button', { name: 'Aplicar al muro' })).toHaveCount(0);
  });

  test('un muro que cruza de una zona a otra cuenta por dos tramos dentro de un solo trazo y cada vano va a su tramo', async ({ page, request }) => {
    const { obra, plano, muro, cantidad } = await dosCuartos(request, 'ZX');
    // Nace sin altura: la toma de las zonas que cruza, por tramos (4 m a 3.00 y 4 m a 4.20, dos caras).
    const cruza = await muro('LINESTRING(2 -2, 10 -2)', { modo: 'area', mide: 'cara2', cara: 'int', lado: 'der' });
    expect(await cantidad()).toBeCloseTo(57.6, 2);
    const trazos = await llamarApi<{ features: { geometry: { type: string } }[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`);
    expect(trazos.features.filter((f) => f.geometry.type === 'LineString')).toHaveLength(1); // un solo trazo: no se partió
    for (const posicion of ['1', '6']) {
      await llamarApi(request, 'control', 'POST', `/trazos/${cruza.trazo_id}/vanos`, { clave: `P-${posicion}`, tipo: 'puerta', ancho_m: '0.9', alto_m: '2.1', posicion_m: posicion });
    }
    // Cada puerta descuenta 0.9 × 2.1 × 2 caras = 3.78: 57.60 − 7.56.
    await expect.poll(cantidad).toBeCloseTo(50.04, 2);

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    await page.getByRole('list', { name: 'Todos los trazos del plano' }).getByRole('listitem').filter({ hasText: /Muro/ }).click();
    const detalle = page.getByTestId('zona-del-muro');
    await expect(detalle.getByTestId('tramo-de-zona')).toHaveCount(2);
    await expect(detalle.getByTestId('tramo-de-zona').nth(0)).toContainText('3.00 m');
    await expect(detalle.getByTestId('tramo-de-zona').nth(1)).toContainText('4.20 m');
    await expect(detalle.getByTestId('muro-por-partir')).toContainText('2 tramos dentro del mismo trazo');
    await expect(detalle.getByTestId('vanos-del-tramo').nth(0)).toContainText('P-1');
    await expect(detalle.getByTestId('vanos-del-tramo').nth(1)).toContainText('P-6');
    await detalle.getByRole('button', { name: 'Aplicar al muro' }).click();
    await expect(page.getByRole('status').filter({ hasText: '2 tramos dentro del mismo trazo' })).toBeVisible();

    // Un solo enlace vigente, con sus dos tramos, y lo mismo de antes (los vanos siguen en su tramo).
    const feats = await llamarApi<{ features: { properties: { trazo_id: string; enlaces: { enlace_id: string; vigente: boolean }[] } }[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`);
    const vigentes = feats.features.find((f) => f.properties.trazo_id === cruza.trazo_id)!.properties.enlaces.filter((e) => e.vigente);
    expect(vigentes).toHaveLength(1);
    const conv = await llamarApi<{ conversion: { tramos: { desde_m: number; hasta_m: number; alt: number }[] } }>(request, 'control', 'GET', `/enlaces/${vigentes[0]!.enlace_id}/conversion`);
    expect(conv.conversion.tramos.map((t) => [t.desde_m, t.hasta_m, t.alt])).toEqual([[0, 4, 3], [4, 8, 4.2]]);
    await expect.poll(cantidad).toBeCloseTo(50.04, 2);
  });

  test('Costos ve las zonas pero no las edita', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `ZC-${sufijo}`,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, { nombre: 'P', archivo_url: 'planos/zc.dwg' });
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/zonas-de-losa`, { nombre: 'Solo lectura', altura_libre_m: '3', espesor_m: '0.12' });

    await entrarComo(page, 'costos');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tab', { name: /Trazos/ }).click();
    const panel = page.getByTestId('zonas-de-losa');
    await expect(panel.getByTestId('zona-de-losa')).toContainText('Solo lectura');
    await expect(panel.getByRole('button', { name: 'Nueva zona' })).toHaveCount(0);
    await expect(panel.getByRole('button', { name: 'Dibujar losa' })).toHaveCount(0);
  });
});
