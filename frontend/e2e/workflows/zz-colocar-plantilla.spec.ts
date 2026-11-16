import { cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, pulsarMarca, test } from '../infraestructura';

/**
 * Ola 4C · trazar un muro con plantilla coloca sus castillos: toman la altura del driver de la obra (no 2.6 m), restan de los m² del muro y
 * se pueden retirar y volver a colocar desde el detalle del trazo. Lo colocado ya no se mueve si el driver cambia (Q1).
 */

const ROLES_Z = ['control'] as const;

test.describe('Cuantificador · colocar la plantilla de un muro', () => {
  test.skip(!hayRoles(...ROLES_Z), motivoSinRoles(...ROLES_Z));
  test.setTimeout(120_000);

  test('un muro trazado con plantilla nace con sus castillos a la altura del driver', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `PLA-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Muro con plantilla',
      archivo_url: 'planos/plantilla.dwg',
    });
    // La altura estándar de ESTA obra: los castillos suben lo alto del muro, que nace con ella.
    await llamarApi(request, 'control', 'PUT', `/obras/${obra.id}/drivers/altura_estandar`, { valor: '2.8' });

    // Una plantilla con un castillo ubicado (los crea Control de obra: el elemento ya está autorizado).
    const clave = `K${sufijo}`;
    // El alto propio del elemento hace única su firma: la biblioteca rechaza un segundo castillo idéntico (409) y otros specs crean castillos.
    const altoDelElemento = 2.5 + (Date.now() % 100000) / 100000;
    await llamarApi(request, 'control', 'POST', '/elementos-parametricos', {
      clave,
      nombre: `Castillo ${clave}`,
      tipo: 'castillo',
      parametros: { alto: Number(altoDelElemento.toFixed(5)) },
    });
    const nombre = `Plantilla ${sufijo}`;
    await llamarApi(request, 'control', 'POST', '/muro-plantillas', {
      nombre,
      tipo: 'con_cadena',
      material: 'tabique_rojo',
      ubicacion: 'interior',
      partes: [{ nombre: 'Cuerpo', desde_m: '0', hasta_m: '2.8', rol: 'cuerpo' }],
      elementos: [{ ref: clave }],
    });

    type Trazo = { id: string; properties: { enlaces: { cantidad: string; vigente: boolean }[]; muro_plantilla_id?: string | null } };
    const trazos = async () => (await llamarApi<{ features: Trazo[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)).features;
    const vanos = async (id: string) =>
      llamarApi<{ tipo: string; alto_m: string; elemento_uid: string | null; posicion_m: string | null }[]>(request, 'control', 'GET', `/trazos/${id}/vanos`);
    const medida = async () => Number((await trazos())[0]!.properties.enlaces.find((e) => e.vigente)!.cantidad);

    await page.setViewportSize({ width: 1280, height: 1000 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = await cajaEstable(page, lienzo);

    // El muro nace con tipo «con cadena» y la plantilla elegida en el panel de la línea.
    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    await page.getByRole('button', { name: '0.15 m' }).click();
    await page.getByRole('group', { name: 'Tipo de muro' }).getByRole('button', { name: 'Con cadena' }).click();
    await expect(page.getByLabel('Altura (m)')).toHaveValue('2.8'); // el panel propone la altura del driver
    await page.getByLabel('Plantilla del muro nuevo').selectOption({ label: `${nombre} · v1 (por validar)` });
    await page.mouse.click(c.x + c.width * 0.55, c.y + c.height * 0.6);
    await page.mouse.click(c.x + c.width * 0.9, c.y + c.height * 0.6);
    await expect.poll(async () => (await trazos()).length).toBe(1);
    const muroId = (await trazos())[0]!.id;

    // Sus dos castillos (distribución «extremos») quedaron colocados: instancias de la plantilla, con la altura del driver.
    await expect.poll(async () => (await vanos(muroId)).length).toBe(2);
    const puestos = await vanos(muroId);
    expect(puestos.map((v) => v.tipo)).toEqual(['castillo', 'castillo']);
    expect(puestos.every((v) => v.elemento_uid === clave)).toBe(true);
    for (const v of puestos) expect(Number(v.alto_m)).toBeCloseTo(2.8, 3);
    expect(Number(puestos[0]!.posicion_m)).toBeLessThan(Number(puestos[1]!.posicion_m));
    const conCastillos = await medida();

    // En el detalle: lo que coloca la plantilla, con su altura y el aviso de lo que no cuenta (aquí ningún concepto lo paga aún).
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    await pulsarMarca(page, page.locator('.visor__trazo').first());
    const region = page.getByRole('region', { name: 'Elementos de la plantilla' });
    await expect(region).toBeVisible();
    await expect(region.getByTestId('contexto-de-colocacion')).toContainText('2.80 m de alto');
    await expect(region.locator(`[data-elemento="${clave}"]`)).toContainText('colocados 2 de 2');

    // Retirar vuelve a medir lo que medía sin castillos; colocar de nuevo los pone (sin duplicarlos).
    await region.getByRole('button', { name: 'Retirar lo colocado' }).click();
    await expect.poll(async () => (await vanos(muroId)).length).toBe(0);
    expect(await medida()).toBeGreaterThan(conCastillos);
    await region.getByRole('button', { name: 'Colocar los elementos de la plantilla' }).click();
    await expect.poll(async () => (await vanos(muroId)).length).toBe(2);
    expect(await medida()).toBeCloseTo(conCastillos, 4);

    // Q1: el driver cambia después y lo ya colocado conserva su altura.
    await llamarApi(request, 'control', 'PUT', `/obras/${obra.id}/drivers/altura_estandar`, { valor: '3.5' });
    for (const v of await vanos(muroId)) expect(Number(v.alto_m)).toBeCloseTo(2.8, 3);
    expect(await medida()).toBeCloseTo(conCastillos, 4);
  });
});
