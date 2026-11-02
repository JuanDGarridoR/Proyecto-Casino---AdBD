# Documento técnico — Sistema de gestión de casino en Django

**Curso:** Bases de Datos: Administración y Aplicaciones — Pontificia Universidad Javeriana
**Equipo:** Juan David Garrido Ramos · Andrés Felipe Torres Monroy · Alejandro Urbina
**Framework asignado:** Django 5.2 (Python)

---

## 1. Descripción del framework

Django es un framework web de Python de tipo "baterías incluidas". Trae de serie un ORM con migraciones, un sistema de plantillas, formularios con validación, autenticación y sesiones, protección CSRF, mensajes y un sitio de administración generado a partir de los modelos.

Sigue el patrón **MTV (Model–Template–View)**:

| Capa | En Django | En este proyecto |
|---|---|---|
| Modelo | `models.py` (ORM) | Tablas del modelo entidad-relación, con `CheckConstraint` y `UniqueConstraint` |
| Plantilla | `templates/*.html` | Interfaz por rol con Bootstrap (solo CSS desde CDN); sin SPA |
| Vista | `views.py` + `urls.py` | Funciones que validan el rol, llaman a los servicios y renderizan |

Un proyecto Django se compone de **apps** reutilizables. Cada una agrupa sus modelos, vistas, URLs, formularios, migraciones y pruebas.

> **PENDIENTE:** Agregar las versiones y el stack: Python 3.12+, Django 5.2.18, python-dotenv, SQLite (desarrollo) o PostgreSQL con psycopg 3 (opcional), Bootstrap por CDN. Agregar un párrafo breve sobre por qué Django (o cómo se asignó) y un poco de contexto del framework: origen, licencia y comunidad.

## 2. Arquitectura utilizada

```
Navegador ──(HTML + zk.js)──► urls.py ──► views.py ──► services.py ──► models.py ──► BD
                                              │              (transaction.atomic, select_for_update)
                                              └── forms.py (validación de entrada)
```

### Apps por dominio

| App | Responsabilidad |
|---|---|
| `cuentas` | Persona, Usuario (modelo propio), Empleado, backend Zero Knowledge, roles (Groups), decorador `rol_requerido`, gestión de empleados, comando `seed` |
| `mesas` | Juego, Mesa, Competencia, Turno, AsignacionMesa; validaciones RN-07/09/10/15; supervisión y concepto |
| `juego` | Ronda, Apuesta; registro de apuestas, cierre de ronda y procesamiento automático; reporte de ganancias |
| `jugadores` | Jugador, Movimiento, Configuración, HistorialEstado, Notificación; suspensiones RN-25 a RN-30 |

### Principios aplicados
- **Lógica de negocio en `services.py`.** Las vistas no modifican saldos ni estados directamente. Así una misma regla se aplica desde la web, desde el comando `seed` y desde las pruebas.
- **Transacciones.** Toda operación que toca varias tablas (apostar, cerrar ronda, aprobar movimiento) corre dentro de `transaction.atomic()`. Bloquea filas con `select_for_update()` (efectivo en PostgreSQL) y actualiza saldos con expresiones `F()` para evitar condiciones de carrera.
- **Validación en tres niveles.** (1) Formularios (`django.forms`) para tipos y formatos. (2) Servicios y `Model.clean()` para reglas que dependen de otras filas. (3) **Constraints en la BD** para lo expresable de forma declarativa.
- **Seguridad por rol en el servidor.** Cada vista lleva `@rol_requerido(...)`. Ocultar opciones del menú es solo una ayuda visual.
- **Migraciones** como única forma de crear el esquema. Los grupos de roles y el umbral inicial se crean en migraciones de datos.

> **PENDIENTE:** Agregar el árbol de carpetas del proyecto (casino/, cuentas/, mesas/, juego/, jugadores/, templates/, static/) y un mapa de URLs por rol: qué pantallas ve cada rol y en qué ruta.

