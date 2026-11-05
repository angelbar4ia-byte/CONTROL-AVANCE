import type { APIRequestContext, Page } from '@playwright/test';
import {
  actividadDe,
  entrarComo,
  expect,
  hayRoles,
  llamarApi,
  motivoSinRoles,
  test,
} from '../infraestructura';

/** El selector de obra del Cuantificador dice «CLAVE · Proyecto · Cluster»: se elige por la clave. */
async function elegirObra(pagina: Page, clave: string) {
  const selector = pagina.getByLabel('Obra', { exact: true });
  const opcion = selector.locator('option', { hasText: clave }).first();
  await selector.selectOption({ label: (await opcion.textContent())!.trim() });
}


/**
 * Cuantificador · trazar sobre un plano y ver la cantidad en la obra
 * (cerebro MODELO.md §1b: plano → trazo → enlace → cantidad).
 *
 *  1. El residente abre el cuantificador, elige la obra y su plano.
 *  2. Dibuja un polígono con cuatro clics y lo termina con Enter.
 *  3. Lo enlaza al Área de una actividad y lo guarda.
 *  4. La cantidad medida aparece en la tabla de la obra, y el servidor
 *     (PostGIS) coincide: el visor no calcula nada.
 *  5. Un clic dentro del polígono lo elige y muestra su enlace; recargar la
 *     página no lo pierde.
 *
 * Los planos se registran con un `archivo_url` que no es imagen ni PDF
 * (`.dwg`) a propósito: así el visor traza sobre su rejilla y la prueba no
 * depende de R2 (en CI no hay). Los fondos de imagen y de PDF se prueban
 * aparte, simulando la URL firmada.
 *
 * Usa `OBRA-G` de `e2e/soporte/semilla.sql`; es de un solo uso (cada prueba
 * registra su propio plano y lo elige por nombre, así no dependen del orden).
 */

const ROLES_G = ['residente'] as const;

async function obraG(request: APIRequestContext) {
  const obras = await llamarApi<{ id: string; clave: string }[]>(
    request,
    'residente',
    'GET',
    '/obras',
  );
  const obra = obras.find((o) => o.clave === 'OBRA-G');
  expect(obra, 'OBRA-G existe (¿se sembró?)').toBeDefined();
  return obra!;
}

/**
 * Una obra propia con sus tres actividades (E2E-EXC, E2E-PLA, E2E-CIM): la
 * cantidad medida de una de ellas es solo de la prueba que la crea, así que no
 * depende de lo que midan las demás en paralelo.
 */
async function obraPropia(request: APIRequestContext, prefijo: string) {
  const clave = `${prefijo}-${Date.now().toString(36).toUpperCase()}`;
  const clusters = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/clusters');
  const prototipos = await llamarApi<{ id: string; clave: string }[]>(request, 'control', 'GET', '/prototipos');
  const usuarios = await llamarApi<{ id: string; nombre: string }[]>(request, 'control', 'GET', '/usuarios');
  const obra = await llamarApi<{ id: string }>(request, 'control', 'POST', '/obras', {
    cluster_id: clusters.find((c) => c.clave === 'CLU-E2E')!.id,
    prototipo_id: prototipos.find((p) => p.clave === 'CAS-E2E')!.id,
    residente_id: usuarios.find((u) => u.nombre === 'Rosa Residente')!.id,
    clave,
  });
  return { id: obra.id, clave };
}

