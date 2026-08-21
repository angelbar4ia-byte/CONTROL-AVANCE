/**
 * Bandeja de cierres del Supervisor (§5.2, §11.3 C.2).
 *
 * ## La única pantalla del móvil que exige señal, y por qué
 *
 * Todo lo demás en esta app lee la réplica local. Esta no puede: las
 * solicitudes de cierre **no están** en el esquema de PowerSync
 * (`sync/powersync.ts`), y no están por decisión. Bajar `solicitud_cierre` a
 * cada teléfono significaría bajar también su checklist, sus adjuntos y su
 * monto —el documento con el que se cobra (§11.3 C, E)— a un dispositivo que
 * solo lo consulta, y sostener offline una máquina de estados de tres pasos
 * con dos roles distintos autorizándola.
 *
 * Y autorizar sin red no serviría de todos modos: autorizar **cierra la
 * actividad** y habilita la estimación, así que el efecto solo existe cuando
 * llega al servidor. Una autorización encolada le diría al supervisor que ya
 * cerró algo que sigue abierto para todos los demás.
 *
 * Entonces se dice: sin señal, esta pantalla muestra que no hay señal. Es la
 * misma honestidad del indicador de sync, aplicada a una pantalla entera.
 *
 * Rechazar sí es reversible —el residente vuelve a solicitar— pero viaja por
 * el mismo camino: no vale la pena una ruta offline para la mitad de un flujo.
 */

import { useState } from 'react';
import { FlatList, Pressable, RefreshControl, Text, View } from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiNoConfigurada, ErrorDeApi, pedir, SinConexion } from '@/lib/api';
import { generarId } from '@/lib/id';
import { Encabezado } from '@/ui/Encabezado';
import { Acciones, Aviso, Campo, Cargando, Hoja, Opciones, Vacio } from '@/ui/Formulario';

interface Cierre {
  readonly id: string;
  readonly actividad_id: string;
  readonly cantidad: number;
  readonly monto: number;
  readonly checklist: readonly unknown[];
  readonly adjuntos: readonly string[];
  readonly comentarios: string | null;
  readonly estatus: string;
}

const ETIQUETA_ESTATUS: Readonly<Record<string, string>> = {
  solicitada: 'Solicitada',
  autorizada: 'Autorizada',
  validada: 'Validada',
  rechazada: 'Rechazada',
};

export function Cierres() {
  const cliente = useQueryClient();
  const [enAccion, setEnAccion] = useState<Cierre | null>(null);

  const {
    data: cierres,
    isLoading,
    isRefetching,
    error,
    refetch,
  } = useQuery({
    queryKey: ['cierres', 'solicitada'],
    // `networkMode` global es `offlineFirst` (§12.5), pensado para las
    // pantallas que leen SQLite. Aquí no hay caché local que valga: sin red
    // no hay bandeja, y decirlo es mejor que mostrar una lista vieja como si
    // fuera la de hoy.
    networkMode: 'online',
    queryFn: () => pedir<Cierre[]>('/api/v1/cierres?estatus=solicitada'),
  });

  const accion = useMutation({
    mutationFn: async ({
      cierre,
      tipo,
      motivo,
    }: {
      cierre: Cierre;
      tipo: 'autorizar' | 'rechazar';
      motivo: string;
    }) =>
      pedir(`/api/v1/cierres/${cierre.id}/${tipo}`, {
        metodo: 'POST',
        cuerpo: tipo === 'rechazar' ? { motivo } : {},
        // Autorizar mueve dinero (§11.3 C, E): un doble toque no puede
        // convertirse en dos autorizaciones. La clave se genera por intento
        // del usuario, no por reintento de red.
        idempotencia: generarId(),
      }),
    onSuccess: () => {
      setEnAccion(null);
      void cliente.invalidateQueries({ queryKey: ['cierres'] });
    },
  });

  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Encabezado
        eyebrow="Supervisor"
        titulo="Cierres"
        descripcion="Autoriza o rechaza lo que solicitó el residente (§11.3 C.2)."
      />

      {isLoading ? (
        <Cargando />
      ) : error ? (
        <ErrorDeBandeja causa={error} onReintentar={() => void refetch()} />
      ) : (
        <FlatList
          data={cierres}
          keyExtractor={(item) => item.id}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => void refetch()} />}
          ListEmptyComponent={<Vacio texto="No hay solicitudes de cierre esperando tu autorización." />}
          renderItem={({ item }) => (
            <Pressable
              onPress={() => setEnAccion(item)}
              className="mb-3 rounded-lg border border-line bg-surface p-4 active:opacity-70"
            >
              <View className="flex-row items-start justify-between gap-3">
                <Text className="flex-1 font-mono text-xs text-text-faint">{item.actividad_id}</Text>
                <Text className="text-xs text-text-mute">
                  {ETIQUETA_ESTATUS[item.estatus] ?? item.estatus}
                </Text>
              </View>

              <View className="mt-2 flex-row items-center justify-between">
                <Text className="font-mono text-sm text-text-mute">Cantidad {item.cantidad}</Text>
                <Text className="font-mono text-lg text-text">{pesos(item.monto)}</Text>
              </View>

              <Text className="mt-2 text-xs text-text-mute">
                {item.checklist.length} puntos de checklist · {item.adjuntos.length} evidencias
              </Text>
            </Pressable>
          )}
        />
      )}

      <FormularioAccion
        cierre={enAccion}
        ocupado={accion.isPending}
        errorEnvio={accion.error}
        onCerrar={() => setEnAccion(null)}
        onConfirmar={(cierre, tipo, motivo) => accion.mutate({ cierre, tipo, motivo })}
      />
    </View>
  );
}

