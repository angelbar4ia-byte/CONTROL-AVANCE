/**
 * Piezas de formulario en campo (DESIGN_SYSTEM.md §3-§4, adaptado a táctil).
 *
 * Salieron de la pantalla de captura de la Fase 1: alta de incidencia,
 * revisión física y captura de avance pedían el mismo modal con los mismos
 * campos, y tenerlo tres veces garantizaba que un día el botón "Guardar" se
 * deshabilitara distinto en cada una. `h-fila` en todo lo tocable es el mismo
 * token de altura de fila de la web, que en móvil cae dentro del mínimo
 * táctil de 44 pt.
 */

import type { ReactNode } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from 'react-native';

import { TOKENS } from '@/lib/tabs';

/** Campo de texto con etiqueta. */
export function Campo({
  etiqueta,
  valor,
  onCambio,
  placeholder,
  editable = true,
  multilinea = false,
  numerico = false,
  autoFocus = false,
  testID,
}: {
  readonly etiqueta: string;
  readonly valor: string;
  readonly onCambio: (v: string) => void;
  readonly placeholder?: string;
  readonly editable?: boolean;
  readonly multilinea?: boolean;
  readonly numerico?: boolean;
  readonly autoFocus?: boolean;
  /**
   * Ancla para los flujos de Maestro (`mobile/e2e/`). Se pasa explícito y no
   * se deriva de `etiqueta` porque la etiqueta es texto de UI: cambiarla es
   * una decisión de redacción, y no debería romper una prueba.
   */
  readonly testID?: string;
}) {
  return (
    <View className="mt-3">
      <Text className="mb-1 text-sm text-text-soft">{etiqueta}</Text>
      <TextInput
        testID={testID}
        value={valor}
        onChangeText={onCambio}
        placeholder={placeholder}
        placeholderTextColor={TOKENS.textMute}
        editable={editable}
        autoFocus={autoFocus}
        multiline={multilinea}
        numberOfLines={multilinea ? 3 : 1}
        keyboardType={numerico ? 'decimal-pad' : 'default'}
        className={
          multilinea
            ? 'rounded-md border border-line bg-bg px-3 py-3 text-base text-text'
            : `h-fila rounded-md border border-line bg-bg px-3 text-base text-text ${
                numerico ? 'font-mono' : ''
              }`
        }
      />
    </View>
  );
}

/**
 * Selector de una opción entre pocas (tipo, impacto, calidad). Chips y no un
 * `Picker`: los enums del §8.2 tienen tres o cuatro valores y un desplegable
 * nativo esconde detrás de un toque lo que cabe en una línea.
 */
export function Opciones<T extends string>({
  etiqueta,
  opciones,
  valor,
  onCambio,
  deshabilitado = false,
}: {
  readonly etiqueta: string;
  readonly opciones: readonly { readonly valor: T; readonly texto: string }[];
  readonly valor: T;
  readonly onCambio: (v: T) => void;
  readonly deshabilitado?: boolean;
}) {
  return (
    <View className="mt-3">
      <Text className="mb-1 text-sm text-text-soft">{etiqueta}</Text>
      <View className="flex-row flex-wrap gap-2">
        {opciones.map((opcion) => {
          const activa = opcion.valor === valor;
          return (
            <Pressable
              key={opcion.valor}
              onPress={() => onCambio(opcion.valor)}
              disabled={deshabilitado}
              className={`rounded-full border px-3 py-2 active:opacity-70 disabled:opacity-50 ${
                activa ? 'border-accent bg-accent-soft' : 'border-line bg-surface'
              }`}
            >
              <Text className={`text-sm ${activa ? 'text-accent' : 'text-text-soft'}`}>
                {opcion.texto}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

/** Par de botones cancelar/confirmar al pie de un modal. */
export function Acciones({
  onCancelar,
  onConfirmar,
  textoConfirmar = 'Guardar',
  ocupado = false,
  deshabilitado = false,
}: {
  readonly onCancelar: () => void;
  readonly onConfirmar: () => void;
  readonly textoConfirmar?: string;
  readonly ocupado?: boolean;
  readonly deshabilitado?: boolean;
}) {
  return (
    <View className="mt-5 flex-row gap-3">
      <Pressable
        onPress={onCancelar}
        disabled={ocupado}
        className="h-fila flex-1 items-center justify-center rounded-md border border-line active:opacity-70"
      >
        <Text className="text-base text-text-soft">Cancelar</Text>
      </Pressable>
      <Pressable
        onPress={onConfirmar}
        disabled={ocupado || deshabilitado}
        className="h-fila flex-1 items-center justify-center rounded-md bg-accent active:opacity-80 disabled:opacity-60"
      >
        {ocupado ? (
          <ActivityIndicator color={TOKENS.surface} />
        ) : (
          <Text className="text-base font-medium text-accent-fg">{textoConfirmar}</Text>
        )}
      </Pressable>
    </View>
  );
}

/**
 * Modal de formulario. `ScrollView` adentro porque con el teclado abierto y
 * tres campos más el selector de fotos, el contenido no cabe en un teléfono
 * chico — y un botón "Guardar" fuera de pantalla es un formulario roto.
 */
export function Hoja({
  visible,
  titulo,
  subtitulo,
  onCerrar,
  children,
}: {
  readonly visible: boolean;
  readonly titulo: string;
  readonly subtitulo?: string;
  readonly onCerrar: () => void;
  readonly children: ReactNode;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCerrar}>
      <View className="flex-1 justify-center bg-scrim px-6">
        <View className="max-h-[85%] rounded-lg bg-surface p-5">
          <Text className="text-lg text-text">{titulo}</Text>
          {subtitulo ? <Text className="mt-1 font-mono text-sm text-text-mute">{subtitulo}</Text> : null}
          <ScrollView keyboardShouldPersistTaps="handled">{children}</ScrollView>
        </View>
      </View>
    </Modal>
  );
}

/**
 * Mensaje de error del formulario. Se llama `Aviso` y no `Error` para no
 * sombrear el `Error` global en cada módulo que lo importe — un `catch` que
 * hiciera `e instanceof Error` compararía contra un componente de React.
 */
export function Aviso({ mensaje }: { readonly mensaje: string | null }) {
  if (!mensaje) return null;
  return <Text className="mt-2 text-sm text-danger">{mensaje}</Text>;
}

/** Estado vacío de una lista. */
export function Vacio({ texto }: { readonly texto: string }) {
  return <Text className="mt-8 text-md text-text-mute">{texto}</Text>;
}

/** Spinner centrado mientras carga una consulta local. */
export function Cargando() {
  return (
    <View className="mt-10 items-center">
      <ActivityIndicator color={TOKENS.accent} />
    </View>
  );
}
