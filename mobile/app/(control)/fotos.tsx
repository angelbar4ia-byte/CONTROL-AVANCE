import { View } from 'react-native';

import { Encabezado } from '@/ui/Encabezado';

export default function Pantalla() {
  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Encabezado
        eyebrow="Control de obra"
        titulo="Fotos"
        descripcion="Evidencias; suben directo a R2 en segundo plano (§12.5)."
      />
    </View>
  );
}
