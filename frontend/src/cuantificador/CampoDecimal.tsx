/**
 * Un número en metros que se escribe con punto: guarda **lo que se teclea** («0.», «.5», «1,2») y solo avisa el número
 * cuando es válido. Si el campo se pintara siempre desde el número, «0.» volvería a «0» en cada tecla y el punto no se
 * podría escribir.
 */

import { useEffect, useRef, useState } from 'react';

import { numeroTecleado } from './volumen';

interface Props {
  readonly etiqueta: string;
  readonly valor: number;
  readonly onValor: (n: number) => void;
  readonly className?: string;
  readonly ancho?: number;
}

export function CampoDecimal({ etiqueta, valor, onValor, className, ancho = 70 }: Props) {
  const [texto, setTexto] = useState(String(valor));
  const editando = useRef(false);
  // Si el valor cambia desde fuera (un botón de valores usuales), el campo lo muestra; lo tecleado que ya lo representa se respeta.
  // Mientras se está escribiendo no se reescribe: un valor derivado de otros campos no debe pisar lo que se teclea ni rellenar el campo
  // recién borrado.
  useEffect(() => {
    if (!editando.current && numeroTecleado(texto) !== valor) setTexto(String(valor));
  }, [valor]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <input
      aria-label={etiqueta}
      className={className}
      inputMode="decimal"
      style={className ? undefined : { width: ancho }}
      value={texto}
      onChange={(e) => {
        const nuevo = e.target.value;
        if (!/^[0-9]*[.,]?[0-9]*$/.test(nuevo)) return; // solo dígitos y un punto o coma
        setTexto(nuevo);
        onValor(numeroTecleado(nuevo));
      }}
      onFocus={() => {
        editando.current = true;
      }}
      onBlur={() => {
        editando.current = false;
        setTexto(String(valor));
      }}
    />
  );
}
