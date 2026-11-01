# 02 — Contexto del dominio: Casino de apuestas y mesas de juego

> **Fuente:** "Contexto del Primer Parcial — 2026-09-21", Bases de Datos: Administración y Aplicaciones, Pontificia Universidad Javeriana.
> **Propósito de este archivo:** enunciado original del docente, reescrito como reglas de negocio numeradas. Es la **fuente de verdad** del dominio: si hay conflicto con otro archivo, manda este. La especificación del grupo está en `03-requerimientos.md`.

## Jugadores

- **RN-01** Todo jugador debe registrarse en el sistema **antes** de poder participar.
- **RN-02** Datos obligatorios del jugador: código único de cliente, documento de identidad, nombre completo, edad y saldo actual en fichas.
- **RN-03** La edad se usa para validar que el jugador **no sea menor de edad**.

## Mesas

- **RN-04** El casino tiene varias mesas de juego (ej. Ruleta, Blackjack, Póker).
- **RN-05** Cada mesa tiene: identificador único, tipo de juego, monto mínimo y monto máximo de apuesta por jugada.
- **RN-06** Cada mesa está asignada a un **crupier** (empleado) durante un **turno** específico.

## Crupieres, turnos y jornadas

- **RN-07** Un crupier solo puede estar a cargo de **una mesa a la vez por turno**.
- **RN-08** Una mesa puede cambiar de crupier entre turnos: **los crupieres rotan cada turno**.
- **RN-09** Un crupier **no puede repetir mesa** durante una misma jornada (día).
- **RN-10** La duración de los turnos se define cada día y **no puede superar 2 horas**.

## Supervisores

- **RN-11** Cada mesa tiene un supervisor que verifica que el crupier no haga trampa.
- **RN-12** Al final de cada turno, el supervisor emite un **concepto** del trabajo del crupier, uno de: `Genera ganancias`, `Genera pérdidas`, `Sospecha de fraude`, `Comportamiento neutro`.
- **RN-13** El concepto es **subjetivo** (criterio del supervisor) y **no se calcula** a partir de las ganancias/pérdidas de la mesa.

## Competencias

- **RN-14** No todos los crupieres ni supervisores conocen todos los juegos.
- **RN-15** A una mesa solo se pueden asignar crupieres y supervisores que **conozcan el juego** de esa mesa.

## Rondas

- **RN-16** Las partidas se desarrollan en **rondas**. Cada ronda pertenece a una mesa, tiene un número correlativo, hora de inicio y hora de cierre.
- **RN-17** Durante una ronda, los jugadores presentes en la mesa pueden hacer **una o más apuestas**.
- **RN-18** Al finalizar la ronda, el crupier ingresa el **resultado ganador** (ej. "Número 17", "Negro", "Impar").

## Apuestas (juegos con registro detallado)

- **RN-19** Al apostar se registra: jugador, ronda, tipo de apuesta (ej. Color Rojo, Número Par, Pleno al 17), monto en fichas y factor de pago (ej. 2:1, 35:1).
- **RN-20** El sistema verifica **estrictamente** que el monto no sea inferior al mínimo ni superior al máximo de la mesa.
- **RN-21** El sistema verifica que el jugador tenga **saldo suficiente**.

## Procesamiento automático de la ronda

Con el resultado ingresado, el sistema procesa **automáticamente** cada apuesta de la ronda:

- **RN-22** Si la apuesta coincide con el resultado → estado **Ganada**; premio = `monto_apostado × factor_pago`, acreditado **inmediatamente** al saldo del jugador.
- **RN-23** Si no coincide → estado **Perdida**; el monto se consolida a favor del casino.

## Apuestas (juegos sin registro detallado)

- **RN-24** En juegos que no permiten registro detallado (ej. póker), las apuestas **solo se registran cuando se evidencia el resultado** (al destapar las cartas).

## Política de Autoexclusión y Prevención de Riesgo

### Jugadores
- **RN-25** Si un jugador acumula en **un mismo día** pérdidas superiores a un **umbral configurado** → estado **Suspendido**.
- **RN-26** Si un jugador **solicita voluntariamente** una pausa → estado **Suspendido**.
- **RN-27** En ambos casos no puede apostar en **ninguna mesa** durante las **siguientes 24 horas**.

### Empleados que juegan
- **RN-28** Los empleados (crupieres, administradores, supervisores, etc.) pueden apostar como cualquier cliente en su tiempo libre.
- **RN-29** Si un empleado acumula pérdidas superiores a **2 meses de su salario** → **Suspendido**. Cuando la deuda baje de ese límite, puede volver a jugar **automáticamente**, hasta que lo vuelva a superar (suspensión sin plazo fijo, dependiente del saldo de pérdidas).
- **RN-30** Si un empleado tiene ganancias superiores a **1 mes de su salario** → estado **Investigación**; no puede apostar en ninguna mesa **hasta que finalice la investigación** por posible fraude (cierre manual).

## Glosario

| Término | Significado |
|---|---|
| Jornada | Un día de operación del casino |
| Turno | Bloque horario de una jornada, máx. 2 h |
| Ronda | Una jugada completa en una mesa, de apertura a resultado |
| Factor de pago | Cuota que multiplica el monto apostado si se gana |
| Registro detallado | Si el juego permite registrar apuestas antes del resultado |
| Umbral | Límite diario de pérdidas configurable para jugadores |
