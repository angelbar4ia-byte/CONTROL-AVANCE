import { cajaEstable, entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, pulsarMarca, test } from '../infraestructura';

/**
 * Plantillas de muro por prototipo (Ola 4, «plantillas por prototipo»): el muro confinado lleva VARIOS castillos, cada uno con su regla
 * (cada separación y extremos, solo extremos, por ml, total del prototipo); hay una plantilla por prototipo y planta (Oro PB y PA son el
 * ejemplo, por confirmar y con su fila y celda del Excel), las demás quedan por capturar, y las cadenas y los castillos estimados
 * alimentan los conceptos al elegir la plantilla en el muro.
 */

const ROLES_ZZ = ['control'] as const;

interface Elemento {
  clave: string;
}
interface Plantilla {
  id: string;
  nombre: string;
  prototipo: string | null;
  planta: string | null;
  por_confirmar: boolean;
  validacion: string;
  notas: string | null;
  elementos: { ref: string; regla?: string | null; total_m?: string | null; base_m2?: string | null; piezas_por_ml?: string | null }[];
}

test.describe('Cuantificador · plantillas de muro por prototipo', () => {
  test.skip(!hayRoles(...ROLES_ZZ), motivoSinRoles(...ROLES_ZZ));
  test.setTimeout(180_000);

  test('Oro PB y PA nacen por confirmar con su celda, un prototipo vacío se captura con varios castillos y el muro toma sus cantidades', async ({
    page,
    request,
  }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    // --- Los elementos del catálogo que usan los ejemplos de Oro (se crean solo si faltan; la firma de cada uno es única) --------
    const existentes = new Set((await llamarApi<Elemento[]>(request, 'control', 'GET', '/elementos-parametricos')).map((e) => e.clave));
    const crear = async (clave: string, cuerpo: Record<string, unknown>) => {
      if (!existentes.has(clave)) await llamarApi(request, 'control', 'POST', '/elementos-parametricos', { clave, nombre: `Elemento ${clave}`, ...cuerpo });
    };
    for (const [n, k] of ['K-1', 'K-2', 'K-3', 'K-6', 'K-7'].entries()) {
      await crear(k, { tipo: 'castillo', parametros: { largo: 0.4 + n / 1000, ancho: 0.15 } });
    }
    for (const [n, k] of ['CE-1', 'CE-2'].entries()) {
      await crear(k, { tipo: 'lineal', categoria: 'cadenas', subcategoria: 'cerramiento', parametros: { ancho: 0.4 + n / 1000, alto: 0.2 } });
    }
    // El prototipo «Rubí · PB» se captura desde cero en cada corrida: si quedó de antes, se borra (ningún muro lo usa).
    const previas = await llamarApi<Plantilla[]>(request, 'control', 'GET', '/muro-plantillas');
    for (const p of previas.filter((x) => x.prototipo === 'rubi')) await llamarApi(request, 'control', 'DELETE', `/muro-plantillas/${p.id}`);

    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `PRT-${sufijo}`,
    });
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Muro por prototipo',
      archivo_url: 'planos/prototipo.dwg',
    });
    await llamarApi(request, 'control', 'PUT', `/obras/${obra.id}/drivers/altura_estandar`, { valor: '3' });
    const muro = (
      await llamarApi<{ trazo_id: string }>(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
        version_plano: 1, fuente: 'pdf', geometria_wkt: 'LINESTRING(0 0, 10 0)', grosor_m: '0.15', alineacion: 'centro',
        enlaces: [{ medida: 'longitud', factor: '1', actividad_id: actividad!.id, conversion: { modo: 'area', mide: 'eje' } }],
      })
    ).trazo_id;

    await page.setViewportSize({ width: 1400, height: 1100 });
    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}&actividad=${actividad!.id}`);
    const pestanas = page.getByRole('tablist', { name: 'Panel lateral' });
    await pestanas.getByRole('tab', { name: /^Artefacto/ }).click();
    const area = page.getByRole('region', { name: 'Artefacto', exact: true });
    const panel = page.getByRole('navigation', { name: 'Plantillas de muro' });

    // --- 1. Cargar los ejemplos: Oro PB y PA por confirmar; las que piden elementos que faltan no se inventan ---------------------
    await panel.getByRole('button', { name: 'Cargar los ejemplos (Oro y global)' }).click();
    const aviso = panel.getByTestId('aviso-de-ejemplos');
    await expect(aviso).toContainText(/Se crearon \d+ plantillas de ejemplo|ya existían/);
    await expect(aviso).toContainText(/faltan en tu catálogo K-4|faltan en tu catálogo K-8|Global/); // las globales piden K-4 y K-8 si no están
    const oro = panel.locator('[data-prototipo="oro_401"]');
    await expect(oro.getByRole('button', { name: 'Oro 4.01 PB: abrir la plantilla' })).toBeVisible();
    await expect(oro.getByRole('button', { name: 'Oro 4.01 PA: abrir la plantilla' })).toBeVisible();
    // Un prototipo de 1 planta solo tiene PB y uno sin capturar lo dice.
    await expect(panel.locator('[data-prototipo="rubi"]')).toContainText('PB · sin capturar');
    await expect(panel.locator('[data-prototipo="rubi"]')).not.toContainText('PA');

    // --- 2. Oro PB: varios castillos con su regla, la celda del Excel y «por confirmar» ---------------------------------------
    await oro.getByRole('button', { name: 'Oro 4.01 PB: abrir la plantilla' }).click();
    await expect(area.getByLabel('Nombre de la plantilla')).toHaveValue('Muro confinado · Oro 4.01 · PB');
    await expect(area.getByLabel('Prototipo de la plantilla')).toHaveValue('oro_401');
    await expect(area.getByLabel('Planta de la plantilla')).toHaveValue('PB');
    await expect(area.getByLabel('Datos por confirmar')).toBeChecked();
    await expect(area.locator('[data-validacion="por_validar"]')).toBeVisible();
    await expect(area.getByLabel('Notas de la plantilla')).toHaveValue(/ASIGNACIÓN!K2152/);
    const lista = area.getByRole('list', { name: 'Elementos de la plantilla' });
    for (const k of ['K-1', 'K-2', 'K-3', 'K-7', 'CE-1']) await expect(lista.locator(`[data-elemento="${k}"]`)).toBeVisible();
    await expect(area.getByLabel('Regla de K-1')).toHaveValue('total');
    await expect(area.getByLabel('Metros totales de K-1')).toHaveValue('126');
    await expect(area.getByLabel('m² de muro de la base de K-1')).toHaveValue('286');
    await expect(area.getByTestId('origen-de-K-1')).toContainText('ASIGNACIÓN!K2152');
    // La vista previa: 126 × 6 m ÷ 286 m² ÷ 3.00 m = 2.64 piezas de K-1 en el tramo (se dibujan 3); K-3 (20 m): 0.42 (se dibuja 1).
    await expect(area.locator('[data-castillo="K-1"][data-regla="total"]')).toHaveCount(3);
    await expect(area.locator('[data-castillo="K-3"][data-regla="total"]')).toHaveCount(1);
    // Cambiar la regla de un castillo (sin guardar) cambia la vista: «solo extremos» dibuja dos piezas.
    await area.getByLabel('Regla de K-1').selectOption('extremos');
    await expect(area.locator('[data-castillo="K-1"][data-regla="extremos"]')).toHaveCount(2);
    await area.getByLabel('Regla de K-1').selectOption('por_ml');
    await area.getByLabel('Piezas por ml de K-1').fill('0.5');
    await expect(area.locator('[data-castillo="K-1"][data-regla="por_ml"]')).toHaveCount(3); // 6 ml × 0.5 pza/ml

    // --- 3. Un prototipo sin datos se captura: planta, varios castillos con su regla y notas ------------------------------------
    await pestanas.getByRole('tab', { name: /^Artefacto/ }).click();
    await panel.getByRole('button', { name: 'Capturar Rubí PB' }).click();
    await expect(area.getByLabel('Nombre de la plantilla')).toHaveValue('Muro confinado · Rubí · PB');
    await expect(area.getByRole('group', { name: 'Tipo de muro de la plantilla' }).getByRole('button', { name: 'Muro confinado' })).toHaveAttribute('aria-pressed', 'true');
    await expect(area.getByLabel('Prototipo de la plantilla')).toHaveValue('rubi');
    await expect(area.getByLabel('Planta de la plantilla')).toHaveValue('PB');
    await expect(area.getByLabel('Planta de la plantilla').locator('option')).toHaveCount(1); // Rubí tiene una sola planta
    await area.getByLabel('Agregar un elemento a la plantilla').selectOption('K-1');
    await area.getByLabel('Agregar un elemento a la plantilla').selectOption('K-3');
    await area.getByLabel('Agregar un elemento a la plantilla').selectOption('CE-1');
    await area.getByLabel('Regla de K-1').selectOption('por_ml');
    await area.getByLabel('Piezas por ml de K-1').fill('0.4');
    await area.getByLabel('Regla de K-3').selectOption('total');
    await area.getByLabel('Metros totales de K-3').fill('28');
    await area.getByLabel('m² de muro de la base de K-3').fill('317.72');
    await area.getByLabel('Notas de la plantilla').fill('Captura de prueba E2E.');
    await area.getByRole('button', { name: 'Crear plantilla' }).click();
    await expect(area.getByText('Plantilla creada: queda por validar.')).toBeVisible();
    const rubi = (await llamarApi<Plantilla[]>(request, 'control', 'GET', '/muro-plantillas')).find((p) => p.prototipo === 'rubi')!;
    expect([rubi.planta, rubi.por_confirmar, rubi.validacion]).toEqual(['PB', true, 'por_validar']);
    expect(rubi.elementos.map((e) => [e.ref, e.regla ?? null])).toEqual([['K-1', 'por_ml'], ['K-3', 'total'], ['CE-1', null]]);
    expect(Number(rubi.elementos[1]!.total_m)).toBe(28);
    await expect(panel.locator('[data-prototipo="rubi"]').getByRole('button', { name: 'Rubí PB: abrir la plantilla' })).toBeVisible();

    // --- 4. El muro elige la plantilla de Oro PB y el detalle dice cuánto lleva de cada castillo y cómo lo contó -------------
    const oroPb = (await llamarApi<Plantilla[]>(request, 'control', 'GET', '/muro-plantillas')).find((p) => p.prototipo === 'oro_401' && p.planta === 'PB')!;
    await llamarApi(request, 'control', 'PUT', `/trazos/${muro}/muro/plantilla`, { plantilla_id: oroPb.id });
    await pestanas.getByRole('tab', { name: /^Trazos/ }).click();
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await cajaEstable(page, lienzo);
    await pulsarMarca(page, page.locator('.visor__trazo').first());
    const region = page.getByRole('region', { name: 'Elementos de la plantilla' });
    await expect(region).toBeVisible();
    await expect(region.getByTestId('contexto-de-colocacion')).toContainText('10.00 m de largo');
    // 10 m × 3.00 m = 30 m²: K-1 lleva 126 × 30 ÷ 286 = 13.22 m de castillo = 4.41 piezas de 3.00 m, contadas por «total»; la cadena, 10 ml.
    await expect(region.locator('[data-elemento="K-1"]')).toContainText('4.41 pza');
    await expect(region.getByTestId('regla-de-K-1')).toContainText('total del prototipo');
    await expect(region.locator('[data-elemento="K-1"]')).toContainText('estimados (no se colocan)');
    await expect(region.locator('[data-elemento="CE-1"]')).toContainText('10.00 ml');
    const colocacion = await llamarApi<{ elementos: { ref: string; regla: string | null; piezas_estimadas: string; metros: string }[] }>(
      request, 'control', 'GET', `/trazos/${muro}/muro/plantilla/colocacion`,
    );
    const k1 = colocacion.elementos.find((e) => e.ref === 'K-1')!;
    expect(k1.regla).toBe('total');
    expect(Number(k1.piezas_estimadas)).toBeCloseTo(4.406, 3);
    expect(Number(k1.metros)).toBeCloseTo(13.218, 2);
  });
});
