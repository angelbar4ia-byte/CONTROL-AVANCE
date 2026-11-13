/** El área de trabajo de la pestaña «Artefacto»: aquí vivirán los tipos de muro y sus plantillas. Todavía sin contenido. */

export function PantallaDeArtefacto() {
  return (
    <section className="pantalla-elementos pantalla-elementos--vacia" role="tabpanel" id="area-artefacto" aria-label="Artefacto">
      <div className="empty">
        <div className="empty-title">Artefacto</div>
        <div className="empty-sub">
          Aquí se definirán los tipos de muro y sus plantillas: qué elementos lleva cada muro y con qué conceptos se paga. Por ahora
          está vacío; el muro de contención de piedra se ve en la pestaña Elementos.
        </div>
      </div>
    </section>
  );
}
