import { cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, pulsarMarca, test } from '../infraestructura';

/**
 * Plantilla 2 «muros y cadena» (con plano estructural): el muro y las cadenas, y los castillos reales se siembran uno por uno, cada uno
 * de su tipo K del catálogo. Un trazo pasa de la plantilla 1 (muro confinado, que propone los castillos) a la 2 y viceversa sin perder lo
 * medido, y antes de cambiar se dice qué cambia.
 */

const ROLES_ZZ = ['control'] as const;

interface Elemento {
  clave: string;
}
interface Vano {
  id: string;
  tipo: string;
  elemento_uid: string | null;
  alto_m: string;
}

test.describe('Cuantificador · muros y cadena', () => {
  test.skip(!hayRoles(...ROLES_ZZ), motivoSinRoles(...ROLES_ZZ));
  test.setTimeout(180_000);

  test('un castillo a mano elige su K y el muro cambia de la plantilla 1 a la 2 y de vuelta sin perder lo medido', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const existentes = new Set((await llamarApi<Elemento[]>(request, 'control', 'GET', '/elementos-parametricos')).map((e) => e.clave));
    const crear = async (clave: string, cuerpo: Record<string, unknown>) => {
      if (existentes.has(clave)) return;
      try {
        await llamarApi(request, 'control', 'POST', '/elementos-parametricos', { clave, nombre: `Elemento ${clave}`, ...cuerpo });
      } catch (e) {
        // Otra corrida lo creó a la vez: basta con que ya exista.
        const ahora = await llamarApi<Elemento[]>(request, 'control', 'GET', '/elementos-parametricos');
        if (!ahora.some((x) => x.clave === clave)) throw e;
      }
    };
    for (const [n, k] of ['K-1', 'K-2', 'K-3', 'K-6', 'K-7'].entries()) {
      await crear(k, { tipo: 'castillo', parametros: { largo: 0.4 + n / 1000, ancho: 0.15 } });
    }
    for (const [n, k] of ['CE-1', 'CE-2'].entries()) {
      await crear(k, { tipo: 'lineal', categoria: 'cadenas', subcategoria: 'cerramiento', parametros: { ancho: 0.4 + n / 1000, alto: 0.2 } });
    }
    const partes = [{ nombre: 'Cuerpo', desde_m: '0', hasta_m: '3', rol: 'cuerpo' }];
    const nombre1 = `Confinado ${sufijo}`;
    const nombre2 = `Muros y cadena ${sufijo}`;
    const p1 = await llamarApi<{ id: string }>(request, 'control', 'POST', '/muro-plantillas', {
      nombre: nombre1, tipo: 'confinado', material: 'tabique_rojo', ubicacion: 'interior', partes,
      elementos: [{ ref: 'K-1', regla: 'por_ml', piezas_por_ml: '0.4' }, { ref: 'CE-1' }],
    });
    const p2 = await llamarApi<{ id: string }>(request, 'control', 'POST', '/muro-plantillas', {
      nombre: nombre2, tipo: 'con_cadena', material: 'tabique_rojo', ubicacion: 'interior', partes, elementos: [{ ref: 'CE-1' }],
    });

    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `MYC-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Muros y cadena',
      archivo_url: 'planos/muros-y-cadena.dwg',
    });
    await llamarApi(request, 'control', 'PUT', `/obras/${obra.id}/drivers/altura_estandar`, { valor: '3' });
    const muro = (
      await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
        version_plano: 1, fuente: 'pdf', geometria_wkt: 'LINESTRING(0 0, 10 0)', grosor_m: '0.15', alineacion: 'centro',
        enlaces: [{ medida: 'longitud', factor: '1', actividad_id: actividad!.id, conversion: { modo: 'area', mide: 'eje' } }],
      })
    ).trazo_id;
    await llamarApi(request, 'control', 'PUT', `/trazos/${muro}/muro/plantilla`, { plantilla_id: p1.id });
    const clasificacion = async () => llamarApi<{ plantilla_id: string | null; tipo: string }>(request, 'control', 'GET', `/trazos/${muro}/muro/clasificacion`);
    const vanos = async () => llamarApi<Vano[]>(request, 'control', 'GET', `/trazos/${muro}/vanos`);
    const medida = async () => {
      const trazos = await llamarApi<{ features: { id: string; properties: { enlaces: { cantidad: string; vigente: boolean }[] } }[] }>(
        request, 'control', 'GET', `/planos/${plano.id}/trazos`,
      );
      return Number(trazos.features.find((f) => f.id === muro)!.properties.enlaces.find((e) => e.vigente)!.cantidad);
    };
    const m0 = await medida();
    expect(m0).toBeCloseTo(30, 3); // 10 m × 3.00 m

    await page.setViewportSize({ width: 1400, height: 1100 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await cajaEstable(page, lienzo);
    await pulsarMarca(page, page.locator('.visor__trazo').first());
    const selector = page.getByLabel('Plantilla de muro', { exact: true });
    await expect(selector).toHaveValue(p1.id);

    // --- 1. De la plantilla 1 a la 2: dice qué cambia; cancelar no cambia nada -----------------------------------------------------
    await selector.selectOption(p2.id);
    const cambio = page.getByRole('region', { name: 'Cambiar de plantilla' });
    await expect(cambio).toBeVisible();
    await expect(cambio.locator('[data-cambia="tipo"]')).toContainText('confinado');
    await expect(cambio.locator('[data-cambia="tipo"]')).toContainText('con_cadena');
    await expect(cambio.locator('[data-elemento="K-1"]')).toHaveAttribute('data-efecto', 'deja');
    await expect(cambio.locator('[data-elemento="CE-1"]')).toHaveAttribute('data-efecto', 'sigue');
    await expect(cambio).toContainText('uno por uno');
    await expect(cambio).toContainText('medición del muro');
    await cambio.getByRole('button', { name: 'Cancelar' }).click();
    await expect(cambio).toHaveCount(0);
    expect((await clasificacion()).plantilla_id).toBe(p1.id);

    await selector.selectOption(p2.id);
    await cambio.getByRole('button', { name: 'Cambiar de plantilla' }).click();
    await expect.poll(async () => (await clasificacion()).plantilla_id).toBe(p2.id);
    expect((await clasificacion()).tipo).toBe('con_cadena');
    expect(await medida()).toBeCloseTo(m0, 3); // lo medido no se pierde
    await expect(page.getByTestId('aviso-de-castillos-a-mano')).toBeVisible();

    // --- 2. Cada castillo a mano elige su K del catálogo --------------------------------------------------------------------------
    const alta = page.getByRole('group', { name: 'Colocar un vano' });
    await alta.getByLabel('Tipo de vano').selectOption('castillo');
    await alta.getByLabel('Castillo que se coloca (tipo K)').selectOption('K-2');
    await alta.getByRole('button', { name: 'Colocar', exact: true }).click();
    await expect.poll(async () => (await vanos()).length).toBe(1);
    await alta.getByLabel('Castillo que se coloca (tipo K)').selectOption('K-3');
    await alta.getByRole('button', { name: 'Colocar', exact: true }).click();
    await expect.poll(async () => (await vanos()).length).toBe(2);
    const sembrados = await vanos();
    expect(sembrados.map((v) => [v.tipo, v.elemento_uid]).sort()).toEqual([['castillo', 'K-2'], ['castillo', 'K-3']]);
    for (const v of sembrados) expect(Number(v.alto_m)).toBeCloseTo(3, 3); // suben lo alto del muro (el driver)
    const conCastillos = await medida();
    expect(conCastillos).toBeLessThan(m0); // resta de los m² del muro

    // --- 3. De vuelta a la plantilla 1: avisa de los castillos sembrados; sin retirarlos se conservan ---------------------------
    await selector.selectOption(p1.id);
    await expect(cambio.getByTestId('castillos-sembrados')).toContainText('2 castillos ya sembrados');
    await expect(cambio).toContainText('dos veces');
    await expect(cambio.locator('[data-elemento="K-1"]')).toHaveAttribute('data-efecto', 'nuevo');
    await cambio.getByRole('button', { name: 'Cambiar de plantilla' }).click();
    await expect.poll(async () => (await clasificacion()).plantilla_id).toBe(p1.id);
    expect(await vanos()).toHaveLength(2);
    expect(await medida()).toBeCloseTo(conCastillos, 3);

    // --- 4. Pasar otra vez a la 2 y de nuevo a la 1 retirando los sembrados: el muro recupera lo suyo ------------------------------
    await selector.selectOption(p2.id);
    await cambio.getByRole('button', { name: 'Cambiar de plantilla' }).click();
    await expect.poll(async () => (await clasificacion()).plantilla_id).toBe(p2.id);
    await selector.selectOption(p1.id);
    await cambio.getByLabel('Retirar los castillos sembrados al cambiar').check();
    await cambio.getByRole('button', { name: 'Cambiar de plantilla' }).click();
    await expect.poll(async () => (await vanos()).length).toBe(0);
    expect((await clasificacion()).plantilla_id).toBe(p1.id);
    expect(await medida()).toBeCloseTo(m0, 3);
  });
});
