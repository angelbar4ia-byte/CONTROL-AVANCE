import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Hojas «matriz» del cuantificador (cerebro WORKFLOWS.md §8.9; D-565, D-583).
 *
 * El concepto es la matriz madre y un insumo puede ser otra matriz (nervaduras, trabes, bastones):
 * esas son las que se cuantifican.
 *
 *  1. El árbol del cuantificador abre, bajo un concepto, sus **matrices internas** con lo que el
 *     catálogo implica para esa actividad.
 *  2. Medir una matriz interna **ajusta el importe** de la actividad sin tocar su cantidad base.
 *  3. Al trazar se elige **qué se mide**: la actividad entera o una de sus matrices.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_S = ['control', 'residente'] as const;

test.describe('Hojas matriz · medir la matriz dentro del concepto', () => {
  test.skip(!hayRoles(...ROLES_S), motivoSinRoles(...ROLES_S));
  test.setTimeout(120_000);

  test('las matrices internas se abren bajo el concepto y medirlas ajusta el importe', async ({
    browser,
    request,
  }) => {
    const clave = `MTZ-${Date.now().toString(36).toUpperCase()}`;
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
      clave,
    });

    // Una losa (matriz madre) de 10 m² a $1,000, dada de alta como trabajo extra.
    const conceptos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/conceptos');
    const losa = conceptos.find((c) => c.clave === 'MTZ-LOSA')!;
    const nerv = conceptos.find((c) => c.clave === 'MTZ-NERV')!;
    const extra = await llamarApi<{ id: string }>(request, 'residente', 'POST', '/actividades', {
      obra_id: obra.id,
      descripcion: 'Losa de cimentación',
      orden_cambio: 'OC-MTZ-1',
      cant_base: '10',
      precio_unitario: '1000',
      precio_destajo: '600',
      concepto_id: losa.id,
    });

    const control = await (await browser.newContext()).newPage();
    await entrarComo(control, 'control');
    await control.goto(`/cuantificador?obra=${obra.id}`);

    // --- 1. Bajo el concepto se abren sus matrices internas -------------------------------------------
    await control.getByRole('button', { name: /Matrices de MTZ-LOSA/ }).click();
    const matrices = control.getByRole('region', { name: 'Matrices de MTZ-LOSA' });
    await expect(matrices).toContainText('MTZ-NERV');
    await expect(matrices).toContainText('MTZ-TRABE');
    await expect(matrices.getByText('Sin medir')).toHaveCount(3); // nervaduras, trabes y bastones
    const filaNerv = matrices.getByRole('treeitem', { name: /MTZ-NERV/ });
    await expect(filaNerv).toContainText('5'); // 10 m² × 0.5 que implica el catálogo

    // Las matrices son carpetas anidadas: los bastones están DENTRO de las nervaduras, y cada una
    // dice cómo se mide (por su unidad) y cuántas lleva medidas.
    const bastones = filaNerv.getByRole('treeitem', { name: /MTZ-BAST/ });
    await expect(bastones).toBeVisible();
    await expect(bastones).toContainText('15'); // 10 × 0.5 × 3 que implica el catálogo
    await expect(bastones.getByTestId('tipo-de-matriz')).toHaveText('Lineal');
    await expect(filaNerv.getByTestId('tipo-de-matriz').first()).toHaveText('Área');
    await expect(filaNerv).toContainText('0 de 2'); // ella y sus bastones, ninguna medida
    await expect(matrices.getByRole('treeitem', { name: /MTZ-TRABE/ }).getByRole('treeitem')).toHaveCount(0);
    // Se contrae la rama y se esconden los bastones.
    await matrices.getByRole('button', { name: /Contraer MTZ-NERV/ }).click();
    await expect(bastones).toHaveCount(0);
    await matrices.getByRole('button', { name: /Expandir MTZ-NERV/ }).click();
    await expect(bastones).toBeVisible();

    // --- 2. Se mide la nervadura: 8 contra 5, y el importe se ajusta ---------------------------------------
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Cimentación',
      archivo_url: 'planos/cim.dwg',
    });
    await llamarApi(request, 'control', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: 'LINESTRING(0 0, 8 0)',
      enlaces: [{ actividad_id: extra.id, matriz_concepto_id: nerv.id, medida: 'longitud', factor: '1' }],
    });
    await control.reload();
    // Las matrices abiertas se recuerdan al recargar o cambiar de menú: siguen abiertas, no hay que volver a abrirlas.
    const despues = control.getByRole('region', { name: 'Matrices de MTZ-LOSA' });
    await expect(despues.getByRole('treeitem', { name: /MTZ-NERV/ })).toContainText('8');
    await expect(despues.getByText('Sin medir')).toHaveCount(2); // quedan las trabes y los bastones
    await expect(despues).toContainText('Lo medido ajusta el importe');
    await expect(despues).toContainText('La cantidad de la actividad no cambia');

    // Un clic en una matriz la vuelve lo que se mide: su tipo resalta el bloque de la barra.
    await despues.getByRole('button', { name: /^MTZ-BAST · / }).click();
    await expect(control.getByTestId('tipo-del-concepto')).toContainText('MTZ-BAST');
    await expect(control.getByTestId('tipo-del-concepto')).toContainText('Lineal (ml)');
    await expect(control.getByRole('toolbar', { name: 'Herramientas de trazo' }).locator('[data-bloque="lineal"]')).toHaveClass(
      /is-resaltado/,
    );
    await despues.getByRole('button', { name: /^MTZ-BAST · / }).click(); // otro clic la suelta: se vuelve a medir la losa
    await expect(control.getByTestId('tipo-del-concepto')).not.toContainText('MTZ-BAST');
    await expect(control.getByTestId('tipo-del-concepto')).toContainText('Área');

    // La matriz que se está midiendo llega elegida al cajón de guardar.
    const bast = conceptos.find((c) => c.clave === 'MTZ-BAST')!;
    await despues.getByRole('button', { name: /^MTZ-BAST · / }).click();
    await control.getByRole('toolbar', { name: 'Herramientas de trazo' }).getByRole('button', { name: 'Línea', exact: true }).click();
    // Aunque en las opciones haya quedado un grosor, los bastones (ml) miden largo: no es un muro.
    await control.getByRole('button', { name: /^0[.,]15/ }).first().click();
    const cabeza = control.locator('.opciones__cabeza[aria-expanded="true"]');
    if ((await cabeza.count()) > 0) await cabeza.first().click();
    const lienzo = control.getByRole('img', { name: 'Plano con sus trazos' });
    const caja = (await lienzo.boundingBox())!;
    await control.mouse.click(caja.x + caja.width * 0.4, caja.y + caja.height * 0.5);
    await control.mouse.click(caja.x + caja.width * 0.8, caja.y + caja.height * 0.5);
    // Con la matriz elegida el trazo se guarda solo, enlazado a ella, sin cajón.
    await expect(control.getByRole('dialog', { name: 'Guardar línea' })).toBeHidden();
    await expect(control.getByRole('status')).toContainText('Trazo guardado');
    await expect
      .poll(async () => {
        const t = await llamarApi<{ features: { properties: { enlaces: { matriz_concepto_id?: string | null }[] } }[] }>(
          request, 'control', 'GET', `/planos/${plano.id}/trazos`,
        );
        return t.features.some(
          (f) =>
            f.properties.enlaces.some((e) => e.matriz_concepto_id === bast.id && (e as { medida?: string }).medida === 'longitud') &&
            !(f.properties as { grosor_m?: unknown }).grosor_m,
        );
      })
      .toBe(true);

    const actividades = await llamarApi<{ id: string; cant_base: string }[]>(
      request,
      'control',
      'GET',
      `/obras/${obra.id}/actividades`,
    );
    expect(Number(actividades.find((a) => a.id === extra.id)!.cant_base)).toBe(10);
  });
});
