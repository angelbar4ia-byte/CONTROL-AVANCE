/** El área de trabajo de la pestaña «Paramétrico»: aquí vivirán los parámetros globales de la obra. Todavía sin contenido. */

export function PantallaParametrica() {
  return (
    <section className="pantalla-elementos pantalla-elementos--vacia" role="tabpanel" id="area-parametrico" aria-label="Paramétrico">
      <div className="empty">
        <div className="empty-title">Paramétrico</div>
        <div className="empty-sub">
          Aquí se ajustarán los valores que comparten los elementos de la obra (por ejemplo, la altura estándar de los muros). Por ahora
          está vacío.
        </div>
      </div>
    </section>
  );
}
