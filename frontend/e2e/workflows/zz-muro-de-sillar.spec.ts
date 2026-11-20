import { altoPropio, cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, pulsarMarca, test } from '../infraestructura';

/**
 * Muro de sillar amarillo de 19 cm, BAP-01010 (decisión del usuario 2026-11-20: realizar el elemento).
 *
 *  1. La biblioteca trae Muros › Muros de sillar con BAP-01010 y el tabique sigue donde estaba.
 *  2. La tarjeta calcula con la pieza 19×25×45 (8.27 pza y 0.0226 m³ por m² con 2 cm de junta y 5 %), se liga al concepto del catálogo (sin
 *     concepto nuevo ni precios), muestra el destajo MOE-02016 y concilia contra los 9 pza y 0.0292 m³ del catálogo (≠, sin editarlo).
 *  3. F6: el desperdicio sale del driver `desperdicio_mamposteria` de la obra (10 % → 8.67 pza) y lo que se teclea manda sobre el driver; el
 *     tabique de 14 cm no lo lee.
 *  4. Costos propone la nueva versión de BAP-01010 y no autoriza; Control de obra autoriza y nace la versión.
 *  5. Una plantilla de muro con material sillar amarillo ya no avisa «material sin elemento»: toma BAP-01010 como mampostería implícita, se
 *     valida con casilla y un trazo la elige.
 */

const ROLES = ['control', 'costos'] as const;

