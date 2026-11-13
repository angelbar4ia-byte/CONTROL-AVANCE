/**
 * El panel izquierdo de la pestaña «Elementos»: la biblioteca plegable por categoría y subcategoría. El elemento que
 * se elige aquí se ve en el área de trabajo (derecha), que así queda solo para su tarjeta.
 */

import { useBibliotecaDeElementosApiV1BibliotecaDeElementosGet } from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';

import { BibliotecaDeElementos } from './BibliotecaDeElementos';

interface Props {
  readonly elegida: string | null;
  readonly onElegir: (clave: string) => void;
}

export function PanelDeBiblioteca({ elegida, onElegir }: Props) {
  const consulta = useBibliotecaDeElementosApiV1BibliotecaDeElementosGet();
  if (consulta.isLoading)
    return (
      <p className="text-mute text-sm" style={{ padding: 10 }}>
        Cargando la biblioteca…
      </p>
    );
  if (consulta.isError)
    return (
      <p className="text-sm" style={{ padding: 10 }} role="alert">
        No se pudo cargar la biblioteca de elementos.
      </p>
    );
  return <BibliotecaDeElementos categorias={consulta.data ?? []} elegida={elegida} onElegir={onElegir} />;
}
