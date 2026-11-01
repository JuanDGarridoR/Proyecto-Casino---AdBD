# 04 — Modelo de datos

> **Fuente:** diagrama entidad-relación del grupo (DBML).
> **Propósito de este archivo:** esquema base de la aplicación, qué regla de negocio cubre cada tabla y qué reglas **no** quedan garantizadas por el esquema y deben implementarse en la lógica (servicios, triggers o constraints adicionales).

## Esquema (DBML)

```dbml
Table persona {
  id_persona      int [pk, increment]
  documento       varchar(20) [not null, unique]
  nombre_completo varchar(100) [not null]
}

Table jugador {
  id_persona       int [pk, ref: > persona.id_persona]
  codigo_cliente   varchar(20) [not null, unique]
  edad             int [not null]
  saldo_fichas     decimal(12,2) [not null, default: 0]
  estado           varchar(20) [not null, default: 'Activo']
  suspendido_hasta datetime
}

Table empleado {
  id_persona int [pk, ref: > persona.id_persona]
  cargo      varchar(50) [not null]
  salario    decimal(12,2) [not null]
}

Table juego {
  id_juego           int [pk, increment]
  tipo_juego         varchar(50) [not null, unique]
  registro_detallado boolean [not null]
}

Table mesa {
  id_mesa      int [pk, increment]
  id_juego     int [not null, ref: > juego.id_juego]
  monto_minimo decimal(12,2) [not null]
  monto_maximo decimal(12,2) [not null]
}

Table competencia {
  id_empleado int [not null, ref: > empleado.id_persona]
  id_juego    int [not null, ref: > juego.id_juego]

  indexes {
    (id_empleado, id_juego) [pk]
  }
}

Table turno {
  id_turno    int [pk, increment]
  fecha       date [not null]
  hora_inicio time [not null]   // NOTA: asume que el turno no cruza medianoche
  hora_fin    time [not null]
}

Table asignacion_mesa {
  id_mesa             int [not null, ref: > mesa.id_mesa]
  id_turno            int [not null, ref: > turno.id_turno]
  id_crupier          int [not null, ref: > empleado.id_persona]
  id_supervisor       int [not null, ref: > empleado.id_persona]
  concepto_supervisor varchar(30)

  indexes {
    (id_mesa, id_turno) [pk]
    (id_crupier, id_turno) [unique]
  }
}

Table ronda {
  id_ronda    int [pk, increment]
  id_mesa     int [not null, ref: > mesa.id_mesa]
  numero      int [not null]
  hora_inicio datetime [not null]
  hora_cierre datetime
  resultado   varchar(100)

  indexes {
    (id_mesa, numero) [unique]
  }
}

Table apuesta {
  id_apuesta     int [pk, increment]
  id_jugador     int [not null, ref: > jugador.id_persona]
  id_ronda       int [not null, ref: > ronda.id_ronda]
  tipo_apuesta   varchar(100) [not null]
  monto_apostado decimal(12,2) [not null]
  factor_pago    decimal(8,2) [not null]
  estado         varchar(20) [not null, default: 'Pendiente']
  premio         decimal(12,2) [not null, default: 0]
}
```

## Diseño y decisiones

- **Generalización `persona` → `jugador` / `empleado`:** ambos comparten `id_persona`. Una misma persona puede tener fila en `jugador` **y** en `empleado`, así se modela que un empleado apueste como cliente (RN-28). Para saber si un jugador es empleado: `EXISTS (SELECT 1 FROM empleado WHERE id_persona = jugador.id_persona)`.
- **`juego` separado de `mesa`:** varias mesas comparten juego; `registro_detallado` decide si las apuestas se registran antes del resultado o solo al evidenciarse (RN-24).
- **`competencia`:** relación N:M empleado–juego (RN-14).
- **`asignacion_mesa`:** una fila por mesa y turno, con crupier, supervisor y concepto.
  - PK `(id_mesa, id_turno)` → una sola asignación por mesa en cada turno.
  - UNIQUE `(id_crupier, id_turno)` → un crupier no atiende dos mesas en el mismo turno (RN-07).
- **`ronda`:** UNIQUE `(id_mesa, numero)` → número correlativo por mesa. `hora_cierre` y `resultado` en NULL mientras la ronda está abierta.
- **`apuesta`:** `estado` arranca en `Pendiente`; `premio` queda en 0 hasta procesar la ronda.

## Mapa regla → dónde se garantiza