/** MXN (§3.5). Se formatea aquí y no en el servidor: es presentación. */
function pesos(monto: number): string {
  return new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(monto);
}

/**
 * El error se traduce a una causa accionable. "Sin conexión" y "el servidor
 * dijo que no" piden cosas distintas del usuario, y un mensaje único los
 * confundiría en el peor momento.
 */
function ErrorDeBandeja({
  causa,
  onReintentar,
}: {
  readonly causa: unknown;
  readonly onReintentar: () => void;
}) {
  const mensaje =
    causa instanceof SinConexion
      ? 'Esta bandeja necesita señal: las solicitudes de cierre no se guardan en el dispositivo.'
      : causa instanceof ApiNoConfigurada
        ? 'Este build no tiene configurada la URL de la API (EXPO_PUBLIC_API_URL).'
        : causa instanceof ErrorDeApi
          ? causa.message
          : 'No se pudo cargar la bandeja.';

  return (
    <View className="mt-8 rounded-lg border border-line bg-surface p-4">
      <Text className="text-base text-text">No hay bandeja ahora</Text>
      <Text className="mt-2 text-sm text-text-mute">{mensaje}</Text>
      <Pressable
        onPress={onReintentar}
        className="mt-4 h-fila items-center justify-center rounded-md border border-line active:opacity-70"
      >
        <Text className="text-base text-text-soft">Reintentar</Text>
      </Pressable>
    </View>
  );
}

const OPCIONES = [
  { valor: 'autorizar', texto: 'Autorizar' },
  { valor: 'rechazar', texto: 'Rechazar' },
] as const;

type Tipo = (typeof OPCIONES)[number]['valor'];

function FormularioAccion({
  cierre,
  ocupado,
  errorEnvio,
  onCerrar,
  onConfirmar,
}: {
  readonly cierre: Cierre | null;
  readonly ocupado: boolean;
  readonly errorEnvio: unknown;
  readonly onCerrar: () => void;
  readonly onConfirmar: (cierre: Cierre, tipo: Tipo, motivo: string) => void;
}) {
  const [tipo, setTipo] = useState<Tipo>('autorizar');
  const [motivo, setMotivo] = useState('');
  const [error, setError] = useState<string | null>(null);

  function confirmar() {
    if (!cierre) return;
    if (tipo === 'rechazar' && !motivo.trim()) {
      setError('Rechazar exige un motivo (§11.3 C).');
      return;
    }
    setError(null);
    onConfirmar(cierre, tipo, motivo.trim());
  }

  return (
    <Hoja
      visible={cierre !== null}
      titulo={tipo === 'autorizar' ? 'Autorizar cierre' : 'Rechazar cierre'}
      subtitulo={cierre ? `${pesos(cierre.monto)} · cantidad ${cierre.cantidad}` : undefined}
      onCerrar={onCerrar}
    >
      <Opciones
        etiqueta="Decisión"
        opciones={OPCIONES}
        valor={tipo}
        onCambio={setTipo}
        deshabilitado={ocupado}
      />

      {tipo === 'autorizar' ? (
        <Text className="mt-3 text-sm text-text-mute">
          Autorizar cierra la actividad y la habilita para estimación (§11.3 C.2). No se puede deshacer
          desde el teléfono.
        </Text>
      ) : (
        <Campo etiqueta="Motivo" valor={motivo} onCambio={setMotivo} editable={!ocupado} multilinea />
      )}

      <Aviso mensaje={error ?? mensajeDeEnvio(errorEnvio)} />
      <Acciones
        onCancelar={onCerrar}
        onConfirmar={confirmar}
        ocupado={ocupado}
        textoConfirmar={tipo === 'autorizar' ? 'Autorizar' : 'Rechazar'}
      />
    </Hoja>
  );
}

function mensajeDeEnvio(causa: unknown): string | null {
  if (!causa) return null;
  if (causa instanceof SinConexion) return 'Sin señal: esta acción necesita servidor.';
  if (causa instanceof ErrorDeApi) return causa.message;
  return 'No se pudo registrar la decisión.';
}
