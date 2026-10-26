import {
  cerrarPorApi,
  entrarComo,
  expect,
  hayRoles,
  motivoSinRoles,
  test,
  type Rol,
} from '../infraestructura';

/**
 * §11.3 D · Cierre de obra final (el acta de entrega).
 *
 *  1. Super intendente abre el cierre y ve lo que **impide entregar**.
 *  2. Se concluye el trabajo pendiente.
 *  3. Los cuatro roles registran su parte: residente entrega, supervisor da su
 *     visto bueno, control responde por calidad y expediente, y el super
 *     intendente firma.
 *  4. Con las cuatro partes, la obra queda **entregada** y se congela.
 *
 * ## Lo que este spec no cubre
 *
 * La revisión física que alimenta el expediente entra por la app móvil (§5.2),
 * así que aquí no se prueba. El panel avisa que el expediente está vacío
 * («Conviene revisarlos»), pero eso **no impide** firmar y es lo que se verifica:
 * que el cierre exija el trabajo concluido y no el acervo.
 *
 * ## El avance de la obra se deriva solo
 *
 * `OBRA-D` arranca en 0 %. El avance de la obra lo calcula la base a partir del
 * de sus actividades (migración 0064): al concluir las dos, la obra llega a
 * 100 % sin que nadie lo ponga, y eso es lo que se verifica. Antes de esa
 * migración nada lo calculaba y la regla `avance_incompleto` frenaba la entrega
 * para siempre.
 *
 * Usa `OBRA-D` de `e2e/soporte/semilla.sql`; es de un solo uso.
 */

const ROLES_D = ['residente', 'supervisor', 'control', 'superIntendente'] as const;

test.describe('§11.3 D · Cierre de obra', () => {
  test.skip(!hayRoles(...ROLES_D), motivoSinRoles(...ROLES_D));

  test.use({ viewport: { width: 1440, height: 900 } });
  // Cuatro sesiones y el preparativo por API: sobra el tope de 30 s por defecto.
  test.setTimeout(90_000);

  test('el acta exige el trabajo concluido y las cuatro partes', async ({ browser, request }) => {
    const sesion = async (rol: Rol) => {
      const pagina = await (
        await browser.newContext({ viewport: { width: 1440, height: 900 } })
      ).newPage();
      await entrarComo(pagina, rol);
      await pagina.goto('/cierres-obra');
      return pagina;
    };
    const filaObra = (pagina: Awaited<ReturnType<typeof sesion>>) =>
      pagina.getByRole('row', { name: /^OBRA-D/ });

    // --- 1. Super intendente abre el cierre; ve lo que impide entregar ---
    const superIntendente = await sesion('superIntendente');
    await superIntendente.getByLabel('Obra').selectOption({ label: 'OBRA-D' });
    await superIntendente.getByRole('button', { name: 'Abrir cierre' }).click();

    // Abrir el cierre abre el acta: ahí está lo que impide entregar.
    const acta = superIntendente.getByRole('dialog', { name: 'Cierre de obra' });
    await expect(acta).toContainText('Impiden entregar');
    await expect(acta).toContainText('2 actividad(es) sin concluir');
    await expect(acta).toContainText('La obra va en 0.00 % de avance');
    await acta.getByLabel('Cerrar', { exact: true }).click();

    await superIntendente.getByRole('button', { name: 'Todos', exact: true }).click();
    await expect(filaObra(superIntendente)).toContainText('En proceso');

    // --- 2. Se concluye el trabajo --------------------------------------
    await cerrarPorApi(request, 'OBRA-D', 'E2E-EXC', 10);
    await cerrarPorApi(request, 'OBRA-D', 'E2E-PLA', 10);

    // La obra llegó a 100 % sola, y de ahí se deriva su estatus (>= 90).
    await superIntendente.reload();
    await superIntendente.getByRole('button', { name: 'Todos', exact: true }).click();
    await expect(filaObra(superIntendente)).toContainText('por_entregar');

    // --- 3. Los cuatro roles registran su parte -------------------------
    const partes: { rol: Rol; etiqueta: string; comentario: string }[] = [
      { rol: 'residente', etiqueta: 'entrega', comentario: 'Obra limpia y entregada' },
      { rol: 'supervisor', etiqueta: 'visto bueno', comentario: 'Visto bueno del supervisor' },
      { rol: 'control', etiqueta: 'calidad y expediente', comentario: 'Calidad conforme' },
    ];

    for (const parte of partes) {
      const pagina = await sesion(parte.rol);
      await pagina.getByRole('button', { name: 'Todos', exact: true }).click();
      await filaObra(pagina).getByRole('button', { name: 'Abrir' }).click();
      const panel = pagina.getByRole('dialog', { name: 'Cierre de obra' });
      await panel.getByRole('textbox', { name: `Tu parte: ${parte.etiqueta}` }).fill(parte.comentario);
      await panel.getByRole('button', { name: 'Registrar mi parte' }).click();
      await expect(panel.getByRole('row', { name: new RegExp(parte.comentario) })).toBeVisible();
    }

    // Con tres de cuatro partes la obra todavía no se entrega.
    await superIntendente.reload();
    await superIntendente.getByRole('button', { name: 'Todos', exact: true }).click();
    await expect(filaObra(superIntendente)).not.toContainText('Entregada');

    // --- 4. Firma el super intendente: la obra queda entregada -----------
    await filaObra(superIntendente).getByRole('button', { name: 'Abrir' }).click();
    const firma = superIntendente.getByRole('dialog', { name: 'Cierre de obra' });
    await expect(firma).not.toContainText('Impiden entregar');
    await firma.getByRole('textbox', { name: 'Tu parte: firma' }).fill('Obra entregada');
    await firma.getByRole('button', { name: 'Registrar mi parte' }).click();

    await superIntendente.reload();
    await superIntendente.getByRole('button', { name: 'Entregadas' }).click();
    await expect(filaObra(superIntendente)).toContainText('entregada');
  });
});
