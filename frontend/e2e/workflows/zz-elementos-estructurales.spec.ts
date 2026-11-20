import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Elementos estructurales de la biblioteca (Ola 3B): trabes, contratrabes, nervaduras, zapata Z-1 y columna C-1.
 *
 *  1. La biblioteca trae las categorías nuevas con sus elementos (24 trabes en «Trabes de losa (catálogo)»).
 *  2. La tarjeta de una trabe: sección ancho × peralte, cálculo por metro lineal y por pieza (largo y zonas de anillo), conciliación con
 *     el catálogo (= ≈ ≠) y el elemento sin mano de obra, con el colado y cimbra por ml por proponer (clave provisional EJ-703, D8) y su destajo por ml sin importe.
 *  3. La zapata Z-1 cuadra con EST-03020 sin dado; la columna C-1 nace con su altura habitual de 4.20 m (editable) y su anclaje es una
 *     sugerencia de 40 diámetros por extremo: el elemento avisa si el valor capturado cumple.
 *  3b. T-2-12x20 (dos anillos) trae una versión propuesta del concepto: Costos la propone, Control de obra la autoriza y el catálogo
 *     vigente sigue a la vista (D7).
 *  4. La corrección de EST-02330 (unidad m² → m) es una versión nueva del concepto: Costos la propone, Control de obra la autoriza y el
 *     catálogo vigente no cambia.
 */

const ROLES = ['control', 'costos'] as const;

