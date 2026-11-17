import { cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, pulsarMarca, test } from '../infraestructura';

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
    await clic(0.55, 0.35);
    await clic(0.85, 0.35);
    await expect.poll(async () => (await trazos()).filter((t) => t.geometry.type === 'LineString').length).toBe(1);
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    await pulsarMarca(page, page.locator('.visor__trazo').last());
    const detalle = page.getByTestId('zona-del-muro');
    await expect(detalle).toBeVisible();
    await expect(detalle.getByTestId('tramo-de-zona')).toHaveCount(2);
    await expect(detalle.getByTestId('tramo-de-zona').nth(0)).toContainText('3.00 m');
    await expect(detalle.getByTestId('tramo-de-zona').nth(1)).toContainText('4.20 m');
    await expect(detalle.getByTestId('muro-por-partir')).toBeVisible();
    await expect(detalle.getByRole('button', { name: 'Aplicar al muro' })).toHaveCount(0);

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
