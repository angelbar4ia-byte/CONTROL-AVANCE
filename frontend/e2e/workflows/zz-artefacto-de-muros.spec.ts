import { cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, pulsarMarca, test } from '../infraestructura';

/**
 * Artefacto (Ola 4A): la plantilla de muro (tipo, material, ubicación con caras A y B, partes de altura y elementos) se crea en la
 * pestaña Artefacto con su vista previa, nace «por validar», solo Control de obra la valida contra la matriz, el Cuantificador la
 * elige para un trazo y, al cambiarla ya validada, nace una versión nueva y el trazo conserva la anterior (Q9).
 */

const ROLES_ZZ = ['control', 'costos'] as const;

interface Plantilla {
  id: string;
  version: number;
  validacion: string;
  vigente: boolean;
}

test.describe('Cuantificador · Artefacto de muros', () => {
  test.skip(!hayRoles(...ROLES_ZZ), motivoSinRoles(...ROLES_ZZ));
  test.setTimeout(150_000);

  test('una plantilla nace por validar, Control la valida, un trazo la elige y al cambiarla nace la versión 2', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const n = Math.floor(Math.random() * 900) + 100; // medidas propias: dos elementos iguales chocan con la firma anti-duplicados
    const castillo = `KA${sufijo}`;
    const cadena = `CA${sufijo}`;
    await llamarApi(request, 'control', 'POST', '/elementos-parametricos', {
      clave: castillo, nombre: `Castillo ${castillo}`, tipo: 'castillo', parametros: { largo: 0.15 + n / 10000, ancho: 0.15 },
    });
    await llamarApi(request, 'control', 'POST', '/elementos-parametricos', {
      clave: cadena, nombre: `Cadena ${cadena}`, tipo: 'lineal', categoria: 'cadenas', subcategoria: 'cerramiento',
      parametros: { ancho: 0.15 + n / 10000, alto: 0.2 },
    });
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `ART-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Artefacto',
      archivo_url: 'planos/artefacto.dwg',
    });
    const muro = (
      await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
        version_plano: 1, fuente: 'pdf', geometria_wkt: 'LINESTRING(0 0, 10 0)', grosor_m: '0.15', alineacion: 'centro',
        enlaces: [{ medida: 'longitud', factor: '1', actividad_id: actividad!.id }],
      })
    ).trazo_id;
    const nombre = `Fachada ${sufijo}`;

    await page.setViewportSize({ width: 1400, height: 1100 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const pestanas = page.getByRole('tablist', { name: 'Panel lateral' });
    await pestanas.getByRole('tab', { name: /^Artefacto/ }).click();
    const area = page.getByRole('region', { name: 'Artefacto', exact: true });

    // --- 1. Una plantilla nueva: tipo con cadena, partes de altura y los elementos ----------------------------------------
    await page.getByRole('button', { name: '+ Nueva plantilla' }).click();
    await area.getByLabel('Nombre de la plantilla').fill(nombre);
    await expect(area.getByRole('group', { name: 'Tipo de muro de la plantilla' }).getByRole('button', { name: 'Muro con cadena' })).toHaveAttribute('aria-pressed', 'true');
    await area.getByRole('button', { name: '+ Parte de altura' }).click();
    await area.getByLabel('Nombre de la parte 1').fill('Cuerpo');
    await area.getByLabel('Hasta de la parte 1').fill('2.3');
    await area.getByLabel('Rol de la parte 1').selectOption('cuerpo');
    await area.getByRole('button', { name: '+ Parte de altura' }).click();
    await area.getByLabel('Nombre de la parte 2').fill('Enrase');
    await area.getByLabel('Hasta de la parte 2').fill('2.6');
    await area.getByLabel('Rol de la parte 2').selectOption('enrase');
    await expect(area.getByLabel('Desde de la parte 2')).toHaveValue('2.3'); // la parte nueva sigue donde acaba la última

    // La ubicación fija las caras de todas las partes (las calcula el servidor); el enrase interior sale exterior.
    await area.getByLabel('Ubicación de la plantilla').selectOption('interior');
    await expect(area.getByLabel('Cara A de la parte 1')).toHaveValue('interior');
    await expect(area.getByLabel('Cara A de la parte 2')).toHaveValue('exterior');
    await area.getByLabel('Ubicación de la plantilla').selectOption('fachada_a');
    await expect(area.getByLabel('Cara A de la parte 1')).toHaveValue('exterior');
    await expect(area.getByLabel('Cara B de la parte 1')).toHaveValue('interior');
    // Cambiar la cara de una parte vuelve personalizada la ubicación.
    await area.getByLabel('Cara B de la parte 2').selectOption('exterior');
    await expect(area.getByLabel('Ubicación de la plantilla')).toHaveValue('personalizada');
    await area.getByLabel('Ubicación de la plantilla').selectOption('fachada_a');

    await area.getByLabel('Agregar un elemento a la plantilla').selectOption(castillo);
    await area.getByLabel('Agregar un elemento a la plantilla').selectOption(cadena);
    await expect(area.getByRole('list', { name: 'Elementos de la plantilla' }).getByRole('listitem')).toHaveCount(2);
    await area.getByLabel(`Posición de ${cadena}`).selectOption('remate');

    // La vista previa dibuja los castillos (ubicados, por ser con cadena) y la cadena.
    await expect(area.getByRole('img', { name: 'Vista previa de la plantilla de muro' })).toBeVisible();
    await expect(area.locator(`[data-castillo="${castillo}"]`)).toHaveCount(3);
    await expect(area.locator(`[data-cadena="${cadena}"]`)).toHaveCount(1);

    // --- 2. Se crea: nace por validar -------------------------------------------------------------------------------------
    await area.getByRole('button', { name: 'Crear plantilla' }).click();
    await expect(area.getByText('Plantilla creada: queda por validar.')).toBeVisible();
    await expect(area.locator('[data-validacion="por_validar"]')).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Plantillas de muro' }).getByRole('button', { name: new RegExp(nombre) })).toBeVisible();
    const lista = async () => llamarApi<Plantilla[]>(request, 'control', 'GET', '/muro-plantillas');
    const creada = (await llamarApi<(Plantilla & { nombre: string })[]>(request, 'control', 'GET', '/muro-plantillas')).find((p) => p.nombre === nombre)!;
    expect([creada.version, creada.validacion]).toEqual([1, 'por_validar']);

    // --- 3. Control de obra la valida contra la matriz (los elementos no tienen conceptos: alertas por revisar) ------------
    const validacion = area.getByRole('group', { name: 'Validación contra la matriz' });
    await expect(validacion.getByRole('list', { name: 'Alertas de la plantilla' })).toBeVisible();
    await expect(validacion.locator(`[data-codigo="sin_concepto"]`).first()).toBeVisible();
    const validar = validacion.getByRole('button', { name: 'Validar la plantilla' });
    await expect(validar).toBeDisabled(); // hay alertas por revisar: hay que aceptarlas
    await validacion.getByLabel('Acepto las alertas por revisar').check();
    await validar.click();
    await expect(area.getByText('Plantilla validada.')).toBeVisible();
    await expect(area.locator('[data-validacion="validada"]')).toBeVisible();

    // --- 4. El Cuantificador elige la plantilla para el trazo ---------------------------------------------------------------
    await pestanas.getByRole('tab', { name: /^Trazos/ }).click();
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await cajaEstable(page, lienzo);
    await pulsarMarca(page, page.locator('.visor__trazo').first());
    // El muro aún no tiene tipo: se clasifica y entonces aparecen su material, su ubicación y su plantilla.
    await page.getByRole('group', { name: 'Tipo de muro' }).last().getByRole('button', { name: 'Confinado' }).click();
    await page.getByLabel('Plantilla de muro', { exact: true }).selectOption(creada.id);
    const clasificacion = async () =>
      llamarApi<{ tipo: string; material: string; ubicacion: string; plantilla_id: string | null }>(
        request, 'control', 'GET', `/trazos/${muro}/muro/clasificacion`,
      );
    await expect.poll(async () => (await clasificacion()).plantilla_id).toBe(creada.id);
    expect(await clasificacion()).toMatchObject({ tipo: 'con_cadena', material: 'tabique_rojo', ubicacion: 'fachada_a' });
    // El castillo se coloca porque la plantilla del muro lleva un castillo ubicado.
    await llamarApi(request, 'control', 'POST', `/trazos/${muro}/vanos`, { clave: 'K-01', tipo: 'castillo', ancho_m: '0.15', alto_m: '1', posicion_m: '3' });

    // --- 5. Cambiar la plantilla validada: nace la versión 2 y el trazo conserva la 1 ------------------------------------------
    await pestanas.getByRole('tab', { name: /^Artefacto/ }).click();
    await page.getByRole('navigation', { name: 'Plantillas de muro' }).getByRole('button', { name: new RegExp(nombre) }).click();
    await area.getByLabel('Altura de la plantilla (m)').fill('3');
    await area.getByRole('button', { name: 'Guardar cambios' }).click();
    await expect(area.getByText(/Nació la versión 2/)).toBeVisible();
    await expect(area.locator('[data-validacion="por_validar"]')).toBeVisible();
    await expect(area.getByRole('list', { name: 'Versiones de la plantilla' }).getByRole('listitem')).toHaveCount(2);
    const vigente = (await lista()).find((p) => p.vigente && p.version === 2)!;
    expect(vigente.id).not.toBe(creada.id);
    expect((await clasificacion()).plantilla_id).toBe(creada.id); // el trazo ya medido conserva la versión 1
  });

  test('Costos edita la plantilla pero no la valida', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const nombre = `Tabique ${sufijo}`;
    const creada = await llamarApi<{ id: string }>(request, 'control', 'POST', '/muro-plantillas', {
      nombre, tipo: 'tabique', material: 'tabique_rojo', ubicacion: 'interior',
    });
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `ARC-${sufijo}`,
    });
    await entrarComo(page, 'costos');
    await page.goto(`/cuantificador?obra=${obra.id}`);
    await page.getByRole('tablist', { name: 'Panel lateral' }).getByRole('tab', { name: /^Artefacto/ }).click();
    await page.getByRole('navigation', { name: 'Plantillas de muro' }).getByRole('button', { name: new RegExp(nombre) }).click();
    const area = page.getByRole('region', { name: 'Artefacto', exact: true });
    await expect(area.getByLabel('Nombre de la plantilla')).toHaveValue(nombre);
    await expect(area.getByLabel('Nombre de la plantilla')).toBeEnabled(); // Costos edita
    await expect(area.getByRole('button', { name: 'Validar la plantilla' })).toHaveCount(0); // pero no valida
    await expect(area.getByText('solo Control de obra la valida')).toBeVisible();
    // Un tabique no lleva castillos ni cadenas: el selector solo ofrece muros.
    const opciones = await area.getByLabel('Agregar un elemento a la plantilla').locator('option').allTextContents();
    expect(opciones.some((o) => /^EST-02010/.test(o))).toBe(true);
    expect(opciones.some((o) => o.includes('Castillo') || o.includes('Cadena'))).toBe(false);
    expect(creada.id).toBeTruthy();
  });
});