## 3. Modelo de datos

> **PENDIENTE:** Insertar el diagrama entidad-relación (imagen exportada del DBML o diagrama Mermaid), con todas las tablas: las del modelo base y las agregadas.

> **PENDIENTE:** Agregar un diccionario de datos: por cada tabla, sus columnas, tipo, nulo/no nulo, PK, FK (a qué tabla apunta) y una descripción. Indicar también la cardinalidad de cada relación (persona 1–0..1 jugador, mesa 1–N ronda, ronda 1–N apuesta, etc.).

### 3.1 Tablas del modelo base (sin cambios de columnas)

`persona`, `jugador`, `empleado`, `juego`, `mesa`, `competencia`, `turno`, `asignacion_mesa`, `ronda`, `apuesta`. Los nombres de tabla y de columna (`db_table`, `db_column`) coinciden con el DBML entregado (`id_persona`, `id_juego`, `id_mesa`, `id_crupier`, …).

### 3.2 Tablas agregadas

| Tabla | Para qué |
|---|---|
| `usuario` | Credenciales Zero Knowledge: `username`, `salt`, `password_hash` (SHA-256 hex, con CHECK de formato), `activo`, FK a persona |
| `movimiento` | Consignaciones y retiros: jugador, tipo, monto, fecha, **estado** (Pendiente/Aprobado/Rechazado), observación |
| `configuracion` | Parámetros clave–valor; `umbral_perdida_diaria` (RN-25) |
| `historial_estado` | Cambios de estado de la cuenta con motivo y fecha (historial de clientes, cierre de investigación) |
| `notificacion` | Avisos a la persona (suspensión, investigación, reactivación, movimientos) |

Las tablas `auth_group`, `django_session`, etc. son propias del framework.

### 3.3 Diferencias entre el modelo lógico y el físico
- **PK compuestas** de `competencia` y `asignacion_mesa`: Django crea un `id` autoincremental y la PK lógica se garantiza con `UniqueConstraint` (`competencia_pk`, `asignacion_mesa_pk`). Así el admin, los formularios y `ModelForm` funcionan sin fricción.
  > **PENDIENTE:** Explicar por qué no se usó `CompositePrimaryKey`, que Django 5.2 ya trae: el admin, `ModelForm` y las FK hacia una tabla con PK compuesta todavía no lo soportan bien.
- `usuario` tiene además las columnas `password` (inutilizable), `last_login`, `is_superuser` e `is_staff`, que exige `AbstractBaseUser`/`PermissionsMixin`.

### 3.4 Constraints declarados en la BD

| Constraint | Regla |
|---|---|
| `jugador_mayor_de_edad` (edad ≥ 18) | RN-03 |
| `jugador_saldo_no_negativo`, `jugador_estado_valido` | Integridad del saldo y de los estados |
| `mesa_montos_validos` (0 < mín ≤ máx) | RN-05 |
| `turno_fin_posterior_inicio` | Un turno no cruza medianoche |
| `asignacion_mesa_pk` (mesa, turno) | Una asignación por mesa y turno |
| `asignacion_crupier_turno_unico` (crupier, turno) | RN-07 |
| `asignacion_crupier_distinto_supervisor` | Crupier ≠ supervisor |
| `asignacion_concepto_valido` | RN-12 (4 valores) |
| `ronda_numero_por_mesa` (mesa, numero) | Número correlativo por mesa |
| `ronda_una_abierta_por_mesa` (UNIQUE parcial donde `hora_cierre IS NULL`) | Una sola ronda abierta por mesa |
| `ronda_cierre_posterior_inicio` | RN-16 |
| `apuesta_monto_positivo`, `apuesta_factor_positivo`, `apuesta_premio_no_negativo`, `apuesta_estado_valido` | Integridad de apuestas |
| `movimiento_*`, `empleado_*`, `usuario_password_hash_sha256` | Montos positivos, valores válidos, hash de 64 hex |

