# OpenShorts Mobile — Prototype v0.2 (fase 2)

PWA independiente para Safari/iOS. Esta versión incorpora un primer flujo de edición y exportación local basado en Canvas + MediaRecorder.

## Funciones
- Importar vídeo local desde Fotos/Archivos.
- Definir inicio y final del fragmento (máximo 90 s en esta fase).
- Recorte central tipo `cover` a 720 × 1280 (9:16).
- Superponer texto de gancho con ajuste básico de líneas.
- Previsualizar el fragmento.
- Exportar usando el primer formato de grabación que el navegador declare compatible; MP4 si Safari lo ofrece, de lo contrario WebM.
- Intentar conservar audio mediante Web Audio API. Si iOS bloquea o no permite la ruta de audio, la exportación puede quedar sin sonido.

## Límites conocidos
- Es un motor experimental de navegador, no el pipeline FFmpeg original.
- No hay todavía transcripción, detección de momentos virales, tracking facial, subtítulos automáticos ni integración Gemini/fal.ai.
- La exportación ocurre en tiempo real: un clip de 30 s puede tardar aproximadamente 30 s o más.
- Mantén Safari en primer plano y prueba primero con clips cortos. El iPhone puede detener procesos por memoria, temperatura o cambio de aplicación.
- La compatibilidad de códecs y la descarga debe validarse en el iPhone real. La aplicación usa detección de capacidades en tiempo de ejecución y no garantiza que todos los iPhone exporten igual.
- Los vídeos seleccionados usan URLs temporales locales; no se suben a ningún servidor en esta fase.

## Seguridad / siguiente arquitectura IA
No incluir claves Gemini, fal.ai ni ElevenLabs en JavaScript público. Para integrar proveedores de IA con seguridad se añadirá un servicio intermediario autenticado o una estrategia BYOK explícita, con límites y control de costes.

## Instalación de prueba
1. Descomprime el ZIP.
2. Publica los archivos en un alojamiento HTTPS estático.
3. Abre la dirección con Safari en el iPhone.
4. Compartir → Añadir a pantalla de inicio.
5. Prueba primero un clip de 15 segundos y verifica vídeo y audio exportados.
