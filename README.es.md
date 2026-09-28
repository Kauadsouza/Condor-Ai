# Condor AI

[English](README.md) · [Português](README.pt-BR.md) · **Español**

Un sistema de IA personal que se ejecuta **en el ordenador de su dueño**, con una identidad persistente, memoria cifrada y control explícito sobre cada capacidad sensible.

No es una envoltura alrededor de un modelo. Los modelos locales, OpenAI y Claude son motores intercambiables; lo que permanece es la identidad, la política de memoria, los permisos y la interfaz.

---

## Por qué existe

Un asistente de IA alojado por un tercero tiene un problema estructural: su memoria es de otra persona. Conversas durante meses y ese historial — quién eres, qué ya explicaste, qué decidiste — vive en un servidor que puede cambiar de reglas, de precio o de dueño.

Condor invierte eso. La memoria se queda cifrada en el disco del dueño; el modelo es la pieza sustituible.

## Principios de diseño

- **Una sola mente:** PC, visor móvil y el acompañante opcional en la nube son interfaces de la misma identidad canónica.
- **Propiedad local:** el estado privado queda bajo control del dueño y nunca se versiona junto al código.
- **Automatización que falla cerrada:** las acciones sobre el ordenador, los archivos y los dispositivos físicos pasan por política y aprobación explícita.
- **Independencia del modelo:** el núcleo determinista sigue funcionando sin API de pago.
- **Seguridad inspeccionable:** cifrado, verificación de integridad, encadenamiento de auditoría y vías de recuperación están documentados y probados.

## Capacidades

- Núcleo FastAPI atado a `127.0.0.1`, con interfaz de escritorio propia.
- Caja fuerte e instantánea de memoria cifradas con **AES-256-GCM**, clave derivada con **scrypt**.
- Hechos, conversaciones, tareas, estado de proyecto y borradores versionados que persisten.
- Identidad estable `condor-core-identity-v1` por encima del enrutador de modelos.
- Conectores Local, OpenAI y Claude seleccionables, con redacción de secretos.
- Voz local, palabra de activación opcional, visión por ordenador solo para autenticación y generación privada de imágenes.
- Herramientas con permisos acotados para archivos, aplicaciones, investigación y desarrollo.
- Visor móvil **de solo lectura** en la red privada, sin rutas de comando, memoria ni caja fuerte.
- Condor X: espacio experimental de diseño 3D y simulación de ingeniería acotada.
- Base opcional de PWA (`cloud/`) para conversación, notas y memoria cifradas con el PC apagado.

## Copia de seguridad: la única parte insustituible

El código vuelve con un `git clone`. La **memoria, la identidad y la caja fuerte no**: existen solo en `~/.condor`, en esta máquina.

Por eso la copia está automatizada, y no es una buena intención:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_backup_task.ps1
```

Pregunta la carpeta de destino, pide la frase secreta **una sola vez** y programa una ejecución diaria más otra cinco minutos después de cada inicio de sesión, para los días en que el PC estaba apagado a la hora prevista.

La frase queda protegida por DPAPI de Windows, legible solo por esta cuenta en esta máquina. **El archivo de copia sigue siendo portátil:** se abre con la frase en cualquier ordenador, que es justamente el objetivo si esta máquina muere. Se conservan las catorce más recientes.

Probar la restauración forma parte del procedimiento, porque una copia que nadie ha restaurado es una esperanza, no una copia:

```powershell
powershell -File scripts\restore_condor_data.ps1 -BackupFile "<archivo.enc>" -CondorHome "$env:TEMP\prueba-restauracion"
```

## Frontera de seguridad

El núcleo completo debe permanecer solo en loopback. **Nunca expongas el puerto `7777` a internet.** El visor móvil corre como proceso y puerto separados, está restringido a redes privadas, exige emparejamiento y devuelve solo datos saneados de lectura.

Secretos, plantillas biométricas, memoria, configuración, registros y archivos del usuario viven fuera del repositorio, en `~/.condor` por defecto. El repositorio restaura la aplicación, pero no ese estado privado. Nunca publiques ni recrees un `~/.condor` existente al publicar el código.

Lee el [modelo de seguridad](SECURITY.md), la [arquitectura](ARCHITECTURE.md) y la [guía de operación](OPERATIONS.md).

## Arquitectura de un vistazo

```text
Interfaz de escritorio / voz / proyectos locales
                |
           Núcleo FastAPI local
                |
   identidad + política + memoria cifrada
        /           |             \
 determinista   modelo local   APIs opcionales

Fronteras separadas:
- visor móvil de solo lectura
- base del acompañante en la nube, cifrada
```

## Instalación en Windows

Requiere Python 3.11 o superior.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_new_windows_pc.ps1
```

Instalación manual:

```powershell
.\scripts\install.ps1
.\scripts\install_local_ai.ps1
.\scripts\run.ps1
```

Las descargas iniciales de modelos pueden ser grandes. Después, los modelos locales configurados funcionan sin cuenta de IA externa.

## Verificación

```powershell
.\.venv\Scripts\python.exe testes\rodar_testes.py
.\.venv\Scripts\python.exe scripts\doctor.py
```

La suite cubre política, cifrado de la caja fuerte, memoria, identidad, enrutamiento de proveedores, fronteras de interfaz, seguridad de dispositivos y las reglas de simulación de Condor X — **sin necesitar API de pago**. Con 114 pruebas, es el repositorio mejor cubierto del conjunto.

El acompañante en la nube se verifica aparte:

```powershell
Set-Location cloud
npm.cmd install
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
```

## Mapa del repositorio

```text
condor/        Núcleo, memoria, seguridad, dispositivos, interfaz y motores de proyecto
cloud/         Base opcional del acompañante PWA cifrado
deploy/        Ejemplos de despliegue en red privada
scripts/       Instalación, diagnóstico, copia de seguridad y ejecución local
testes/        Suite de regresión de seguridad y comportamiento
windows/       Identidad del lanzador nativo de Windows
```

## Estado, sin maquillaje

Condor es un sistema personal de I+D en uso, no un asistente de consumo terminado. La operación local en el PC y las fronteras de seguridad probadas están implementadas. El acompañante en la nube es una base que aún necesita infraestructura propia, autenticación real y validación de extremo a extremo. Las herramientas de Condor X son prototipos y simulaciones: no afirman rendimiento físico validado.

## Licencia

Proyecto de portafolio con código visible y propietario. La visibilidad pública no concede permiso para copiar, redistribuir ni comercializar.

Creado y mantenido por [Kauã Diniz Souza](https://github.com/Kauadsouza).