### 3.5 Reglas validadas en servicios o en `clean()`

| Regla | Dónde |
|---|---|
| RN-09 no repetir mesa en la jornada | `AsignacionMesa.clean()` |
| RN-10 turno ≤ 2 h, turnos sin solaparse | `Turno.clean()` |
| RN-15 competencia de crupier y supervisor | `AsignacionMesa.clean()` |
| RN-20 mín ≤ monto ≤ máx, RN-21 saldo suficiente, ronda abierta, jugador Activo | `juego.services._validar_apuesta` |
| Solo el crupier asignado a la mesa en el turno en curso la opera | `juego.services.verificar_crupier_en_turno` |
| RN-22/23 procesamiento automático | `juego.services.cerrar_ronda` |
| RN-24 juegos sin registro detallado | `cerrar_ronda(..., apuestas_al_resultado)` |
| RN-25 a RN-30 suspensiones | `jugadores.services.evaluar_estado` |
| Retiro ≤ saldo | `jugadores.services._aplicar_movimiento` / `solicitar_movimiento` |
| Concepto solo al terminar el turno y por el supervisor asignado | `mesas.services.emitir_concepto` |

## 4. Funcionalidades implementadas

### 4.1 Autenticación Zero Knowledge con SHA-256

1. **Registro:** el servidor genera un `salt` y lo guarda en la sesión. El navegador (`static/js/zk.js`) calcula `H = SHA256(salt + contraseña)` y envía solo `H`. Los campos de contraseña **no tienen atributo `name`**, así que el navegador no puede enviarlos.
2. **Login, paso 1:** `POST /cuentas/desafio/` con el usuario. El servidor responde `{salt, nonce}`; el nonce es aleatorio (`secrets.token_hex(32)`) y queda en la sesión. Para un usuario inexistente se devuelve un salt ficticio y estable, para no revelar qué usuarios existen.
3. **Login, paso 2:** el navegador envía `R = SHA256(H + nonce)`.
4. **Verificación:** `cuentas.backends.ZeroKnowledgeBackend` (registrado en `AUTHENTICATION_BACKENDS`) consume el nonce, recalcula `SHA256(H_guardado + nonce)`, compara con `hmac.compare_digest` y llama a `login()`. Las sesiones son las de `django.contrib.sessions`.

Así ni la contraseña ni `H` viajan durante el login, y una `R` capturada no se puede reutilizar (probado en `cuentas/tests.py`). Si `crypto.subtle` no está disponible (HTTP por IP de red), `zk.js` usa una implementación de SHA-256 en JS puro, verificada contra `hashlib`.

**Limitaciones (exigencia del curso, no recomendación de producción):** `H` guardado en la BD equivale a la contraseña si la BD se filtra. Además, SHA-256 simple es rápido de atacar por fuerza bruta; en producción se usaría un KDF lento (PBKDF2, Argon2) o un protocolo PAKE como SRP u OPAQUE.

### 4.2 Control de acceso por roles
- Cuatro **Groups**: Administrador, Supervisor, Crupier, Jugador. Se derivan de los datos: el cargo del empleado y la existencia de una fila en `jugador`.
- `@rol_requerido(...)` protege cada vista. `base.html` arma el menú solo con las opciones del **rol activo**.
- Una persona que es empleado y jugador tiene ambos roles y cambia de contexto desde el menú ("Rol: …").

### 4.3 Casos de uso (los 6, con CRUD)