| Regla | Garantizada por el esquema | Debe implementarse en lógica / BD |
|---|---|---|
| RN-02 datos obligatorios del jugador | NOT NULL + UNIQUE | — |
| RN-03 mayor de edad | — | `CHECK (edad >= 18)` o validación al registrar |
| RN-05 mín/máx por mesa | columnas | `CHECK (monto_minimo > 0 AND monto_minimo <= monto_maximo)` |
| RN-07 un crupier, una mesa por turno | UNIQUE `(id_crupier, id_turno)` | — |
| RN-09 no repetir mesa en la jornada | — | validar que no exista otra asignación del mismo crupier en la misma mesa con un turno de la misma `fecha` (trigger o servicio) |
| RN-10 turno ≤ 2 h | — | `CHECK (hora_fin > hora_inicio AND hora_fin - hora_inicio <= interval '2 hours')` (sintaxis según el motor) |
| Turnos que no se solapan en un día | — | validación en servicio (si se decide exigirlo) |
| RN-12 valores del concepto | — | `CHECK` o enum con los 4 valores |
| RN-15 competencia en el juego | — | validar crupier y supervisor contra `competencia` para el `id_juego` de la mesa |
| Crupier ≠ supervisor en la misma asignación | — | `CHECK (id_crupier <> id_supervisor)` (recomendado) |
| RN-16 ronda abierta → cierre | — | `CHECK (hora_cierre IS NULL OR hora_cierre >= hora_inicio)` |
| RN-20 mín ≤ monto ≤ máx | — | validar contra la mesa de la ronda (trigger o servicio) |
| RN-21 saldo suficiente | — | validar y descontar el monto **en la misma transacción** |
| Apostar solo en ronda abierta | — | validar `ronda.hora_cierre IS NULL` |
| RN-22/23 procesamiento | — | transacción al cerrar ronda: actualizar `estado`, `premio`, `saldo_fichas` |
| Estados válidos | — | `CHECK` en `jugador.estado` (`Activo`, `Suspendido`, `Investigación`) y `apuesta.estado` (`Pendiente`, `Ganada`, `Perdida`) |
| RN-25..27 suspensión 24 h | `estado` + `suspendido_hasta` | calcular pérdidas del día y setear `suspendido_hasta = now() + 24h` |
| RN-29 empleado: pérdidas > 2 salarios | — | recalcular tras cada apuesta/consignación; sin `suspendido_hasta` |
| RN-30 empleado: ganancias > 1 salario | — | pasar a `Investigación`; cierre manual por un admin |

## Supuestos sobre el saldo (definir y mantener consistentes)

- Recomendado: al **registrar** la apuesta se descuenta `monto_apostado` del saldo; al ganar se acredita `premio`. Definir si `premio = monto × factor` incluye o no la devolución del monto apostado (en ruleta, 35:1 normalmente paga 35 **más** la apuesta). Documentar la decisión.
- Pérdida diaria de un jugador = suma de `monto_apostado` de apuestas `Perdida` del día (o neto pérdidas − ganancias; elegir y documentar).

## Lo que el esquema actual NO cubre (tablas a agregar)

El DBML base no tiene dónde guardar varias cosas que piden los requisitos. Propuestas mínimas:

| Necesidad | Requisito | Propuesta |
|---|---|---|
| Credenciales y rol | Login ZK + SHA-256, control por roles | `usuario(id_usuario, id_persona FK, username UNIQUE, password_hash char(64), salt, rol, activo)` |
| Consignaciones/retiros | Caso de uso 3.6, historial | `movimiento(id_movimiento, id_jugador FK, tipo CHECK IN ('Consignacion','Retiro'), monto, fecha)` |
| Umbral diario configurable | RN-25 | `configuracion(clave PK, valor)` o tabla `parametro` con `umbral_perdida_diaria` |
| Cambios de estado de cuenta | Historial de clientes | `historial_estado(id, id_jugador FK, estado_anterior, estado_nuevo, motivo, fecha)` |
| Notificaciones | Funcionalidad adicional 1 | `notificacion(id, id_persona FK, mensaje, fecha, leida boolean)` |
| Cierre de investigación | RN-30 | puede ir en `historial_estado` con motivo `Cierre investigación` |

> No modificar las tablas existentes sin acordarlo con el grupo: el modelo base es el entregado en el parcial. Agregar tablas nuevas es seguro; cambiar columnas existentes, documentarlo.

## Implementación en Django

### Mapeo de tablas a modelos

