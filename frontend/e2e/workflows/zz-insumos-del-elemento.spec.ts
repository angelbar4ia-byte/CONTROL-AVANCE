import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, solicitarApi, test } from '../infraestructura';

/**
 * Insumos permitidos por tipo de elemento, familias y comparación con el catálogo (plan de elementos de muro, fase D):
 *  1. La tarjeta del elemento (pestaña Trazos) deja elegir el concreto de las familias de concretos; se guarda en el elemento.
 *  2. La ventana de agregar insumos (clase → familia → búsqueda, multiselección) marca «fuera de lo usual» el insumo de otra
 *     familia y no deja marcarlo; el servidor lo rechaza con un 422 claro.
 *  3. Herramienta y equipo: el andamio se crea como insumo provisional, sin precio, y se agrega al elemento.
 *  4. La comparación con el concepto del catálogo muestra los insumos del elemento.
 */

const ROLES_ZD = ['control'] as const;

interface Familia { id: string; clave: string }

test.describe('Cuantificador · insumos del elemento', () => {
  test.skip(!hayRoles(...ROLES_ZD), motivoSinRoles(...ROLES_ZD));
  test.setTimeout(120_000);

  test('materiales, ventana de insumos permitidos, andamio provisional y comparación', async ({ page, request }) => {
    const sufijo = Date.now().toString(36).toUpperCase();
    const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
    const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
    const unidades = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/unidades');
    const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
      cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
      prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
      clave: `INS-${sufijo}`,
    });
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Insumos del elemento',
      archivo_url: 'planos/insumos-del-elemento.dwg',
    });

    // Las familias del catálogo (la subfamilia cuelga de la familia); se reutilizan si ya existen.
    const existentes = await llamarApi<Familia[]>(request, 'control', 'GET', '/familias');
    const familia = async (nombre: string, padre?: string): Promise<string> => {
      const hallada = existentes.find((f) => f.clave.toUpperCase() === nombre.toUpperCase());
      if (hallada) return hallada.id;
      const f = await llamarApi<Familia>(request, 'control', 'POST', '/familias', { clave: nombre, nombre, parent_id: padre ?? null, aplica_a: 'material' });
      existentes.push(f);
      return f.id;
    };
    const aceros = await familia('Aceros');
    const consumible = await familia('Consumible', aceros);
    const mezclas = await familia('Mezclas');
    const concretos = await familia('Concretos', mezclas);
    const petreos = await familia('Pétreos');
    const piedras = await familia('Piedras', petreos);
    const kg = unidades.find((u) => u.clave === 'kg')?.id ?? null;
    const insumo = (clave: string, descripcion: string, familia_id: string) =>
      llamarApi<{ id: string }>(request, 'control', 'POST', '/insumos', { clave: `${clave}-${sufijo}`, descripcion, tipo: 'material', unidad_id: kg, familia_id, costo_base: 10 });
    const alambre = await insumo('ACE', `ALAMBRE ${sufijo}`, consumible);
    await insumo('MEZ', `CONCRETO ${sufijo}`, concretos);
    await insumo('PET', `PIEDRA ${sufijo}`, piedras);

    const clave = `KI-${sufijo}`.slice(0, 20);
    const alto = 3.1 + (Date.now() % 1_000_000) / 1e7;
    const elemento = await llamarApi<{ id: string }>(request, 'control', 'POST', '/elementos-parametricos', {
      clave, nombre: 'Castillo con insumos', tipo: 'castillo', parametros: { alto },
    });
    const concepto = await llamarApi<{ id: string }>(request, 'control', 'POST', '/conceptos', {
      tipo: 'concepto', clave: `CI-${sufijo}`, descripcion: 'Concepto de colado', unidad_id: unidades.find((u) => u.clave === 'pza')!.id,
    });
    await llamarApi(request, 'control', 'POST', `/elementos-parametricos/${elemento.id}/conceptos-por-contexto`, {
      concepto_id: concepto.id, unidad: 'pza', toma: { concreto: true },
    });

    // El servidor rechaza el insumo de otra familia con un mensaje claro.
    const hallados = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', `/elementos-parametricos/${elemento.id}/insumos-disponibles?q=PET-${sufijo}`);
    const rechazo = await solicitarApi(request, 'control', 'POST', `/elementos-parametricos/${elemento.id}/insumos`, { insumos: [{ insumo_id: hallados[0]!.id }] });
    expect(rechazo.status()).toBe(422);
    expect(await rechazo.text()).toContain('no es de las familias');

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    await page.getByRole('tab', { name: /^Trazos/ }).click();
    await page.getByRole('button', { name: `Ver ${clave}` }).click();
    const tarjeta = page.locator(`[data-insumos-del-elemento="${clave}"]`);

    // --- 1. El concreto del elemento ---------------------------------------------------------------------------
    await tarjeta.getByLabel('Concreto (concreto)').selectOption(`MEZ-${sufijo}`);
    await expect.poll(async () => {
      const lista = await llamarApi<{ clave: string; materiales: { concreto: string | null } }[]>(request, 'control', 'GET', '/elementos-parametricos');
      return lista.find((e) => e.clave === clave)?.materiales.concreto;
    }).toBe(`MEZ-${sufijo}`);

    // --- 2. La ventana: la piedra sale fuera de lo usual y no se puede marcar -----------------------------------------
    await tarjeta.getByRole('button', { name: '+ Agregar insumos' }).click();
    const ventana = page.getByRole('dialog', { name: 'Agregar insumos al elemento' });
    await ventana.locator('[data-clase-de-insumo="material"]').click();
    await ventana.getByLabel('Buscar insumo').fill(sufijo);
    await expect(ventana.locator(`[data-insumo-disponible="PET-${sufijo}"]`)).toContainText('fuera de lo usual');
    await expect(ventana.getByLabel(`Marcar PET-${sufijo}`)).toBeDisabled();
    await ventana.getByLabel(`Marcar ACE-${sufijo}`).check();
    await ventana.getByLabel(`Marcar MEZ-${sufijo}`).check();
    await ventana.getByRole('button', { name: /^Agregar 2 seleccionados/ }).click();
    await expect(tarjeta.locator(`[data-insumo-agregado="ACE-${sufijo}"]`)).toBeVisible();
    await expect(tarjeta.locator(`[data-insumo-agregado="MEZ-${sufijo}"]`)).toBeVisible();
    expect(alambre.id).toBeTruthy();

    // --- 3. Herramienta y equipo: el andamio provisional, sin precio ------------------------------------------------
    await tarjeta.getByRole('button', { name: '+ Agregar insumos' }).click();
    const v2 = page.getByRole('dialog', { name: 'Agregar insumos al elemento' });
    await v2.locator('[data-clase-de-insumo="herramienta"]').click();
    await v2.locator('[data-sugerencia]').first().click();
    await expect(v2.locator('[data-insumo-disponible]').first()).toContainText('provisional, sin precio');
    await v2.locator('[data-insumo-disponible]').first().getByRole('checkbox').check();
    await v2.getByRole('button', { name: /^Agregar 1 seleccionado/ }).click();
    await expect(tarjeta.locator('[data-insumo-agregado]').filter({ hasText: 'Provisional, sin precio' })).toHaveCount(1);

    // --- 4. La comparación ------------------------------------------------------------------------------------------
    const comparacion = tarjeta.locator(`[data-comparacion="CI-${sufijo}"]`);
    await expect(comparacion).toContainText('= hasta 3 %, ≈ hasta 8 %, ≠ más');
    await expect(comparacion.locator(`[data-insumo-comparado="MEZ-${sufijo}"]`)).toHaveAttribute('data-marca', 'solo_elemento');
  });
});