| Caso de uso | Rol | Operaciones |
|---|---|---|
| **Gestión de mesas** | Administrador | CRUD de juegos y mesas; CRUD de turnos, incluida la definición de los turnos de un día con su duración; CRUD de asignaciones crupier + supervisor validando RN-07/09/10/15. Supervisor: concepto al final del turno |
| **Gestión de rondas** | Crupier | Abrir (número correlativo), consultar, eliminar si está vacía, ingresar resultado y cerrar |
| **Gestión de apuestas** | Crupier | Registrar, modificar y anular (con devolución) mientras la ronda está abierta; póker: registro al evidenciar el resultado |
| **Gestión de ganancias** | Automático + Administrador | Premio = monto × factor acreditado al instante; reporte por mesa, día y jugador |
| **Gestión de suspensiones** | Automático + Jugador + Administrador | RN-25 umbral diario, RN-26 pausa voluntaria, RN-29 deuda del empleado, RN-30 investigación con cierre manual |
| **Consignaciones y retiros** | Jugador (solicita) y Administrador (registra, aprueba, rechaza, edita o elimina pendientes) | El retiro no supera el saldo; los retiros pendientes comprometen saldo |

**Comparación del resultado:** el crupier escribe el resultado como texto, con varias opciones ganadoras separadas por comas (ej. "Asiento 1, Asiento 3"). Una apuesta gana si su tipo, normalizado (minúsculas, sin tildes), está en ese conjunto. En la ruleta basta con escribir el número: el sistema deduce pleno, color, paridad, falta/pasa y docena. El formulario sugiere tipos de apuesta con su pago habitual.

### 4.4 Funcionalidades adicionales (las 4) + interfaz por rol

> **PENDIENTE:** Aclarar que la lista tiene 5 puntos porque el 5 (interfaz por rol) es obligatorio y no cuenta entre las 4 adicionales.

1. **Notificaciones:** se generan en cada cambio de estado (Suspendido, Investigación, reactivación) y al aprobar o rechazar movimientos. Un contador aparece en el menú.
2. **Gestión de empleados:** alta con usuario ZK, cargo, salario y juegos que conoce; edición, desactivación, eliminación (solo sin asignaciones) y habilitación como jugador (RN-28).
3. **Historial de clientes:** apuestas, consignaciones y retiros, cambios de estado y, para empleados, sus indicadores de deuda y ganancias.
4. **Validación de autorizaciones y suspensiones:** competencias (RN-15), estado del jugador antes de cada apuesta, mayoría de edad al registrar.
5. **Interfaz de usuario por rol** (obligatoria): un panel distinto para cada rol.

### 4.5 Decisiones de negocio documentadas
- **Saldo:** el monto se **descuenta al registrar** la apuesta. Al ganar se acredita `premio = monto × factor` **más la devolución** del monto (un 35:1 paga 35 más la apuesta). `premio` guarda solo la ganancia neta.
- **Pérdida diaria (RN-25):** suma bruta de los montos de apuestas Perdidas cuyas rondas cerraron ese día. No descuenta lo ganado.
- **Deuda del empleado (RN-29):** pérdidas netas (perdido − ganado) en una **ventana móvil de 30 días**. Al superar 2 salarios queda Suspendido sin plazo (`suspendido_hasta = NULL`). Cuando las pérdidas antiguas salen de la ventana y la deuda baja del límite, se reactiva solo.
- **Ganancias del empleado (RN-30):** ganancias netas desde el último cierre de investigación. Superar 1 salario lo pasa a Investigación, que solo un administrador cierra.
- **Vencimiento de 24 h:** no hay proceso en segundo plano. El estado se reevalúa antes de cada apuesta, al cerrar rondas, al aprobar movimientos y al abrir el panel o el historial del jugador.
- **Quién registra apuestas:** el crupier, como dice el enunciado. El jugador las "realiza" en la mesa y consulta su resultado en su historial.
- **Operación de la mesa:** solo el crupier asignado a esa mesa en el turno en curso puede abrir y cerrar rondas o registrar apuestas.
- **Unidad monetaria:** 1 ficha = 1 peso. Salarios, umbral y montos usan la misma unidad.
- **Movimientos aprobados** no se editan ni eliminan, por trazabilidad; se corrigen con un movimiento inverso.