test.describe('Cuantificador · muro de sillar amarillo BAP-01010', () => {
  test.skip(!hayRoles(...ROLES), motivoSinRoles(...ROLES));
  test.setTimeout(180_000);

  test('la tarjeta calcula, concilia, lee el driver de desperdicio y Costos propone lo que Control autoriza', async ({ page, browser, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `SIL-${sufijo}`,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Muro de sillar',
      archivo_url: 'planos/muro-de-sillar.dwg',
    });
    const url = `/cuantificador?obra=${obra.id}&plano=${plano.id}`;
    await page.setViewportSize({ width: 1400, height: 1100 });
    await entrarComo(page, 'control');
    await page.goto(url);
    const pestanas = page.getByRole('tablist', { name: 'Panel lateral' });
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();
    const biblioteca = page.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    const area = page.getByRole('region', { name: 'Elementos', exact: true });

    // --- 1. La biblioteca ---------------------------------------------------------------------------------------------
    await expect(biblioteca.getByRole('button', { name: /Muros de sillar/ })).toBeVisible();
    await expect(biblioteca.getByRole('button', { name: /Muros de tabique/ })).toBeVisible();
    await expect(biblioteca.getByRole('button', { name: /^BAP-01010\b/ })).toBeVisible();
    await expect(biblioteca.getByRole('button', { name: /^EST-02010\b/ })).toBeVisible();

    // --- 2. La tarjeta: pieza real, concepto del catálogo y conciliación -----------------------------------------------------
    await biblioteca.getByRole('button', { name: /^BAP-01010\b/ }).click();
    const muro = area.getByRole('article', { name: /BAP-01010/ });
    await expect(muro.getByTestId('sillar-piezas')).toContainText('8.27 pza');
    await expect(muro.getByTestId('sillar-mezcla')).toContainText('0.0226 m³');
    await expect(muro.getByTestId('sillar-espesor')).toContainText('19.0 cm');
    await expect(muro.getByTestId('sillar-mano-de-obra')).toContainText('MOE-02016');
    await expect(muro.getByTestId('sillar-concepto')).toContainText('BAP-01010 · del catálogo');
    await expect(muro.getByRole('region', { name: 'Concepto que lo paga' })).toHaveAttribute('data-concepto-elegido', 'BAP-01010');
    await expect(muro.getByRole('region', { name: 'Concepto que lo paga' })).toContainText('Matriz del catálogo');
    await expect(muro.getByTestId('tabique-planta')).toBeVisible();
    const conciliacion = muro.locator('[data-conciliacion="BAP-01010"]');
    await expect(conciliacion.locator('tr[data-insumo="PET-00008"]')).toContainText('9.0000');
    await expect(conciliacion.locator('tr[data-insumo="MEZ-07010"]')).toContainText('0.0292');
    await expect(conciliacion.locator('tr[data-marca="≠"]')).toHaveCount(2);
    await expect(muro.getByRole('list', { name: 'Advertencias' })).toContainText('9 pza');
    await muro.getByLabel('Cantidad', { exact: true }).fill('100');
    await expect(muro.getByTestId('sillar-total')).toContainText('827.4 pza (828 a comprar)');

    // --- 3. F6: el desperdicio sale del driver de la obra y lo tecleado manda --------------------------------------------------
    const usado = muro.locator('[data-driver-usado="desperdicio_mamposteria"]');
    await expect(usado).toHaveAttribute('data-fuente', 'defecto');
    await llamarApi(request, 'control', 'PUT', `/obras/${obra.id}/drivers/desperdicio_mamposteria`, { valor: '10' });
    await page.reload();
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    await biblioteca.getByRole('button', { name: /^BAP-01010\b/ }).click();
    await expect(usado).toHaveAttribute('data-fuente', 'obra');
    await expect(muro.getByTestId('sillar-piezas')).toContainText('8.67 pza'); // 7.88 pza netas con 10 %
    await muro.getByLabel('Desperdicio de mampostería').fill('5');
    await expect(muro.getByTestId('sillar-piezas')).toContainText('8.27 pza');
    await expect(usado).toHaveAttribute('data-fuente', 'peticion');
    // Con la junta y el desperdicio que implica el catálogo el elemento coincide: no hay nada que proponer.
    await muro.getByLabel('Junta en centímetros').fill('2.4');
    await muro.getByLabel('Desperdicio de mampostería').fill('16.6');
    await expect(conciliacion.locator('tr[data-marca="="]')).toHaveCount(2);
    await expect(muro.getByRole('button', { name: /Confirmar cálculo/ })).toBeDisabled();
    // El tabique de 14 cm no lee el driver de la obra: sigue en 50.0 pza.
    await biblioteca.getByRole('button', { name: /^EST-02010\b/ }).click();
    await expect(area.getByRole('article', { name: /EST-02010/ }).getByTestId('tabique-piezas')).toContainText('50.0 pza');
    await biblioteca.getByRole('button', { name: /^BAP-01010\b/ }).click();

    // --- 4. Costos propone, Control de obra autoriza -------------------------------------------------------------------------------
    // La propuesta es del concepto BAP-01010 de toda la organización: en una base ya usada (segunda corrida) ya hay una vigente y proponer es
    // idempotente; en una base limpia (CI) se recorre el ciclo completo.
    const previas = await llamarApi<{ estado: string }[]>(request, 'control', 'GET', '/biblioteca-de-elementos/sillar/BAP-01010/propuestas');
    const yaHayVigente = previas.some((p) => p.estado !== 'rechazada');
    const costos = await browser.newPage();
    await entrarComo(costos, 'costos');
    await costos.goto(url);
    await costos.getByRole('tablist', { name: 'Panel lateral' }).getByRole('tab', { name: /^Elementos/ }).click();
    const bibCostos = costos.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await bibCostos.getByRole('button', { name: 'Expandir todo' }).click();
    await bibCostos.getByRole('button', { name: /^BAP-01010\b/ }).click();
    const sillarCostos = costos.getByRole('region', { name: 'Elementos', exact: true }).getByRole('article', { name: /BAP-01010/ });
    await expect(sillarCostos.getByRole('button', { name: 'Autorizar' })).toHaveCount(0);
    await expect(sillarCostos.getByRole('button', { name: /concepto nuevo/i })).toHaveCount(0); // el concepto ya está en el catálogo (F7)
    await sillarCostos.getByRole('button', { name: /Confirmar cálculo/ }).click();
    if (yaHayVigente) {
      await expect(sillarCostos.getByTestId('sillar-aviso')).toContainText('ya hay una vigente');
    } else {
      await expect(sillarCostos.getByTestId('sillar-aviso')).toContainText('espera la autorización de Control de obra');
      await expect(sillarCostos.locator('[data-propuesta="BAP-01010"]')).toContainText('Pendiente');
      await expect(sillarCostos.locator('[data-propuesta="BAP-01010"]')).toContainText('PET-00008');
    }
    await costos.close();

    await page.reload();
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    await biblioteca.getByRole('button', { name: /^BAP-01010\b/ }).click();
    const propuesta = muro.locator('[data-propuesta="BAP-01010"]').first();
    if (!yaHayVigente) {
      await propuesta.getByRole('button', { name: 'Autorizar' }).click();
    }
    await expect(propuesta).toContainText(/Autorizada · versión \d+/);
  });

  test('una plantilla de sillar amarillo ya no avisa «sin elemento»: toma BAP-01010, se valida y un trazo la elige', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const castillo = `KS${sufijo}`;
    // El alto propio hace única la firma del castillo (la biblioteca rechaza un segundo castillo idéntico).
    await llamarApi(request, 'control', 'POST', '/elementos-parametricos', {
      clave: castillo, nombre: `Castillo ${castillo}`, tipo: 'castillo', parametros: { alto: Number(altoPropio(7).toFixed(5)) },
    });
    const elementos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/elementos-parametricos');
    await llamarApi(request, 'control', 'POST', `/elementos-parametricos/${elementos.find((e) => e.clave === castillo)!.id}/conceptos-por-contexto`, {
      clave_propuesta: `EJS${sufijo}`.slice(0, 20), descripcion: `Concepto de ${castillo}`, unidad: 'pza', toma: { concreto: true, acero: true, cimbra: true },
    });
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `SIP-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Barda de sillar',
      archivo_url: 'planos/barda-de-sillar.dwg',
    });
    const muro = (
      await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
        version_plano: 1, fuente: 'pdf', geometria_wkt: 'LINESTRING(0 0, 10 0)', grosor_m: '0.19', alineacion: 'centro',
        enlaces: [{ medida: 'longitud', factor: '1', actividad_id: actividad!.id }],
      })
    ).trazo_id;
    const nombre = `Barda de sillar ${sufijo}`;
    const plantilla = await llamarApi<{ id: string }>(request, 'control', 'POST', '/muro-plantillas', {
      nombre, tipo: 'confinado', material: 'sillar_amarillo', ubicacion: 'barda', altura_m: '2.6', elementos: [{ ref: castillo }],
    });

    await page.setViewportSize({ width: 1400, height: 1100 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const pestanas = page.getByRole('tablist', { name: 'Panel lateral' });
    await pestanas.getByRole('tab', { name: /^Artefacto/ }).click();
    await page.getByRole('navigation', { name: 'Plantillas de muro' }).getByRole('button', { name: new RegExp(nombre) }).click();
    const area = page.getByRole('region', { name: 'Artefacto', exact: true });
    await expect(area.getByLabel('Nombre de la plantilla')).toHaveValue(nombre);
    await expect(area.getByLabel('Material de la plantilla')).toHaveValue('sillar_amarillo');

    // --- El aviso «material sin elemento» desaparece: BAP-01010 es la mampostería implícita y se revisa como cualquier elemento ------------
    const validacion = area.getByRole('group', { name: 'Validación contra la matriz' });
    await expect(validacion.getByRole('list', { name: 'Alertas de la plantilla' })).toBeVisible();
    await expect(validacion.locator('[data-codigo="material_sin_elemento"]')).toHaveCount(0);
    await expect(validacion.locator('[data-codigo="material_sin_concepto"]')).toHaveCount(0);
    await expect(validacion.locator('[data-codigo="sin_concepto"]')).toHaveCount(0);
    await expect(validacion.locator('li[data-nivel="bloquea"]')).toHaveCount(0);
    await expect(validacion.getByText(/BAP-01010/).first()).toBeVisible(); // la mampostería del sillar es un elemento más de la revisión
    const validar = validacion.getByRole('button', { name: 'Validar la plantilla' });
    await validacion.getByLabel('Acepto las alertas por revisar').check();
    await validar.click();
    await expect(area.getByText('Plantilla validada.')).toBeVisible();

    // --- El selector de elementos de muro ofrece BAP-01010 ----------------------------------------------------------------------------
    const opciones = await area.getByLabel('Agregar un elemento a la plantilla').locator('option').allTextContents();
    expect(opciones.some((o) => /^BAP-01010/.test(o))).toBe(true);

    // --- Un trazo elige la plantilla de sillar ------------------------------------------------------------------------------------------
    await pestanas.getByRole('tab', { name: /^Trazos/ }).click();
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await cajaEstable(page, lienzo);
    await pulsarMarca(page, page.locator('.visor__trazo').first());
    await page.getByRole('group', { name: 'Tipo de muro' }).last().getByRole('button', { name: 'Confinado' }).click();
    await page.getByLabel('Plantilla de muro', { exact: true }).selectOption(plantilla.id);
    const clasificacion = async () =>
      llamarApi<{ tipo: string; material: string; ubicacion: string; plantilla_id: string | null }>(request, 'control', 'GET', `/trazos/${muro}/muro/clasificacion`);
    await expect.poll(async () => (await clasificacion()).plantilla_id).toBe(plantilla.id);
    expect(await clasificacion()).toMatchObject({ tipo: 'confinado', material: 'sillar_amarillo', ubicacion: 'barda' });
  });
});
