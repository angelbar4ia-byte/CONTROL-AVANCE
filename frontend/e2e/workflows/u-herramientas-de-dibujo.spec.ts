import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Herramientas de dibujo del cuantificador: rectángulo, círculo, elipse, arco, línea y polilínea,
 * con el ortogonal (90° por defecto, Mayús para invertirlo, ángulo de trabajo editable) y la
 * referencia a objetos (el cursor se pega a los extremos de lo que ya hay).
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_U = ['control'] as const;

type Geo = { type: string; coordinates: unknown };
interface Feature {
  geometry: Geo;
  properties: { enlaces: { cantidad: string }[] };
}

const area = (anillo: [number, number][]) => {
  let s = 0;
  for (let i = 0; i < anillo.length - 1; i += 1) {
    s += anillo[i]![0] * anillo[i + 1]![1] - anillo[i + 1]![0] * anillo[i]![1];
  }
  return Math.abs(s) / 2;
};

test.describe('Cuantificador · herramientas de dibujo', () => {
  test.skip(!hayRoles(...ROLES_U), motivoSinRoles(...ROLES_U));
  test.setTimeout(150_000);

  test('rectángulo, círculo, elipse, arco, polilínea con ortogonal y referencia a objetos', async ({
    page,
    request,
  }) => {
    const clave = `DIB-${Date.now().toString(36).toUpperCase()}`;
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
    const actividades = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const planoNuevo = async (nombre: string) =>
      llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
        nombre,
        archivo_url: `planos/${nombre}.dwg`,
      });
    const trazosDe = async (planoId: string) =>
      (await llamarApi<{ features: Feature[] }>(request, 'control', 'GET', `/planos/${planoId}/trazos`)).features;

    await entrarComo(page, 'control');
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const abrir = async (planoId: string) => {
      await page.goto(`/cuantificador?obra=${obra.id}&plano=${planoId}`);
      await expect(lienzo).toBeVisible();
    };
    const en = async (fx: number, fy: number) => {
      const c = (await lienzo.boundingBox())!;
      return { x: c.x + c.width * fx, y: c.y + c.height * fy };
    };
    const clic = async (fx: number, fy: number) => {
      const p = await en(fx, fy);
      await page.mouse.click(p.x, p.y);
    };
    const guardar = async (nombre: string, medida: string) => {
      const alta = page.getByRole('dialog', { name: nombre });
      const valor = await alta.locator('#enlace-actividad-0 option').nth(1).getAttribute('value');
      await alta.getByLabel('Actividad 1').selectOption(valor!);
      await alta.getByLabel('Medida').selectOption(medida);
      await alta.getByRole('button', { name: 'Guardar trazo' }).click();
      await expect(page.getByRole('status')).toContainText('Trazo guardado');
    };

    // --- Rectángulo: dos esquinas ---------------------------------------------------------------------
    const pRect = await planoNuevo('rect');
    await abrir(pRect.id);
    await barra.getByRole('button', { name: 'Rectángulo', exact: true }).click();
    await clic(0.3, 0.3);
    await clic(0.6, 0.55); // la forma se cierra con el segundo clic
    await guardar('Guardar polígono', 'area');
    const rect = (await trazosDe(pRect.id))[0]!;
    const anilloR = (rect.geometry.coordinates as [number, number][][])[0]!;
    expect(anilloR).toHaveLength(5);
    const xs = anilloR.map((c) => c[0]);
    const ys = anilloR.map((c) => c[1]);
    expect(area(anilloR)).toBeCloseTo((Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys)), 6);

    // --- Círculo: centro y un punto del borde ------------------------------------------------------------
    const pCirc = await planoNuevo('circ');
    await abrir(pCirc.id);
    await barra.getByRole('button', { name: 'Círculo', exact: true }).click();
    await clic(0.5, 0.5);
    await page.mouse.move((await en(0.6, 0.5)).x, (await en(0.6, 0.5)).y);
    await expect(page.getByTestId('previa')).toBeVisible(); // la forma se ve antes del segundo clic
    await clic(0.6, 0.5);
    await guardar('Guardar polígono', 'area');
    const circ = (await trazosDe(pCirc.id))[0]!;
    const anilloC = (circ.geometry.coordinates as [number, number][][])[0]!;
    expect(anilloC.length).toBeGreaterThan(100);
    const radio = (Math.max(...anilloC.map((c) => c[0])) - Math.min(...anilloC.map((c) => c[0]))) / 2;
    expect(area(anilloC) / (Math.PI * radio * radio)).toBeGreaterThan(0.999);
    expect(area(anilloC)).toBeLessThan(Math.PI * radio * radio);

    // --- Elipse: centro, extremo de un eje y un punto del otro ------------------------------------------
    const pEli = await planoNuevo('eli');
    await abrir(pEli.id);
    await barra.getByRole('button', { name: 'Elipse', exact: true }).click();
    await clic(0.5, 0.5);
    await clic(0.7, 0.5);
    await clic(0.5, 0.65);
    await guardar('Guardar polígono', 'area');
    const eli = (await trazosDe(pEli.id))[0]!;
    const anilloE = (eli.geometry.coordinates as [number, number][][])[0]!;
    const a = (Math.max(...anilloE.map((c) => c[0])) - Math.min(...anilloE.map((c) => c[0]))) / 2;
    const b = (Math.max(...anilloE.map((c) => c[1])) - Math.min(...anilloE.map((c) => c[1]))) / 2;
    expect(a).toBeGreaterThan(b); // el eje largo es el horizontal
    expect(area(anilloE) / (Math.PI * a * b)).toBeGreaterThan(0.999);

    // --- Arco: inicio, un punto del arco y final ----------------------------------------------------------
    const pArc = await planoNuevo('arc');
    await abrir(pArc.id);
    await barra.getByRole('button', { name: 'Arco', exact: true }).click();
    await clic(0.3, 0.85);
    await clic(0.5, 0.55);
    await clic(0.7, 0.85);
    await guardar('Guardar línea', 'longitud');
    const arc = (await trazosDe(pArc.id))[0]!;
    expect(arc.geometry.type).toBe('LineString');
    const pts = arc.geometry.coordinates as [number, number][];
    expect(pts.length).toBeGreaterThan(8);
    const cuerda = Math.hypot(pts.at(-1)![0] - pts[0]![0], pts.at(-1)![1] - pts[0]![1]);
    const largoArco = pts.slice(1).reduce((s, p, i) => s + Math.hypot(p[0] - pts[i]![0], p[1] - pts[i]![1]), 0);
    expect(largoArco).toBeGreaterThan(cuerda * 1.05); // el arco es más largo que la cuerda

    // --- Polilínea con ortogonal: por defecto a 90°; Mayús lo invierte; el ángulo es editable -------------
    const pPol = await planoNuevo('pol');
    await abrir(pPol.id);
    await barra.getByRole('button', { name: 'Polilínea', exact: true }).click();
    const orto = page.getByRole('button', { name: /^ORTO/ });
    await expect(orto).toHaveAttribute('aria-pressed', 'true');
    await expect(orto).toContainText('90°');
    await clic(0.3, 0.55);
    await clic(0.6, 0.59); // casi horizontal: sale horizontal
    await clic(0.64, 0.85); // casi vertical: sale vertical
    await page.keyboard.down('Shift'); // Mayús invierte el ortogonal: ahora sí queda libre
    await clic(0.4, 0.92);
    await page.keyboard.up('Shift');
    await page.keyboard.press('Enter');
    await guardar('Guardar línea', 'longitud');
    const pol = (await trazosDe(pPol.id))[0]!;
    const v = pol.geometry.coordinates as [number, number][];
    expect(v).toHaveLength(4);
    expect(v[1]![1]).toBeCloseTo(v[0]![1], 6); // tramo 1: horizontal
    expect(v[2]![0]).toBeCloseTo(v[1]![0], 6); // tramo 2: vertical
    expect(v[3]![0]).not.toBeCloseTo(v[2]![0], 1); // tramo 3 (con Mayús): libre, ni vertical ni horizontal
    expect(v[3]![1]).not.toBeCloseTo(v[2]![1], 1);

    // El ángulo de trabajo se edita en las ayudas de dibujo: a 45° las diagonales también salen exactas.
    const pDiag = await planoNuevo('diag');
    await abrir(pDiag.id);
    await barra.getByRole('button', { name: 'Polilínea', exact: true }).click();
    await page.getByRole('button', { name: 'Ayudas de dibujo' }).click();
    const ayudas = page.getByRole('region', { name: 'Ayudas de dibujo' });
    await ayudas.getByRole('button', { name: '45°' }).click();
    await expect(orto).toContainText('45°');
    await page.getByRole('button', { name: 'Ayudas de dibujo' }).click(); // se cierra
    await clic(0.3, 0.55);
    await clic(0.55, 0.77); // más o menos a 40°: sale a 45° exactos
    await page.keyboard.press('Enter');
    await guardar('Guardar línea', 'longitud');
    const diag = (await trazosDe(pDiag.id))[0]!.geometry.coordinates as [number, number][];
    expect(Math.abs(diag[1]![0] - diag[0]![0])).toBeCloseTo(Math.abs(diag[1]![1] - diag[0]![1]), 6);

    // Apagado, deja el trazo libre.
    await orto.click();
    await expect(orto).toHaveAttribute('aria-pressed', 'false');
  });

  test('referencia a objetos: el cursor se pega al extremo de lo que ya hay', async ({ page, request }) => {
    const clave = `REF-${Date.now().toString(36).toUpperCase()}`;
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
    const actividades = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'ref',
      archivo_url: 'planos/ref.dwg',
    });
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: 'POLYGON((0 0, 100 0, 100 60, 0 60, 0 0))',
      enlaces: [{ actividad_id: actividades[0]!.id, medida: 'area', factor: '1' }],
    });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await expect(page.locator('.visor__trazo')).toHaveCount(1);
    const caja = (await page.locator('.visor__trazo path').first().boundingBox())!;
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    await barra.getByRole('button', { name: 'Polilínea', exact: true }).click();

    // Cerca de la esquina superior derecha: aparece la marca de extremo y el clic cae exacto en (100, 0).
    await page.mouse.move(caja.x + caja.width - 4, caja.y + 5);
    await expect(page.getByTestId('referencia')).toHaveAttribute('data-tipo', 'extremo');
    await page.mouse.click(caja.x + caja.width - 4, caja.y + 5);
    // La esquina de abajo, igual: la línea nace y termina exacta en dos vértices del área.
    await page.mouse.move(caja.x + caja.width - 5, caja.y + caja.height - 4);
    await expect(page.getByTestId('referencia')).toHaveAttribute('data-tipo', 'extremo');
    await page.mouse.click(caja.x + caja.width - 5, caja.y + caja.height - 4);
    await page.keyboard.press('Enter');
    const alta = page.getByRole('dialog', { name: 'Guardar línea' });
    const valor = await alta.locator('#enlace-actividad-0 option').nth(1).getAttribute('value');
    await alta.getByLabel('Actividad 1').selectOption(valor!);
    await alta.getByRole('button', { name: 'Guardar trazo' }).click();
    await expect(page.getByRole('status')).toContainText('Trazo guardado');
    const lineas = (
      await llamarApi<{ features: Feature[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)
    ).features.filter((f) => f.geometry.type === 'LineString');
    expect(lineas[0]!.geometry.coordinates).toEqual([
      [100, 0],
      [100, 60],
    ]);

    // Apagada la referencia, el mismo clic ya no se pega.
    await page.getByRole('button', { name: 'REF', exact: true }).click();
    await page.mouse.move(caja.x + caja.width - 4, caja.y + 5);
    await expect(page.getByTestId('referencia')).toHaveCount(0);
    await expect(lienzo).toBeVisible();
  });
});
