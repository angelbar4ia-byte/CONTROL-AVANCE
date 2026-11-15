import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { afterEach, describe, expect, it } from 'vitest';

import { CampoDecimal } from './CampoDecimal';

/**
 * Regresión de «escribe 2.1 y queda 1.22» (zy-vano-decimales): el campo derivado (Cerramiento CE = altura + antepecho) se
 * reescribía con un efecto pasivo que corría al enfocarlo. Aquí el valor externo cambia con `flushSync` (los efectos pasivos
 * quedan pendientes, como con la máquina cargada) y se enfoca el campo enseguida.
 */

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const contenedores: HTMLElement[] = [];
afterEach(() => {
  contenedores.splice(0).forEach((c) => c.remove());
});

function montar(valor: number) {
  const c = document.createElement('div');
  document.body.appendChild(c);
  contenedores.push(c);
  const raiz = createRoot(c);
  const recibido: number[] = [];
  const pintar = (v: number) => <CampoDecimal etiqueta="CE" valor={v} onValor={(n) => recibido.push(n)} />;
  act(() => raiz.render(pintar(valor)));
  const input = c.querySelector('input') as HTMLInputElement;
  return { raiz, pintar, input, recibido };
}

describe('CampoDecimal', () => {
  it('muestra el valor que llega de fuera en el mismo commit, sin esperar a un efecto', () => {
    const { raiz, pintar, input } = montar(1.2);
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;
    try {
      flushSync(() => raiz.render(pintar(1.7)));
      expect(input.value).toBe('1.7');
    } finally {
      (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    }
  });

  it('enfocar justo después de un cambio externo no deja texto viejo para que lo tecleado se le agregue', () => {
    const { raiz, pintar, input, recibido } = montar(1.2);
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = false;
    try {
      flushSync(() => raiz.render(pintar(1.7)));
      input.focus();
      // Quien escribe vacía el campo y teclea 2.6: el texto es exactamente lo tecleado.
      const poner = (v: string) => {
        const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
        set.call(input, v);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      };
      poner('');
      poner('2');
      poner('2.');
      poner('2.6');
      expect(input.value).toBe('2.6');
      expect(recibido.at(-1)).toBe(2.6);
    } finally {
      (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    }
  });
});
