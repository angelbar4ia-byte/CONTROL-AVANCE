import { entrarComo, expect, hayRoles, llamarApi, motivoSinRoles, test } from '../infraestructura';

/**
 * Mediciones, la capa sombra del cuantificador (migración 0088).
 *
 *  1. Una medición se crea en la pestaña «Mediciones» y se vuelve la activa: lo que se dibuja entra a
 *     ella, sin pedir concepto. Una submedición (recámara 1) cuelga de la madre (la losa).
 *  2. Lo suelto no suma a ningún concepto («sin asignar»); al asignar la losa a un concepto suma lo de
 *     todas sus recámaras, y un trazo que entra después hereda el enlace.
 *  3. Una medición solo admite trazos de su tipo: se avisa antes de guardar.
 *  4. Quitar la asignación deja el concepto sin esa cantidad.
 *
 * Es una obra nueva por corrida: no consume obras de la semilla.
 */

const ROLES_X = ['control'] as const;

type Feature = { id: string; geometry: { type: string; coordinates: unknown }; properties: { medicion_id: string | null; enlaces: { vigente: boolean }[] } };

test.describe('Cuantificador · mediciones', () => {
  test.skip(!hayRoles(...ROLES_X), motivoSinRoles(...ROLES_X));
  test.setTimeout(150_000);

  test('se dibuja una vez en una medición y se asigna a un concepto', async ({ page, request }) => {
    const clave = `MED-${Date.now().toString(36).toUpperCase()}`;
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
    const [actividad] = await llamarApi<{ id: string }[]>(request, 'control', 'GET', `/obras/${obra.id}/actividades`);
    const plano = await llamarApi<{ id: string }>(request, 'control', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Cimentación',
      archivo_url: 'planos/cim-med.dwg',
    });
    const trazos = async () =>
      (await llamarApi<{ features: Feature[] }>(request, 'control', 'GET', `/planos/${plano.id}/trazos`)).features;
    const cantidad = async () => {
      const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
        request,
        'control',
        'GET',
        `/obras/${obra.id}/cuantificacion`,
      );
      return Number(nodos.find((n) => n.nodo_id === actividad!.id)?.cantidad_medida ?? 0);
    };

    await entrarComo(page, 'control');
    await page.goto(`/cuantificador?obra=${obra.id}&plano=${plano.id}`);
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const c = (await lienzo.boundingBox())!;
    const clic = (fx: number, fy: number) => page.mouse.click(c.x + c.width * fx, c.y + c.height * fy);
    const panel = page.getByRole('region', { name: 'Mediciones del plano' });
    const rect = async (x1: number, y1: number, x2: number, y2: number) => {
      await barra.getByRole('button', { name: 'Rectángulo', exact: true }).click();
      await clic(x1, y1);
      await clic(x2, y2);
    };

    // --- 1. Una medición y su submedición ---------------------------------------------------------------
    await page.getByRole('tab', { name: /Mediciones/ }).click();
    await expect(panel).toContainText('Este plano aún no tiene mediciones');
    await panel.getByRole('button', { name: 'Nueva medición' }).click();
    await panel.getByLabel('Nombre de la medición').fill('Losa de cimentación');
    await panel.getByLabel('Tipo de medición').selectOption('area');
    await panel.getByRole('button', { name: 'Crear medición' }).click();
    await expect(page.getByTestId('tipo-del-concepto')).toContainText('Losa de cimentación');
    await expect(barra.locator('[data-bloque="area"]')).toHaveClass(/is-resaltado/);

    await panel.getByRole('button', { name: 'Agregar una submedición a Losa de cimentación' }).click();
    await panel.getByLabel('Nombre de la medición').fill('Recámara 1');
    await expect(panel.getByLabel('Dentro de')).toHaveValue(/.+/);
    await panel.getByRole('button', { name: 'Crear medición' }).click();
    await expect(page.getByTestId('tipo-del-concepto')).toContainText('Recámara 1');
    await expect(panel.getByRole('treeitem', { name: 'Losa de cimentación' }).getByRole('treeitem', { name: 'Recámara 1' })).toBeVisible();

    // Lo que se dibuja entra a la medición activa, sin pedir concepto.
    await rect(0.4, 0.3, 0.55, 0.45);
    let alta = page.getByRole('dialog', { name: 'Guardar polígono' });
    await expect(alta.getByTestId('aviso-medicion')).toContainText('Recámara 1');
    await expect(alta.getByTestId('aviso-medicion')).toContainText('Todavía no alimenta ningún concepto');
    await alta.getByRole('button', { name: 'Guardar trazo' }).click();
    await expect(alta).toBeHidden();
    await expect.poll(async () => (await trazos()).length).toBe(1);

    await panel.getByRole('button', { name: 'Agregar una submedición a Losa de cimentación' }).click();
    await panel.getByLabel('Nombre de la medición').fill('Recámara 2');
    await panel.getByRole('button', { name: 'Crear medición' }).click();
    await expect(page.getByTestId('tipo-del-concepto')).toContainText('Recámara 2');
    await rect(0.6, 0.3, 0.8, 0.5);
    alta = page.getByRole('dialog', { name: 'Guardar polígono' });
    await expect(alta.getByTestId('aviso-medicion')).toContainText('Recámara 2');
    await alta.getByRole('button', { name: 'Guardar trazo' }).click();
    await expect(alta).toBeHidden();
    await expect.poll(async () => (await trazos()).length).toBe(2);

    const [t1, t2] = await trazos();
    expect(t1!.properties.medicion_id).not.toBeNull();
    expect(t2!.properties.medicion_id).not.toBeNull();
    expect(t1!.properties.medicion_id).not.toBe(t2!.properties.medicion_id);
    expect(t1!.properties.enlaces).toHaveLength(0); // suelto: no suma a ningún concepto
    expect(await cantidad()).toBe(0);

    // La losa suma lo de sus recámaras y dice que aún no alimenta nada.
    const losa = panel.getByRole('treeitem', { name: 'Losa de cimentación', exact: true });
    await expect(losa.getByText('Sin asignar').first()).toBeVisible();
    const valorLosa = Number((await losa.getByTestId('valor-de-medicion').first().textContent())!.replace(/[^\d.]/g, ''));
    expect(valorLosa).toBeGreaterThan(0);

    // --- 2. Se asigna la losa a un concepto: suma las dos recámaras ----------------------------------------------
    await panel.getByRole('button', { name: 'Asignar Losa de cimentación a un concepto' }).click();
    const formulario = panel.getByRole('form', { name: 'Asignar Losa de cimentación' });
    await formulario.getByRole('combobox').first().selectOption({ index: 1 });
    await formulario.getByRole('button', { name: 'Asignar' }).click();
    await expect(page.getByRole('status')).toContainText('2 trazos enlazados');
    await expect.poll(cantidad).toBeCloseTo(valorLosa, 1); // la pantalla redondea a dos decimales
    await expect(losa.getByText('Sin asignar')).toHaveCount(0);

    // Un trazo que entra después hereda el enlace de la losa: se enlaza solo.
    // La recámara 2 sigue siendo la medición activa (la última que se creó): ahí entra lo que se dibuje.
    await expect(panel.getByRole('button', { name: 'Recámara 2', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await rect(0.6, 0.6, 0.7, 0.7);
    alta = page.getByRole('dialog', { name: 'Guardar polígono' });
    await expect(alta.getByTestId('aviso-medicion')).toContainText('Se enlaza sola');
    await alta.getByRole('button', { name: 'Guardar trazo' }).click();
    await expect(page.getByRole('status')).toContainText('Trazo guardado');
    await expect.poll(async () => (await trazos()).length).toBe(3);
    const despues = await cantidad();
    expect(despues).toBeGreaterThan(valorLosa);

    // --- 3. Una medición de área no admite una línea: se avisa antes de guardar --------------------------------
    await barra.getByRole('button', { name: 'Línea', exact: true }).click();
    const cabeza = page.locator('.opciones__cabeza[aria-expanded="true"]');
    if ((await cabeza.count()) > 0) await cabeza.first().click();
    await clic(0.4, 0.8);
    await clic(0.6, 0.8);
    alta = page.getByRole('dialog', { name: 'Guardar línea' });
    await expect(alta.getByTestId('aviso-incompatible')).toContainText('no admite una línea');
    await expect(alta.getByRole('button', { name: 'Guardar trazo' })).toBeDisabled();
    await alta.getByRole('button', { name: 'Cancelar' }).click();
    expect((await trazos()).length).toBe(3);

    // --- 4. Quitar la asignación: el concepto deja de sumar esa medición -----------------------------------------
    await page.getByRole('tab', { name: /Mediciones/ }).click();
    await panel.getByRole('button', { name: /Quitar la asignación de Losa de cimentación/ }).click();
    await expect(page.getByRole('status')).toContainText('dejaron de sumar');
    await expect.poll(cantidad).toBe(0);
    await expect(losa.getByText('Sin asignar').first()).toBeVisible();
  });
});