test.describe('Cuantificador · trazar un polígono', () => {
  test.skip(!hayRoles(...ROLES_G), motivoSinRoles(...ROLES_G));
  test.setTimeout(90_000);

  test('un polígono enlazado a una actividad suma su área a la obra', async ({
    page,
    request,
  }) => {
    const obras = await llamarApi<{ id: string; clave: string }[]>(
      request,
      'residente',
      'GET',
      '/obras',
    );
    const obra = obras.find((o) => o.clave === 'OBRA-G');
    expect(obra, 'OBRA-G existe (¿se sembró?)').toBeDefined();
    await llamarApi(request, 'residente', 'POST', `/obras/${obra!.id}/planos`, {
      nombre: 'Planta baja E2E',
      archivo_url: 'e2e/planta-baja.dwg',
    });

    // --- 1. Abrir el cuantificador -------------------------------------
    await entrarComo(page, 'residente');
    await page.goto('/cuantificador');
    await elegirObra(page, 'OBRA-G');
    await page.getByLabel('Plano', { exact: true }).selectOption({ label: 'Planta baja E2E · v1' });

    // --- 2. Dibujar -----------------------------------------------------
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await expect(lienzo).toBeVisible();
    const caja = (await lienzo.boundingBox())!;
    const en = (fx: number, fy: number) => ({
      x: caja.x + caja.width * fx,
      y: caja.y + caja.height * fy,
    });

    await page.getByRole('button', { name: 'Polígono', exact: true }).click();
    // Dos vértices no cierran un polígono: Enter no abre el formulario.
    for (const [fx, fy] of [
      [0.3, 0.3],
      [0.7, 0.3],
    ] as const) {
      await page.mouse.click(en(fx, fy).x, en(fx, fy).y);
    }
    await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog')).toHaveCount(0);

    for (const [fx, fy] of [
      [0.7, 0.7],
      [0.3, 0.7],
    ] as const) {
      await page.mouse.click(en(fx, fy).x, en(fx, fy).y);
    }
    await expect(page.getByText('4 vértices')).toBeVisible();
    await page.keyboard.press('Enter');

    // --- 3. Enlazar y guardar ------------------------------------------
    const alta = page.getByRole('dialog', { name: 'Guardar polígono' });
    const valorActividad = await alta
      .locator('#enlace-actividad-0 option', { hasText: 'E2E-EXC' })
      .getAttribute('value');
    await alta.getByLabel('Actividad 1').selectOption(valorActividad!);
    await alta.getByLabel('Medida').selectOption('area');
    await alta.getByRole('button', { name: 'Guardar trazo' }).click();

    // --- 4. La cantidad llega a la obra --------------------------------
    await expect(page.getByRole('status')).toContainText('Trazo guardado');
    const filas = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
      request,
      'residente',
      'GET',
      `/obras/${obra!.id}/cuantificacion`,
    );
    const actividadId = await actividadDe(request, 'residente', 'OBRA-G', 'E2E-EXC');
    const nodo = filas.find((n) => n.nodo_id === actividadId);
    expect(nodo, 'la actividad enlazada aparece en la cuantificación').toBeDefined();
    expect(Number(nodo!.cantidad_medida)).toBeGreaterThan(0);

    const tabla = page.getByRole('treeitem', { name: /Excavación de cepas/ });
    await expect(tabla).toBeVisible();

    // --- 5. Elegirlo con un clic y que sobreviva a recargar -------------
    await page.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    await page.mouse.click(en(0.5, 0.5).x, en(0.5, 0.5).y);
    await expect(page.getByText('Trazo elegido')).toBeVisible();
    await expect(page.getByRole('cell', { name: /Área × 1/ })).toBeVisible();

    await page.reload();
    await elegirObra(page, 'OBRA-G');
    // Al recargar se abre el primer plano de la lista, que depende de los que
    // hayan registrado las demás pruebas: se elige el de ésta por nombre.
    await page.getByLabel('Plano', { exact: true }).selectOption({ label: 'Planta baja E2E · v1' });
    await expect(page.locator('.visor__trazo')).toHaveCount(1);
  });

  test('un plano que es imagen se pinta de fondo y el visor encuadra a su tamaño', async ({
    page,
    request,
  }) => {
    const obras = await llamarApi<{ id: string; clave: string }[]>(
      request,
      'residente',
      'GET',
      '/obras',
    );
    const obra = obras.find((o) => o.clave === 'OBRA-G')!;
    await llamarApi(request, 'residente', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Plano con imagen',
      archivo_url: 'e2e/fachada.png',
    });

    // R2 no existe en CI: se simula la URL firmada y el archivo que serviría.
    // La imagen mide 400×200 y las coordenadas del plano son las suyas.
    await page.route('**/api/v1/planos/*/archivo', (ruta) =>
      ruta.fulfill({
        json: {
          url: 'http://127.0.0.1:5173/__e2e/fachada.svg',
          expira_en_segundos: 900,
          expira_en: new Date(Date.now() + 900_000).toISOString(),
        },
      }),
    );
    await page.route('**/__e2e/fachada.svg', (ruta) =>
      ruta.fulfill({
        contentType: 'image/svg+xml',
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><rect width="400" height="200" fill="#ddd"/></svg>',
      }),
    );

    await entrarComo(page, 'residente');
    await page.goto('/cuantificador');
    await elegirObra(page, 'OBRA-G');
    await page.getByLabel('Plano', { exact: true }).selectOption({ label: 'Plano con imagen · v1' });

    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await expect(lienzo.locator('image')).toHaveAttribute('width', '400');
    await expect(lienzo).toHaveAttribute('viewBox', '0 0 400 200');
  });

  test('el residente anota el plano y la nota se elige con un clic, sin sumar cantidad', async ({
    page,
    request,
  }) => {
    const obra = await obraG(request);
    await llamarApi(request, 'residente', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Plano con notas',
      archivo_url: 'e2e/notas.dwg',
    });

    await entrarComo(page, 'residente');
    await page.goto('/cuantificador');
    await elegirObra(page, 'OBRA-G');
    await page.getByLabel('Plano', { exact: true }).selectOption({ label: 'Plano con notas · v1' });

    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    const caja = (await lienzo.boundingBox())!;
    const centro = { x: caja.x + caja.width * 0.5, y: caja.y + caja.height * 0.5 };

    await page.getByRole('button', { name: 'Nota', exact: true }).click();
    await page.mouse.click(centro.x, centro.y);
    const alta = page.getByRole('dialog', { name: 'Anotar el plano' });
    await alta.getByLabel('Nota', { exact: true }).fill('Revisar el nivel del piso aquí');
    await alta.getByRole('button', { name: 'Guardar nota' }).click();
    await expect(page.getByRole('status')).toContainText('Nota guardada');
    await expect(page.locator('.visor__nota')).toHaveCount(1);

    await page.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    await page.mouse.click(centro.x, centro.y);
    await expect(page.getByText('Nota elegida')).toBeVisible();
    // En `aside`: el mismo texto vive también en el <title> (tooltip) de la nota.
    await expect(page.locator('aside').getByText('Revisar el nivel del piso aquí')).toBeVisible();
    await expect(page.getByText('Una nota no suma cantidad.')).toBeVisible();
  });

  test('Control de obra no anota: la herramienta Nota no se le ofrece', async ({ page }) => {
    test.skip(!hayRoles('control'), motivoSinRoles('control'));
    await entrarComo(page, 'control');
    await page.goto('/cuantificador');
    await elegirObra(page, 'OBRA-G');
    await expect(page.getByRole('button', { name: 'Polígono', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Nota', exact: true })).toHaveCount(0);
  });

  test('reemplazar un enlace: el anterior deja de sumar y el nuevo cuenta', async ({
    page,
    request,
  }) => {
    const obra = await obraG(request);
    const actividadId = await actividadDe(request, 'residente', 'OBRA-G', 'E2E-PLA');
    const plano = await llamarApi<{ id: string }>(
      request,
      'residente',
      'POST',
      `/obras/${obra.id}/planos`,
      { nombre: 'Plano para reemplazar', archivo_url: 'e2e/reemplazo.dwg' },
    );
    // A (40×30 = 1200) alimenta la actividad; B (60×30 = 1800) llega después,
    // sin enlace, y es la que va a sustituir a A.
    const rectangulo = (x0: number, ancho: number) =>
      `POLYGON((${x0} 0, ${x0 + ancho} 0, ${x0 + ancho} 30, ${x0} 30, ${x0} 0))`;
    await llamarApi(request, 'residente', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'pdf',
      geometria_wkt: rectangulo(0, 40),
      enlaces: [{ medida: 'area', factor: '1', actividad_id: actividadId }],
    });
    await llamarApi(request, 'residente', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'dwg',
      geometria_wkt: rectangulo(100, 60),
      enlaces: [],
    });
    const medido = async () => {
      const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
        request,
        'residente',
        'GET',
        `/obras/${obra.id}/cuantificacion`,
      );
      return Number(nodos.find((n) => n.nodo_id === actividadId)?.cantidad_medida);
    };
    expect(await medido()).toBe(1200);

    await entrarComo(page, 'residente');
    await page.goto('/cuantificador');
    await elegirObra(page, 'OBRA-G');
    await page.getByLabel('Plano', { exact: true }).selectOption({ label: 'Plano para reemplazar · v1' });

    // El visor encuadra los dos trazos (x de 0 a 160); A queda a la izquierda.
    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await expect(page.locator('.visor__trazo')).toHaveCount(2);
    const caja = (await lienzo.boundingBox())!;
    await page.mouse.click(caja.x + caja.width * 0.18, caja.y + caja.height * 0.5);
    await expect(page.getByText('Trazo elegido')).toBeVisible();

    await page.getByRole('button', { name: 'Reemplazar', exact: true }).click();
    const dialogo = page.getByRole('dialog', { name: 'Reemplazar enlace' });
    const valorB = await dialogo
      .locator('#reemplazo-trazo option', { hasText: 'DWG' })
      .getAttribute('value');
    await dialogo.getByLabel('Sustituir por').selectOption(valorB!);
    await dialogo.getByLabel('Medida').selectOption('area');
    await dialogo.getByRole('button', { name: 'Reemplazar', exact: true }).click();

    await expect(page.getByRole('status')).toContainText('Enlace reemplazado');
    await expect(page.getByText('· reemplazado')).toBeVisible();
    // El servidor es la fuente de verdad: A ya no suma, B sí.
    expect(await medido()).toBe(1800);
  });

  test('la primera hoja de un PDF se pinta de fondo a escala fija', async ({ page, request }) => {
    const obra = await obraG(request);
    await llamarApi(request, 'residente', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Plano en PDF',
      archivo_url: 'e2e/hoja.pdf',
    });

    // Una hoja de 300×200 puntos. A escala 2 (ESCALA_PDF) son 600×400 unidades
    // de plano: si alguien cambia la escala, los trazos hechos sobre PDF se
    // mueven y esta prueba avisa.
    const pdf = [
      '%PDF-1.4',
      '1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj',
      '2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj',
      '3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]>>endobj',
      'trailer<</Root 1 0 R/Size 4>>',
      '%%EOF',
    ].join('\n');
    await page.route('**/api/v1/planos/*/archivo', (ruta) =>
      ruta.fulfill({
        json: {
          url: 'http://127.0.0.1:5173/__e2e/hoja.pdf',
          expira_en_segundos: 900,
          expira_en: new Date(Date.now() + 900_000).toISOString(),
        },
      }),
    );
    await page.route('**/__e2e/hoja.pdf', (ruta) =>
      ruta.fulfill({ contentType: 'application/pdf', body: pdf }),
    );

    await entrarComo(page, 'residente');
    await page.goto('/cuantificador');
    await elegirObra(page, 'OBRA-G');
    await page.getByLabel('Plano', { exact: true }).selectOption({ label: 'Plano en PDF · v1' });

    const lienzo = page.getByRole('img', { name: 'Plano con sus trazos' });
    await expect(lienzo.locator('image')).toHaveCount(1);
    await expect(lienzo).toHaveAttribute('viewBox', '0 0 600 400');
  });

  test('enlazar a un nodo del prototipo es de Control: el residente no lo ve', async ({
    browser,
    request,
  }) => {
    test.skip(!hayRoles('control'), motivoSinRoles('control'));
    const obra = await obraG(request);
    await llamarApi(request, 'residente', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Plano de gobierno',
      archivo_url: 'e2e/gobierno.dwg',
    });

    // No se guarda: enlazar a un nodo sobrescribe la cantidad del prototipo,
    // que comparten todas las obras (otros workflows generan obras de él). El
    // guardado lo cubre el test de backend del camino «diseño nuevo»; aquí se
    // fija lo que es de la interfaz: quién ve la opción y la advertencia.
    async function abrirFormularioDeTrazo(rol: 'control' | 'residente') {
      const pagina = await (await browser.newContext()).newPage();
      await entrarComo(pagina, rol);
      await pagina.goto('/cuantificador');
      await elegirObra(pagina, 'OBRA-G');
      await pagina.getByLabel('Plano', { exact: true }).selectOption({ label: 'Plano de gobierno · v1' });
      const caja = (await pagina.getByRole('img', { name: 'Plano con sus trazos' }).boundingBox())!;
      await pagina.getByRole('button', { name: 'Polígono', exact: true }).click();
      for (const [fx, fy] of [
        [0.3, 0.3],
        [0.7, 0.3],
        [0.5, 0.7],
      ] as const) {
        await pagina.mouse.click(caja.x + caja.width * fx, caja.y + caja.height * fy);
      }
      await pagina.keyboard.press('Enter');
      return pagina.getByRole('dialog', { name: 'Guardar polígono' });
    }

    const control = await abrirFormularioDeTrazo('control');
    await control.getByLabel('Enlazar a').selectOption('prototipo');
    await expect(control.getByRole('note')).toContainText('Sobrescribe la cantidad');
    // Los conceptos del prototipo de la semilla están disponibles.
    await expect(control.locator('#enlace-actividad-0 option', { hasText: 'E2E-EXC' })).toHaveCount(1);

    const residente = await abrirFormularioDeTrazo('residente');
    await expect(residente.getByLabel('Actividad 1')).toBeVisible();
    await expect(residente.getByLabel('Enlazar a')).toHaveCount(0);
  });

  test('Control aprueba un trazo: queda constancia y la cantidad no cambia', async ({
    browser,
    request,
  }) => {
    test.skip(!hayRoles('control'), motivoSinRoles('control'));
    const obra = await obraG(request);
    const plano = await llamarApi<{ id: string }>(
      request,
      'residente',
      'POST',
      `/obras/${obra.id}/planos`,
      { nombre: 'Plano para aprobar', archivo_url: 'e2e/aprobar.dwg' },
    );
    const actividadId = await actividadDe(request, 'residente', 'OBRA-G', 'E2E-PLA');
    await llamarApi(request, 'residente', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'pdf',
      geometria_wkt: 'POLYGON((0 0, 40 0, 40 30, 0 30, 0 0))',
      enlaces: [{ medida: 'area', factor: '1', actividad_id: actividadId }],
    });
    const medido = async () => {
      const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
        request,
        'control',
        'GET',
        `/obras/${obra.id}/cuantificacion`,
      );
      return Number(nodos.find((n) => n.nodo_id === actividadId)?.cantidad_medida);
    };
    const antes = await medido();

    async function elegirElTrazo(rol: 'control' | 'residente') {
      const pagina = await (await browser.newContext()).newPage();
      await entrarComo(pagina, rol);
      await pagina.goto('/cuantificador');
      await elegirObra(pagina, 'OBRA-G');
      await pagina.getByLabel('Plano', { exact: true }).selectOption({ label: 'Plano para aprobar · v1' });
      await expect(pagina.locator('.visor__trazo')).toHaveCount(1);
      const caja = (await pagina.getByRole('img', { name: 'Plano con sus trazos' }).boundingBox())!;
      await pagina.mouse.click(caja.x + caja.width * 0.5, caja.y + caja.height * 0.5);
      await expect(pagina.getByText('Trazo elegido')).toBeVisible();
      return pagina;
    }

    // El residente no aprueba lo que se traza: ve «Sin aprobar» y ningún botón.
    const residente = await elegirElTrazo('residente');
    await expect(residente.getByText('Sin aprobar')).toBeVisible();
    await expect(residente.getByRole('button', { name: 'Aprobar trazo' })).toHaveCount(0);

    const control = await elegirElTrazo('control');
    await expect(control.getByText('Aprobar deja constancia de la revisión')).toBeVisible();
    await control.getByRole('button', { name: 'Aprobar trazo' }).click();
    await expect(control.getByRole('status')).toContainText('Trazo aprobado');
    await expect(control.getByText(/^Aprobado ·/)).toBeVisible();
    await expect(control.locator('.visor__trazo.is-aprobado')).toHaveCount(1);
    await expect(control.getByRole('button', { name: 'Aprobar trazo' })).toHaveCount(0);

    // Es una marca de revisión, no una compuerta: la cantidad es la misma.
    expect(await medido()).toBe(antes);
  });

  test('un polígono con los bordes cruzados no se guarda: el motivo llega a la pantalla', async ({
    page,
    request,
  }) => {
    const obra = await obraG(request);
    await llamarApi(request, 'residente', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Plano de la corbata',
      archivo_url: 'e2e/corbata.dwg',
    });

    await entrarComo(page, 'residente');
    await page.goto('/cuantificador');
    await elegirObra(page, 'OBRA-G');
    await page.getByLabel('Plano', { exact: true }).selectOption({ label: 'Plano de la corbata · v1' });

    const caja = (await page.getByRole('img', { name: 'Plano con sus trazos' }).boundingBox())!;
    await page.getByRole('button', { name: 'Polígono', exact: true }).click();
    // El ortogonal (por defecto) alinearía los lados; la corbata necesita diagonales: se apaga.
    await page.getByRole('button', { name: /^ORTO/ }).click();
    // Cuatro vértices en orden de «corbata»: los lados 1-2 y 3-4 se cruzan. El
    // área firmada se cancela y PostGIS mediría 0: el trazo sumaría cero en silencio.
    for (const [fx, fy] of [
      [0.3, 0.2],
      [0.7, 0.5],
      [0.7, 0.2],
      [0.3, 0.5],
    ] as const) {
      await page.mouse.click(caja.x + caja.width * fx, caja.y + caja.height * fy);
    }
    await page.keyboard.press('Enter');

    const alta = page.getByRole('dialog', { name: 'Guardar polígono' });
    const valor = await alta
      .locator('#enlace-actividad-0 option', { hasText: 'E2E-EXC' })
      .getAttribute('value');
    await alta.getByLabel('Actividad 1').selectOption(valor!);
    await alta.getByLabel('Medida').selectOption('area');
    await alta.getByRole('button', { name: 'Guardar trazo' }).click();

    await expect(alta.getByRole('alert')).toContainText('inválida');
    // El cajón sigue abierto con lo dibujado: quien traza corrige y reintenta.
    await expect(alta).toBeVisible();
    await expect(page.locator('.visor__trazo')).toHaveCount(0);
  });
  test('calibrar la escala: dos puntos y los metros que son corrigen todas las cantidades del plano', async ({
    page,
    request,
  }) => {
    test.skip(!hayRoles('control'), motivoSinRoles('control'));
    const obra = await obraPropia(request, 'CAL');
    const clave = obra.clave;
    const plano = await llamarApi<{ id: string }>(
      request,
      'residente',
      'POST',
      `/obras/${obra.id}/planos`,
      { nombre: 'Plano para calibrar', archivo_url: 'e2e/calibrar.dwg' },
    );
    const actividadId = await actividadDe(request, 'residente', clave, 'E2E-CIM');
    await llamarApi(request, 'residente', 'POST', `/planos/${plano.id}/trazos`, {
      version_plano: 1,
      fuente: 'pdf',
      geometria_wkt: 'POLYGON((0 0, 40 0, 40 30, 0 30, 0 0))',
      enlaces: [{ medida: 'area', factor: '1', actividad_id: actividadId }],
    });
    const medido = async () => {
      const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
        request,
        'residente',
        'GET',
        `/obras/${obra.id}/cuantificacion`,
      );
      return Number(nodos.find((n) => n.nodo_id === actividadId)?.cantidad_medida);
    };

    // Sin calibrar: la cantidad está en unidades de plano (40 × 30) y la pantalla lo dice.
    expect(await medido()).toBe(1200);
    await entrarComo(page, 'residente');
    await page.goto('/cuantificador');
    await elegirObra(page, clave);
    await page.getByLabel('Plano', { exact: true }).selectOption({ label: 'Plano para calibrar · v1' });
    await expect(page.getByText('Sin calibrar: cantidades en unidades de plano')).toBeVisible();

    // Marcar dos puntos de una distancia conocida y decir cuántos metros son.
    const caja = (await page.getByRole('img', { name: 'Plano con sus trazos' }).boundingBox())!;
    await page.getByRole('button', { name: 'Calibrar escala', exact: true }).click();
    await page.mouse.click(caja.x + caja.width * 0.3, caja.y + caja.height * 0.1);
    await page.mouse.click(caja.x + caja.width * 0.7, caja.y + caja.height * 0.1);
    const dialogo = page.getByRole('dialog', { name: 'Calibrar la escala' });
    await expect(dialogo).toContainText('unidades de plano');
    await dialogo.getByLabel('Distancia real (m)').fill('10');
    await expect(dialogo.getByText(/Escala: 1 unidad de plano = /)).toBeVisible();
    await dialogo.getByRole('button', { name: 'Calibrar escala', exact: true }).click();

    await expect(page.getByRole('status')).toContainText('Escala calibrada');
    await expect(page.getByText(/^Escala 1 u = /)).toBeVisible();

    // El servidor aplicó la escala: el área cambió con el cuadrado de los metros por unidad.
    const trazos = await llamarApi<{ escala_m_por_unidad: string }>(
      request,
      'residente',
      'GET',
      `/planos/${plano.id}/trazos`,
    );
    const k = Number(trazos.escala_m_por_unidad);
    expect(k).toBeGreaterThan(0);
    expect(k).not.toBe(1);
    expect(Math.abs((await medido()) - 1200 * k * k)).toBeLessThan(1e-3 * Math.max(1, 1200 * k * k));
  });
  test('un polígono con hueco descuenta la abertura: se dibuja, se guarda y el servidor mide el área restada', async ({
    page,
    request,
  }) => {
    test.skip(!hayRoles('control'), motivoSinRoles('control'));
    const obra = await obraPropia(request, 'HUE');
    const plano = await llamarApi<{ id: string }>(request, 'residente', 'POST', `/obras/${obra.id}/planos`, {
      nombre: 'Fachada con ventana',
      archivo_url: 'e2e/fachada.dwg',
    });
    const actividadId = await actividadDe(request, 'residente', obra.clave, 'E2E-CIM');

    await entrarComo(page, 'residente');
    await page.goto('/cuantificador');
    await elegirObra(page, obra.clave);
    await page.getByLabel('Plano', { exact: true }).selectOption({ label: 'Fachada con ventana · v1' });
    const caja = (await page.getByRole('img', { name: 'Plano con sus trazos' }).boundingBox())!;
    const en = (fx: number, fy: number) => ({
      x: caja.x + caja.width * fx,
      y: caja.y + caja.height * fy,
    });
    const clic = async ([fx, fy]: readonly [number, number]) =>
      page.mouse.click(en(fx, fy).x, en(fx, fy).y);

    // El muro: cuatro vértices, guardado como área.
    await page.getByRole('button', { name: 'Polígono', exact: true }).click();
    for (const p of [[0.2, 0.1], [0.8, 0.1], [0.8, 0.35], [0.2, 0.35]] as const) await clic(p);
    await expect(page.getByText('4 vértices')).toBeVisible();
    await page.keyboard.press('Enter');
    const alta = page.getByRole('dialog', { name: 'Guardar polígono' });
    const valor = await alta
      .locator('#enlace-actividad-0 option', { hasText: 'E2E-CIM' })
      .getAttribute('value');
    await alta.getByLabel('Actividad 1').selectOption(valor!);
    await alta.getByLabel('Medida').selectOption('area');
    await alta.getByRole('button', { name: 'Guardar trazo' }).click();
    await expect(page.getByRole('status')).toContainText('Trazo guardado');

    // Sin un área elegida la herramienta Hueco no se puede usar: primero se elige el área.
    const barra = page.getByRole('toolbar', { name: 'Herramientas de trazo' });
    await expect(barra.getByRole('button', { name: 'Hueco', exact: true })).toBeDisabled();
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    const muroGuardado = (await page.locator('.visor__trazo path').first().boundingBox())!;
    await page.mouse.click(muroGuardado.x + muroGuardado.width * 0.05, muroGuardado.y + muroGuardado.height * 0.5);
    await expect(page.getByText('Trazo elegido')).toBeVisible();
    await expect(barra.getByRole('button', { name: 'Hueco', exact: true })).toBeEnabled();

    // Abrir el hueco: la ventana. Enter lo cierra y el servidor lo resta del área.
    await barra.getByRole('button', { name: 'Hueco', exact: true }).click();
    const sobre = (fx: number, fy: number) => ({
      x: muroGuardado.x + muroGuardado.width * fx,
      y: muroGuardado.y + muroGuardado.height * fy,
    });
    for (const [fx, fy] of [[0.4, 0.3], [0.6, 0.3], [0.6, 0.7], [0.4, 0.7]] as const) {
      await page.mouse.click(sobre(fx, fy).x, sobre(fx, fy).y);
    }
    await expect(page.getByText(/Hueco: 4 vértices/)).toBeVisible();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('status')).toContainText('Hueco abierto');

    // El servidor lo guardó con dos anillos y midió el área ya descontada.
    const trazos = await llamarApi<{
      features: { geometry: { type: string; coordinates: [number, number][][] } }[];
    }>(request, 'residente', 'GET', `/planos/${plano.id}/trazos`);
    expect(trazos.features).toHaveLength(1); // el hueco no es un trazo más
    const [exterior, hueco] = trazos.features[0]!.geometry.coordinates as [[number, number][], [number, number][]];
    expect(trazos.features[0]!.geometry.type).toBe('Polygon');
    expect(hueco).toBeDefined();
    const area = (anillo: [number, number][]) => {
      let suma = 0;
      for (let i = 0; i < anillo.length - 1; i += 1) {
        suma += anillo[i]![0] * anillo[i + 1]![1] - anillo[i + 1]![0] * anillo[i]![1];
      }
      return Math.abs(suma) / 2;
    };
    const esperado = area(exterior) - area(hueco);
    const nodos = await llamarApi<{ nodo_id: string; cantidad_medida: string }[]>(
      request,
      'residente',
      'GET',
      `/obras/${obra.id}/cuantificacion`,
    );
    const medido = Number(nodos.find((n) => n.nodo_id === actividadId)!.cantidad_medida);
    expect(Math.abs(medido - esperado)).toBeLessThan(1e-6 * Math.max(1, esperado));
    expect(medido).toBeLessThan(area(exterior)); // el hueco sí se descontó

    // Un clic dentro de la ventana no elige el muro; uno en el muro, sí. Al guardar,
    // el visor se reencuadra al trazo, así que los puntos se calculan sobre lo que
    // se ve: la posición relativa del hueco dentro del muro, según lo que guardó el
    // servidor, aplicada a la caja del trazo en pantalla.
    await barra.getByRole('button', { name: 'Seleccionar', exact: true }).click();
    await page.keyboard.press('Escape');
    const xs = exterior.map((c) => c[0]);
    const ys = exterior.map((c) => c[1]);
    const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const centro = (anillo: [number, number][]) => [
      anillo.reduce((s2, c) => s2 + c[0], 0) / anillo.length,
      anillo.reduce((s2, c) => s2 + c[1], 0) / anillo.length,
    ] as const;
    const [hx, hy] = centro(hueco.slice(0, -1));
    const muro = (await page.locator('.visor__trazo path').first().boundingBox())!;
    await page.mouse.click(
      muro.x + muro.width * ((hx - minX) / (maxX - minX)),
      muro.y + muro.height * ((hy - minY) / (maxY - minY)),
    );
    await expect(page.getByText('Trazo elegido')).toHaveCount(0);
    await page.mouse.click(muro.x + muro.width * 0.05, muro.y + muro.height * 0.5);
    await expect(page.getByText('Trazo elegido')).toBeVisible();
  });
});
