# 03 — Especificación de requerimientos del casino (versión del grupo)

> **Fuente:** "Especificación de requerimientos del casino", Administración de Bases de Datos, periodo 2026-3. Autores: Juan David Garrido Ramos, Andrés Felipe Torres Monroy y Alejandro Urbina.
> **Propósito de este archivo:** roles, permisos, casos de uso y funcionalidades que la aplicación debe implementar. Las reglas `RN-xx` citadas están en `02-contexto-casino.md`.

## 1. Descripción general

Sistema para gestionar jugadores, mesas, turnos, rondas, apuestas, ganancias, suspensiones y consignaciones/retiros. Debe garantizar que:

- Solo participen jugadores registrados y mayores de edad.
- Las apuestas respeten el mínimo/máximo de la mesa y el saldo del jugador.
- A cada mesa solo se asignen crupieres y supervisores que conozcan su juego.
- Un crupier no atienda más de una mesa por turno ni repita mesa en la misma jornada.
- Los jugadores Suspendidos o en Investigación no puedan apostar.

## 2. Roles y permisos

### Administrador
- Gestionar mesas y empleados.
- Registrar nuevos usuarios (administradores, supervisores, crupieres).
- Asignar/actualizar los juegos que conoce cada crupier y supervisor.
- Asignar a cada mesa un crupier y un supervisor por turno; definir la duración de los turnos de cada día.
- Configurar el umbral diario de pérdidas de los jugadores.

### Supervisor
- Verificar que el crupier de su mesa no haga trampa.
- Emitir al final de cada turno el concepto del crupier (`Genera ganancias` | `Genera pérdidas` | `Sospecha de fraude` | `Comportamiento neutro`).

### Crupier
- Atender la mesa asignada durante su turno.
- Registrar las rondas de su mesa y las apuestas de los jugadores presentes.
- Ingresar el resultado ganador de cada ronda.

### Jugador
- Registrarse con código único de cliente, documento, nombre completo, edad y saldo en fichas.
- Realizar una o más apuestas en rondas de la mesa donde está presente.
- Solicitar voluntariamente una pausa (autoexclusión).
- Los empleados también pueden jugar como jugadores (reglas de la sección 3.5).

### Matriz rápida de acceso

| Funcionalidad | Admin | Supervisor | Crupier | Jugador |
|---|:-:|:-:|:-:|:-:|
| CRUD mesas | ✔ | | | |
| CRUD empleados / competencias | ✔ | | | |
| Definir turnos y asignaciones | ✔ | | | |
| Configurar umbral de pérdidas | ✔ | | | |
| Emitir concepto del crupier | | ✔ | | |
| Abrir/cerrar rondas, ingresar resultado | | | ✔ | |
| Registrar apuestas | | | ✔ | (ver nota) |
| Solicitar autoexclusión | | | | ✔ |
| Ver saldo, historial, notificaciones propias | | | | ✔ |
| Consignaciones/retiros | ✔ (registro) | | | ✔ (solicitud) |

### Roles en Django

- Modelar los 4 roles como **Groups** de `django.contrib.auth` (`Administrador`, `Supervisor`, `Crupier`, `Jugador`) o como un campo `rol` en el usuario; elegir uno y no mezclar.
- Proteger cada vista con un decorador/mixin por rol (p. ej. `@rol_requerido('Crupier')` propio, o `UserPassesTestMixin` en vistas basadas en clase). Nunca confiar solo en ocultar botones.
- La navegación de la plantilla base (`base.html`) se arma según el rol del usuario en sesión, para cumplir "mostrar únicamente las funcionalidades permitidas".
- Una persona que es empleado y jugador a la vez puede tener ambos roles; la interfaz debe permitirle cambiar de contexto.
- El admin de Django (`/admin/`) puede usarse como apoyo para el rol Administrador, pero la funcionalidad obligatoria debe existir en la interfaz propia del sistema.

> Nota: según el enunciado, quien **registra** las apuestas es el crupier; el jugador las "realiza". Decidir si el jugador también puede registrarlas desde su interfaz y documentarlo. Las filas de consignaciones/retiros son una propuesta, el enunciado no fija quién las registra.

## 3. Casos de uso

### 3.1 Gestión de mesas (Administrador)
- CRUD de mesas; asignar crupier y supervisor por turno.
- Cada mesa: id único, tipo de juego, monto mínimo y máximo.
- Validaciones: competencia en el juego (RN-15), un crupier una mesa por turno (RN-07), no repetir mesa en la jornada (RN-09), turno ≤ 2 h (RN-10).
- Al final del turno, el supervisor registra su concepto (RN-12, RN-13).

### 3.2 Gestión de rondas (Crupier)
- Cada ronda: mesa, número correlativo, hora inicio, hora cierre.
- Durante la ronda se aceptan una o más apuestas por jugador.
- Al ingresar el resultado, el sistema procesa automáticamente todas las apuestas de la ronda (ver 3.4).

### 3.3 Gestión de apuestas (Crupier)
- Registro detallado: jugador, ronda, tipo de apuesta, monto, factor de pago.
- Validar estrictamente `monto_minimo ≤ monto ≤ monto_maximo` y saldo suficiente.
- Sin registro detallado (póker): registrar solo al evidenciarse el resultado.
- Al procesar: coincide → **Ganada**; no coincide → **Perdida** (monto a favor del casino).
- Jugador **Suspendido** o en **Investigación** no puede apostar.

### 3.4 Gestión de ganancias (automático)
- Premio = `monto_apostado × factor_pago`, acreditado de inmediato al saldo.
- Monto de apuesta perdida se consolida a favor del casino.
- Acumular pérdidas y ganancias por jugador (insumo de 3.5).

### 3.5 Gestión de suspensiones (automático)
- Pérdidas del día > umbral → **Suspendido** 24 h.
- Pausa voluntaria → **Suspendido** 24 h.
- Empleado con pérdidas > 2 salarios → **Suspendido**; se reactiva solo cuando la deuda baja del límite.
- Empleado con ganancias > 1 salario → **Investigación** hasta que se cierre la investigación.

### 3.6 Gestión de consignaciones y retiros
- Cada movimiento: jugador, tipo (consignación | retiro), monto en fichas, fecha.
- Un retiro no puede superar el saldo disponible.

## 4. Funcionalidades adicionales

1. **Notificaciones:** avisar al jugador cuando su cuenta pase a Suspendido o Investigación.
2. **Gestión de empleados:** el administrador registra y gestiona empleados, incluyendo salario y juegos que conocen.
3. **Historial de clientes:** por jugador, sus apuestas, ganancias, consignaciones, retiros y cambios de estado.
4. **Validación de autorizaciones y suspensiones:**
   - Crupieres y supervisores asignados conocen el juego de la mesa.
   - Antes de cada apuesta, el jugador no está Suspendido ni en Investigación.
   - Al registrar un jugador, no es menor de edad.
5. **Interfaz de usuario (obligatoria):** interfaz intuitiva por rol que muestre únicamente lo permitido a ese rol.

## Estados

- **Cuenta del jugador:** `Activo` → `Suspendido` (con o sin fecha de fin) | `Investigación`. Volver a `Activo` al vencer las 24 h, al bajar la deuda del empleado o al cerrar la investigación.
- **Apuesta:** `Pendiente` → `Ganada` | `Perdida`.
- **Concepto del supervisor:** `Genera ganancias` | `Genera pérdidas` | `Sospecha de fraude` | `Comportamiento neutro`.