test.describe('Cuantificador · elementos estructurales de la biblioteca', () => {
  test.skip(!hayRoles(...ROLES), motivoSinRoles(...ROLES));
  test.setTimeout(150_000);

  test('trabes por ml y por pieza, Z-1, C-1 y la corrección de EST-02330', async ({ page, request, browser }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `EST-${sufijo}`,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Elementos estructurales',
      archivo_url: 'planos/elementos-estructurales.dwg',
    });

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    const pestanas = page.getByRole('tablist', { name: 'Panel lateral' });
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();
    const area = page.getByRole('region', { name: 'Elementos', exact: true });
    const biblioteca = page.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });

    // --- 1. La biblioteca -------------------------------------------------------------------------------------------
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    for (const categoria of [/Trabes/, /Contratrabes/, /Nervaduras/, /Zapatas/, /Columnas/]) {
      await expect(biblioteca.getByRole('button', { name: categoria }).first()).toBeVisible();
    }
    await expect(biblioteca.getByRole('button', { name: /Trabes de losa \(catálogo\)/ })).toBeVisible();
    for (const clave of ['T-1-15x25', 'T-14-17x60', 'CT1-15x25', 'N-1-12x25', 'Z-1', 'C-1']) {
      await expect(biblioteca.getByRole('button', { name: new RegExp(`^${clave}\\b`) })).toBeVisible();
    }

    // --- 2. Una trabe: por ml, por pieza y la conciliación ----------------------------------------------------------
    await biblioteca.getByRole('button', { name: /^T-1-15x25\b/ }).click();
    const trabe = area.getByRole('article', { name: /T-1-15x25/ });
    await expect(trabe.getByTestId('ee-seccion')).toContainText('15 × 25 cm (ancho × peralte)');
    await expect(trabe.getByTestId('ee-concreto')).toContainText('0.0394 m³ por metro');
    await expect(trabe.getByTestId('ee-cimbra')).toContainText('0.65 m² (3 lados)');
    await expect(trabe.getByTestId('ee-sin-mano-de-obra')).toBeVisible();
    const conciliacion = trabe.locator('[data-conciliacion="AUX-00008"]');
    await expect(conciliacion.locator('tr[data-marca="="]')).toHaveCount(2); // anillo y alambre iguales al catálogo
    await expect(conciliacion.locator('tr[data-marca="≈"]')).toContainText('ACR-00001'); // varilla: traslape de 40 diámetros contra 8 %
    await expect(conciliacion.locator('tr[data-marca="≈"]')).toContainText('-4.4 %');
    // El colado y la cimbra por ml se proponen con su clave provisional (D8); el destajo por ml queda sin importe y no hay precios.
    const camino = trabe.getByRole('region', { name: 'Colado, cimbra y destajo' });
    await expect(camino).toHaveAttribute('data-camino', 'por_registrar');
    await expect(camino.getByTestId('ee-camino-colado')).toContainText('Concepto nuevo por registrar');
    await expect(camino.getByTestId('ee-sin-destajo')).toContainText('no trae destajo');
    await expect(camino.locator('[data-concepto-propuesto="EJ-703"]')).toBeVisible();
    await expect(camino.getByTestId('ee-destajo-por-ml')).toContainText('EJ-703-MO');
    await expect(camino.getByTestId('ee-destajo-por-ml')).toContainText('sin importe');
    expect(await camino.innerText()).not.toMatch(/\$/);

    // Por pieza de 6 m, con zonas de anillo en los extremos.
    await trabe.getByLabel('Se mide por').selectOption('pieza');
    await trabe.getByLabel('Largo de la pieza en metros').fill('6');
    await expect(trabe.getByTestId('ee-concreto')).toContainText('0.2363 m³ por pieza');
    await expect(trabe.getByText('Cortes, traslapes y anillos del acero')).toBeVisible();
    await trabe.getByLabel(/Anillos con zona más cerrada/).check();
    await expect(trabe.getByTestId('ee-concreto')).toContainText('0.2363 m³ por pieza');
    await expect(trabe.getByRole('region', { name: 'Conciliación con el catálogo' })).toContainText('por metro (de la pieza de 6.00 m)');
    await trabe.getByLabel('Se mide por').selectOption('ml');
    await expect(trabe.getByTestId('ee-concreto')).toContainText('0.0394 m³ por metro');

    // La nervadura no lleva cimbra; la contratrabe, dos costados.
    await biblioteca.getByRole('button', { name: /^N-1-12x25\b/ }).click();
    const nervadura = area.getByRole('article', { name: /N-1-12x25/ });
    await expect(nervadura.getByTestId('ee-cimbra')).toContainText('0.00 m² (0 lados)');
    await biblioteca.getByRole('button', { name: /^CT1-15x25\b/ }).click();
    await expect(area.getByRole('article', { name: /CT1-15x25/ }).getByTestId('ee-cimbra')).toContainText('0.50 m² (2 lados)');

    // --- 3. Z-1 y C-1 ------------------------------------------------------------------------------------------------
    await biblioteca.getByRole('button', { name: /^Z-1\b/ }).click();
    const zapata = area.getByRole('article', { name: /Z-1/ });
    await expect(zapata.locator('[data-conciliacion="EST-03020"] tr[data-marca="="]')).toHaveCount(2); // varilla y alambre
    await expect(zapata.locator('[data-conciliacion="EST-03020"]')).toContainText('MOE-05010'); // el destajo va en el concepto
    await expect(zapata.getByRole('list', { name: 'Advertencias' })).toContainText('dado');
    await expect(zapata.getByLabel('Se mide por')).toHaveCount(0);
    await biblioteca.getByRole('button', { name: /^C-1\b/ }).click();
    const columna = area.getByRole('article', { name: /C-1/ });
    await expect(columna.getByLabel('Altura de la columna en metros')).toHaveValue('4.2');
    await expect(columna.getByTestId('ee-concreto')).toContainText('0.3969 m³ por pieza'); // 0.30 × 0.30 × 4.20 × 1.05
    // El anclaje es una sugerencia (40 diámetros por extremo): vacío propone, capturado avisa si cumple.
    await expect(columna.getByTestId('ee-anclaje')).toContainText('Sugerido: 40 diámetros por extremo');
    await columna.getByLabel('Anclaje de la varilla por extremo en centímetros').fill('20');
    await expect(columna.getByTestId('ee-anclaje')).toHaveAttribute('data-cumple', 'false');
    await expect(columna.getByTestId('ee-anclaje')).toContainText('NO cumple');
    await columna.getByLabel('Anclaje de la varilla por extremo en centímetros').fill('60');
    await expect(columna.getByTestId('ee-anclaje')).toHaveAttribute('data-cumple', 'true');
    await columna.getByLabel('Altura de la columna en metros').fill('7');
    await expect(columna.getByRole('list', { name: 'Advertencias' })).toContainText('pasa del escalón');
    await expect(columna.locator('[data-conciliacion="EST-12011"]')).toBeVisible();

    // --- 3b. T-2-12x20: dos anillos en el catálogo, una versión propuesta del concepto ------------------------------------
    await biblioteca.getByRole('button', { name: /^T-2-12x20\b/ }).click();
    const t2 = area.getByRole('article', { name: /T-2-12x20/ });
    await expect(t2.locator('[data-conciliacion="AUX-10205"] tr[data-marca="solo_catalogo"]')).toContainText('ACE-00029'); // el segundo anillo
    await expect(t2.locator('[data-conciliacion="AUX-10205"]')).toContainText('Versión propuesta'); // junto al catálogo vigente
    const versiones = t2.getByRole('region', { name: 'Versiones propuestas' });
    const proponer = versiones.getByRole('button', { name: 'Proponer las correcciones del catálogo' });
    if (await proponer.count()) {
      await proponer.click();
      await expect(versiones.locator('[data-propuesta="AUX-10205"]')).toContainText(/Pendiente|Autorizada/); // lo que propone Control de obra nace autorizado
    }
    const propuesta = versiones.locator('[data-propuesta="AUX-10205"]');
    await expect(propuesta).toContainText('ACE-00029');
    const autorizar = propuesta.getByRole('button', { name: 'Autorizar' });
    if (await autorizar.count()) await autorizar.click();
    await expect(propuesta).toContainText('Autorizada');
    // El catálogo vigente no cambió: la fila del segundo anillo sigue ahí con 0.6683.
    await expect(t2.locator('[data-conciliacion="AUX-10205"]')).toContainText('0.6683');

    // --- 3c. T-5-12x30: el estribo pasa del anillo 10×25 al alambrón (ACE-00002), con los kg reales ----------------------
    await biblioteca.getByRole('button', { name: /^T-5-12x30\b/ }).click();
    const t5 = area.getByRole('article', { name: /T-5-12x30/ });
    const conciliacionT5 = t5.locator('[data-conciliacion="AUX-00060"]');
    await expect(conciliacionT5).toContainText('Versión propuesta');
    await expect(conciliacionT5.locator('tr[data-marca="solo_propuesta"]')).toContainText('ACE-00002'); // el alambrón entra
    await expect(conciliacionT5.locator('tr[data-marca="solo_propuesta"]')).toContainText('1.8032'); // kg reales por metro
    const versionesT5 = t5.getByRole('region', { name: 'Versiones propuestas' });
    const proponerT5 = versionesT5.getByRole('button', { name: 'Proponer las correcciones del catálogo' });
    if (await proponerT5.count()) await proponerT5.click();
    const propuestaT5 = versionesT5.locator('[data-propuesta="AUX-00060"]');
    await expect(propuestaT5).toContainText('ACE-00002');
    await expect(propuestaT5).toContainText('ACE-00006');
    // El catálogo vigente no cambió: el anillo 10×25 sigue con 1.9401.
    await expect(conciliacionT5).toContainText('1.9401');

    // --- 4. La corrección de EST-02330 como versión nueva del concepto ------------------------------------------------
    await biblioteca.getByRole('button', { name: /^T-1-15x25\b/ }).click();
    const costos = await browser.newContext();
    const paginaCostos = await costos.newPage();
    await entrarComo(paginaCostos, 'costos');
    await paginaCostos.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await paginaCostos.getByRole('tablist', { name: 'Panel lateral' }).getByRole('tab', { name: /^Elementos/ }).click();
    const bibliotecaCostos = paginaCostos.getByRole('tabpanel', { name: /Elementos/ }).getByRole('navigation', { name: 'Biblioteca de elementos' });
    await bibliotecaCostos.getByRole('button', { name: 'Expandir todo' }).click();
    await bibliotecaCostos.getByRole('button', { name: /^T-1-15x25\b/ }).click();
    const correccionCostos = paginaCostos.locator('[data-correccion="EST-02330"]');
    await expect(correccionCostos.getByRole('table', { name: 'Diferencia de EST-02330' })).toContainText('m²');
    await correccionCostos.getByRole('button', { name: /Proponer versión nueva/ }).click();
    await expect(correccionCostos).toContainText('Pendiente de autorizar por Control de obra');
    await expect(correccionCostos.getByRole('button', { name: 'Autorizar' })).toHaveCount(0); // Costos propone, no autoriza
    await costos.close();

    await page.reload();
    await pestanas.getByRole('tab', { name: /^Elementos/ }).click();
    await biblioteca.getByRole('button', { name: 'Expandir todo' }).click();
    await biblioteca.getByRole('button', { name: /^T-1-15x25\b/ }).click();
    const correccion = trabe.locator('[data-correccion="EST-02330"]');
    await expect(correccion).toContainText('Pendiente de autorizar por Control de obra');
    await correccion.getByRole('button', { name: 'Autorizar' }).click();
    await expect(correccion).toContainText('Autorizada · versión 1');
    // El catálogo vigente se sigue mostrando como venía: la diferencia queda a la vista.
    await expect(correccion.getByRole('table', { name: 'Diferencia de EST-02330' })).toContainText('m²');
    await expect(correccion.getByRole('list', { name: 'Historial de EST-02330' })).toContainText('Versión 1 autorizada');
    // La API confirma el estado y que no se creó ningún elemento ni concepto de EST-02330.
    const estado = await llamarApi<{ estado: string; version_vigente: number | null; valor_vigente: string; valor_catalogo: string }[]>(
      request, 'control', 'GET', '/correcciones-de-catalogo',
    );
    expect(estado[0]).toMatchObject({ estado: 'autorizada', version_vigente: 1, valor_vigente: 'm', valor_catalogo: 'm2' });
  });
});
