# Proyecto Casino - Django

Aplicación web para la gestión de un casino de apuestas y mesas de juego.
Bases de Datos: Administración y Aplicaciones — Pontificia Universidad Javeriana.

**Equipo:** Juan David Garrido Ramos · Andrés Felipe Torres Monroy · Alejandro Urbina<br>
**Framework:** Django 5.2 (Python 3.12+) · **BD:** SQLite (desarrollo) o PostgreSQL

## Instalación

```bash
python -m venv venv
# Windows:  venv\Scripts\activate      Linux/macOS:  source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # en Windows: copy .env.example .env  (y cambie SECRET_KEY)
python manage.py migrate
python manage.py seed           # datos de prueba; para recargar: python manage.py seed --reset
python manage.py runserver
```

Abra **http://localhost:8000/** (o `http://127.0.0.1:8000/`).

### PostgreSQL (opcional)
1. `pip install "psycopg[binary]>=3.2"`
2. Cree la base: `createdb casino`
3. En `.env`: `DB_ENGINE=postgresql` y las variables `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.
4. `python manage.py migrate && python manage.py seed`

### Pruebas automatizadas
```bash
python manage.py test
```
36 pruebas cubren el login Zero Knowledge, el control de acceso por rol y las reglas de negocio (RN-03, 07, 09, 10, 12, 15, 20–27, 29, 30, consignaciones y retiros).

## Usuarios de prueba (contraseña de todos: `Casino123*`)

| Usuario | Rol | Situación en los datos de prueba |
|---|---|---|
| `admin` | Administrador | Acceso completo y al admin de Django (`/admin/`) |
| `sup1` | Supervisor | Supervisa las mesas 1 y 4; tiene conceptos pendientes de los turnos de ayer |
| `sup2` | Supervisor + Jugador | Como jugador (E-SUP2) está en **Investigación** (ganó más de 1 salario) |
| `crup1` | Crupier | Mesa 2 (Blackjack) en el turno actual |
| `crup2` | Crupier | Mesa 1 (Ruleta) en el turno actual, con una ronda abierta |
| `crup3` | Crupier + Jugador | Mesa 3 (Póker) en el turno actual; jugador E-CRU3 activo (demo de cambio de rol) |
| `crup4` | Crupier + Jugador | Mesa 4 (Ruleta VIP); jugador E-CRU4 **Suspendido** sin plazo (pérdidas > 2 salarios) |
| `jugador1` | Jugador | Activo con saldo y una consignación pendiente |
| `jugador2` | Jugador | Activo, perdió 900.000 hoy (umbral 1.000.000): una pérdida más lo suspende |
| `jugador3` | Jugador | **Suspendido 24 h** por pausa voluntaria |
| `jugador4` | Jugador | Activo, con un retiro pendiente de aprobación |

El seed también intenta registrar a un menor de 16 años y muestra el rechazo.

> **Turnos:** el seed crea el turno "actual" a partir de la hora en que se ejecuta (máx. 2 h). Si la demo es más tarde, ejecute `python manage.py seed --reset` antes de presentar, o cree turnos y asignaciones desde *Turnos*.

## Guion de demostración sugerido

1. **jugador2** → *Mi cuenta*: saldo, estado y pérdidas de hoy frente al umbral.
2. **crup2** → *Mis mesas* → Mesa 1: registrar una apuesta de 600.000 (rechazada: máximo 500.000), otra de 400.000 a "Rojo" para jugador2, y cerrar con resultado `2` (negro). jugador2 queda **Suspendido 24 h** y recibe una notificación.
3. Intentar apostar con **jugador3** (suspendido): rechazado.
4. **crup3** → Mesa 3 (Póker, sin registro detallado): abrir ronda, cerrarla registrando las apuestas al evidenciar el resultado. Luego cambiar a rol **Jugador** desde el menú.
5. **sup1** → *Mis supervisiones*: emitir el concepto de un turno de ayer.
6. **admin** → *Turnos*: crear una asignación que viole RN-09 o RN-15 (rechazada); *Caja*: aprobar el retiro de jugador4; *Jugadores*: cerrar la investigación de E-SUP2; *Ganancias*; *Configuración* del umbral.

## Estructura

```
casino/       configuración (settings, urls) y utilidades de pruebas
cuentas/      Persona, Usuario (login ZK), Empleado, roles, gestión de empleados, comando seed
mesas/        Juego, Mesa, Competencia, Turno, AsignacionMesa, supervisión
juego/        Ronda, Apuesta, procesamiento de resultados, reporte de ganancias
jugadores/    Jugador, Movimiento, Configuracion, HistorialEstado, Notificacion, suspensiones
templates/    plantillas por app + base.html con menú por rol
static/js/zk.js   hash SHA-256 en el navegador (desafío–respuesta)
docs/documento-tecnico.md
```

La lógica de negocio está en `services.py` de cada app; las vistas solo orquestan.