| Tabla | Modelo Django | Notas |
|---|---|---|
| `persona` | `Persona` | `documento = CharField(max_length=20, unique=True)` |
| `jugador` | `Jugador` | `persona = OneToOneField(Persona, primary_key=True, on_delete=PROTECT)` |
| `empleado` | `Empleado` | igual que `Jugador`, OneToOne con PK compartida |
| `juego` | `Juego` | `registro_detallado = BooleanField()` |
| `mesa` | `Mesa` | `juego = ForeignKey(Juego, on_delete=PROTECT)` |
| `competencia` | `Competencia` o `ManyToManyField` | `Empleado.juegos = ManyToManyField(Juego, db_table='competencia')` es lo más idiomático |
| `turno` | `Turno` | `DateField` + dos `TimeField` |
| `asignacion_mesa` | `AsignacionMesa` | ver nota de PK compuesta |
| `ronda` | `Ronda` | `UniqueConstraint(fields=['mesa','numero'])` |
| `apuesta` | `Apuesta` | `estado` con `TextChoices` |

- Usar `db_table` en `Meta` para que los nombres de tabla coincidan con el modelo entregado.
- Montos: `DecimalField(max_digits=12, decimal_places=2)`; nunca `FloatField`.
- Estados y concepto del supervisor: `models.TextChoices` + `CheckConstraint` para que la BD también los valide.
- `on_delete=PROTECT` en casi todas las FK: no se debe poder borrar una mesa con rondas o un jugador con apuestas sin decidirlo explícitamente.

### Llaves compuestas

`asignacion_mesa` y `competencia` tienen PK compuesta en el diseño. Dos opciones:
1. **Recomendada (más simple):** dejar que Django cree un `id` autoincremental y declarar `UniqueConstraint(fields=['mesa','turno'])` y `UniqueConstraint(fields=['crupier','turno'])`. Se conserva la semántica del modelo y todo el ecosistema (admin, formularios, `ModelForm`) funciona sin fricción.
2. `models.CompositePrimaryKey('mesa', 'turno')` (disponible desde Django 5.2): respeta el diseño literalmente, pero el soporte en admin y en algunas relaciones es limitado.

Documentar la opción elegida como diferencia entre el modelo lógico y el físico.

### Dónde va cada validación

- **Constraints en BD (`Meta.constraints`):** `CheckConstraint` para edad ≥ 18, mín ≤ máx, `crupier != supervisor`, estados válidos, `hora_fin > hora_inicio`; `UniqueConstraint` para las unicidades. La duración ≤ 2 h puede validarse en `clean()` si el motor no permite la expresión.
- **`Model.clean()` / formularios:** validaciones que dependen de otras filas pero son de una sola entidad (competencia del crupier y supervisor, no repetir mesa en la jornada).
- **`services.py` + `transaction.atomic()`:** operaciones con varias tablas:
  - `registrar_apuesta(jugador, ronda, ...)`: `select_for_update()` sobre el jugador, verificar estado/suspensión vencida, ronda abierta, mín/máx y saldo; descontar saldo; crear apuesta.
  - `cerrar_ronda(ronda, resultado)`: marcar Ganada/Perdida, calcular premio, acreditar saldos, luego evaluar suspensiones.
  - `evaluar_suspension(jugador)`: reglas RN-25, RN-29, RN-30; registrar historial y notificación.
  - `registrar_movimiento(...)`: consignación/retiro con validación de saldo.
- Evitar meter lógica de negocio en `signals`: hace el flujo difícil de seguir y de explicar en la exposición.
- Recordar que `save()` no llama a `full_clean()` automáticamente; los servicios deben llamarlo o validar explícitamente.

### Usuario y roles

- Crear un modelo `Usuario` propio (`AbstractBaseUser` + `PermissionsMixin`, `AUTH_USER_MODEL = 'cuentas.Usuario'`) con `persona = OneToOneField(Persona)`, `salt` y `password_hash` (char 64, SHA-256 en hex). Definirlo **antes de la primera migración**: cambiar `AUTH_USER_MODEL` después es muy costoso.
- La autenticación se hace con un backend propio (ver `01-enunciado-proyecto.md`, sección Autenticación).

### Suspensiones de 24 h

No hace falta un proceso en segundo plano: al validar una apuesta (y al cargar la vista del jugador), si `estado == 'Suspendido'` y `suspendido_hasta <= timezone.now()`, se reactiva la cuenta a `Activo` y se registra en el historial. Usar `USE_TZ = True` y `TIME_ZONE = 'America/Bogota'`.

## Datos de prueba sugeridos

- 1 administrador, 2 supervisores, 3 crupieres (con competencias distintas), algunos que también sean jugadores.
- Juegos: Ruleta (detallado), Blackjack (detallado), Póker (sin registro detallado).
- Mesas con distintos mínimos/máximos.
- Turnos de una jornada (≤ 2 h cada uno) con rotación de crupieres.
- Jugadores: uno activo con saldo, uno menor de edad (para probar el rechazo), uno cerca del umbral, uno Suspendido, un empleado en Investigación.