## 5. Datos de prueba y evidencia
- `python manage.py seed [--reset]` crea 1 administrador, 2 supervisores, 4 crupieres con competencias distintas (3 de ellos también juegan), 3 juegos (Ruleta y Blackjack detallados, Póker sin registro detallado), 4 mesas, turnos de ayer y de hoy con rotación de crupieres, historial de rondas y jugadores en todos los estados. Todo pasa por las validaciones del sistema. También intenta registrar a un menor de edad y muestra el rechazo.
- `python manage.py test`: 36 pruebas automatizadas (login ZK, accesos por rol, reglas de negocio).

> **PENDIENTE — Instalación y ejecución:** Agregar los pasos: crear venv, `pip install -r requirements.txt`, copiar `.env.example` a `.env`, `python manage.py migrate`, `python manage.py seed`, `python manage.py runserver`. Agregar la configuración opcional de PostgreSQL (`DB_ENGINE=postgresql` y las variables `DB_*`). Están en el README.

> **PENDIENTE — Usuarios de prueba:** Agregar la tabla de usuarios del README (usuario, rol y situación en los datos de prueba) e indicar la contraseña común `Casino123*`: admin, sup1, sup2, crup1 a crup4, jugador1 a jugador4.

> **PENDIENTE — Detalle de los datos sembrados:** Listar los juegos (Ruleta, Blackjack, Póker y si tienen registro detallado), las 4 mesas con su juego y montos mínimo y máximo, los turnos de ayer y de hoy con sus asignaciones, el umbral de pérdida diaria (1.000.000) y el estado inicial de cada jugador.

> **PENDIENTE — Detalle de las pruebas automatizadas:** Agregar una tabla por app (cuentas: 10, juego: 10, jugadores: 8, mesas: 8) con lo que cubre cada grupo y las RN que verifica (RN-03, 07, 09, 10, 12, 15, 20–27, 29, 30, consignaciones y retiros).

> **PENDIENTE — Guion de demostración:** Agregar los 6 pasos del README (jugador2 → crup2 apuesta y cierre → jugador3 suspendido → crup3 póker y cambio de rol → sup1 concepto → admin asignación inválida, caja, investigación, ganancias y umbral), con el resultado esperado de cada paso.

### 5.1 Capturas de pantalla

> **PENDIENTE — Captura:** Pantalla de login.

> **PENDIENTE — Captura:** DevTools → Network en el login, donde se ve que solo se envía `R` (ni la contraseña ni `H`).

> **PENDIENTE — Captura:** Panel de cada rol (Administrador, Supervisor, Crupier, Jugador) y el selector "Rol: …" de una persona con dos roles.

> **PENDIENTE — Captura:** Apuesta rechazada por superar el monto máximo de la mesa (RN-20).

> **PENDIENTE — Captura:** Apuesta rechazada a un jugador suspendido (jugador3).

> **PENDIENTE — Captura:** Cierre de ronda con el resultado y las apuestas marcadas Ganada/Perdida con su premio.

> **PENDIENTE — Captura:** jugador2 suspendido 24 h por superar el umbral, con su notificación (RN-25).

> **PENDIENTE — Captura:** Asignación rechazada por RN-09 o RN-15.

> **PENDIENTE — Captura:** Concepto emitido por el supervisor (RN-12).

> **PENDIENTE — Captura:** Caja: aprobar o rechazar una consignación o un retiro.

> **PENDIENTE — Captura:** Historial de un cliente y cierre de investigación (RN-30).

> **PENDIENTE — Captura:** Reporte de ganancias.

> **PENDIENTE — Captura:** Salida de `python manage.py seed`, con el rechazo del menor de edad.

> **PENDIENTE — Captura:** Salida de `python manage.py test` con las 36 pruebas en OK.

## 6. Dificultades encontradas
1. **SHA-256 frente al hasher de Django.** El hasher por defecto (PBKDF2) y `check_password` no cumplen el requisito. Hubo que escribir un modelo de usuario propio (`AUTH_USER_MODEL`, definido **antes** de la primera migración) y un backend de autenticación. Además, el login del admin de Django usa `check_password`, así que se redirigió `/admin/login/` al login propio.
2. **`TextChoices` anidados y `Meta`.** Una clase `Meta` no ve las clases definidas en el cuerpo del modelo. Las listas de valores para los `CheckConstraint` exigieron mover los `TextChoices` a nivel de módulo.
3. **Reglas entre filas.** RN-09 y el solapamiento de turnos no son expresables como `CHECK` portable entre SQLite y PostgreSQL. Quedaron en `clean()`, y hay que llamar a `full_clean()` explícitamente porque `save()` no valida.
4. **Fechas con zona horaria.** Con `USE_TZ=True`, los turnos (fecha + hora local) se comparan con instantes UTC. Para "el día" se usan rangos `[00:00, 24:00)` locales en vez de `__date`, para no depender del motor.
5. **Interpretación del enunciado:** cómo comparar el resultado con la apuesta, si el premio incluye la devolución, cómo "baja la deuda" de un empleado. Se tomaron y documentaron las decisiones de la sección 4.5.
6. **Turnos y demo en vivo.** Como las reglas dependen de la hora real, el seed calcula el turno en curso según la hora de ejecución.

## 7. Análisis crítico del framework

| Aspecto | Valoración |
|---|---|
| **Calidad** | Madura y estable. Documentación excelente. Seguridad por defecto: CSRF, escapado de HTML en plantillas, consultas parametrizadas, `ProtectedError` |
| **Facilidad de uso** | Muy alta para CRUD: `ModelForm` + admin generan formularios y validación con poco código. Las migraciones automáticas aceleran mucho la evolución del esquema |
| **Curva de aprendizaje** | Media. Exige entender proyecto/apps, MTV, el ORM (`select_related`, `annotate`, `F`, `Q`), el orden de los middlewares y las convenciones de nombres. Personalizar la autenticación es la parte más empinada |
| **Ventajas** | Baterías incluidas (auth, sesiones, admin, formularios, mensajes, i18n). ORM portable entre SQLite y PostgreSQL. `CheckConstraint` y `UniqueConstraint` parciales declarativos. `transaction.atomic`. Cliente de pruebas integrado |
| **Desventajas** | El ORM oculta el SQL y facilita consultas N+1 si no se usa `select_related`. Las PK compuestas tienen soporte limitado (recién en 5.2). Cambiar `AUTH_USER_MODEL` a mitad de proyecto es muy costoso |
| **Limitaciones** | Reglas complejas entre filas (RN-09, solapamientos) no se pueden declarar en el ORM: se usan `clean()`/servicios o triggers en SQL crudo. La interfaz reactiva requiere JS aparte, ya que las plantillas son del lado del servidor. El hasher por defecto no permite SHA-256 simple sin código propio |

## 8. Conclusiones y recomendaciones
- Django permitió cubrir los 6 casos de uso y las 4 funcionalidades adicionales con poco código repetitivo, gracias al ORM, `ModelForm`, las sesiones y el admin.
- Concentrar las reglas en `services.py` con transacciones y reforzarlas con constraints en la BD dio una solución coherente y fácil de probar.
- **Recomendaciones:** definir el modelo de usuario propio desde el día 1. Usar PostgreSQL en producción, para que `select_for_update` bloquee de verdad. Reemplazar SHA-256 simple por un KDF lento o por SRP/OPAQUE si el sistema fuera real. Agregar un trigger en la BD para RN-09 si se quiere garantizar la regla también fuera de la aplicación.

## Anexo A. Reglas de negocio

> **PENDIENTE:** Agregar la lista completa de reglas RN-01 a RN-30 (están en `docs/02-contexto-casino.md`), con una tabla de tres columnas: regla, descripción y dónde se implementa (constraint, `clean()`, servicio o vista). El documento hoy no menciona RN-01, 02, 04, 06, 08, 11, 13, 14, 17, 18, 19, 23 y 27, aunque están implementadas.
