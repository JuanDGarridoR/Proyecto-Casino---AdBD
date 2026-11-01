# 01 — Enunciado del Proyecto Framework

> **Fuente:** "Proyecto Framework" — Bases de Datos: Administración y Aplicaciones, Ing. Ricardo Naranjo Faccini, MSc. Pontificia Universidad Javeriana, Depto. de Ingeniería de Sistemas.
> **Propósito de este archivo:** reglas del juego del proyecto (qué se evalúa, qué es obligatorio, qué se entrega y cuándo). Para el dominio del casino ver `02-contexto-casino.md` y `03-requerimientos.md`; para el esquema ver `04-modelo-datos.md`.

## Equipo

- Juan David Garrido Ramos
- Andrés Felipe Torres Monroy
- Alejandro Urbina

**Framework asignado:** **Django** (Python)
Todo el proyecto debe usar **exclusivamente** Django. No mezclar con otros frameworks web (nada de Flask, FastAPI, ni un SPA en React/Angular/Vue como frontend separado). La interfaz se hace con el sistema de plantillas de Django; JavaScript plano solo donde haga falta (p. ej. el hash SHA-256 del login en el navegador).

## Objetivo

Desarrollar una **aplicación web completa para la gestión de un casino**, basada en el contexto del primer parcial, que incluya:

- Autenticación de usuarios (**Zero Knowledge**)
- Control de acceso por roles
- Persistencia en base de datos
- Interfaz web funcional

## Requisitos funcionales mínimos

### Autenticación
- Sistema de login
- Manejo de sesiones (usar el framework de sesiones de Django: `django.contrib.sessions`, `login()` / `logout()`)
- Contraseñas almacenadas con **SHA-256**
- Esquema **Zero Knowledge**: la contraseña en texto plano no debe viajar al servidor ni guardarse. (Interpretación a confirmar con el docente: el cliente calcula el hash SHA-256 en el navegador; idealmente con desafío/nonce de sesión para que el hash enviado no sea reutilizable.)

#### Propuesta de implementación en Django (desafío–respuesta)
1. **Registro:** el navegador calcula `H = SHA256(salt + password)` con `crypto.subtle.digest` y envía solo `H`. El servidor guarda `salt` y `H`.
2. **Login, paso 1:** el usuario envía su `username`; el servidor responde con su `salt` y un `nonce` aleatorio (`secrets.token_hex`) guardado en la sesión.
3. **Login, paso 2:** el navegador calcula `R = SHA256(H + nonce)` y envía `R`.
4. **Verificación:** un **authentication backend** propio (`AUTHENTICATION_BACKENDS`) recalcula `SHA256(H_guardado + nonce_sesion)`, compara con `hmac.compare_digest`, invalida el nonce y llama a `login()`.
- No usar `check_password` / `set_password` de Django: su hasher por defecto es PBKDF2, no SHA-256. Si se usa un modelo de usuario propio, la columna de contraseña de Django queda sin uso (`set_unusable_password()`).
- Limitación a mencionar en la exposición: `H` guardado en la BD equivale a la contraseña si la BD se filtra; además SHA-256 simple es rápido de atacar por fuerza bruta. Es una exigencia del curso, no una recomendación de producción.

### Control de acceso por roles
Según el rol, el sistema muestra **únicamente** las funcionalidades permitidas. Roles base: Administrador, Supervisor, Crupier, Jugador (ver `03-requerimientos.md`).

## Casos de uso obligatorios — mínimo 3 de:

1. Gestión de mesas
2. Gestión de rondas
3. Gestión de apuestas
4. Gestión de ganancias
5. Gestión de suspensiones
6. Gestión de consignaciones/retiros

"Gestión" implica **CRUD completo** respetando las restricciones del contexto.

**Elegidos:** los 6 (mesas, rondas, apuestas, ganancias, suspensiones, consignaciones/retiros).

## Funcionalidades adicionales

- **Obligatoria:** Interfaz de usuario (por rol).
- **Mínimo 3 adicionales** de:
  1. Notificaciones
  2. Gestión de empleados
  3. Historial de clientes
  4. Validación de autorizaciones/suspensiones

**Elegidas:** las 4 (notificaciones, gestión de empleados, historial de clientes, validación de autorizaciones/suspensiones).

## Requisitos técnicos

- No es obligatorio PHP ni PostgreSQL.
- Usar el framework asignado.
- Base de datos relacional o NoSQL, con persistencia real.
- Lógica de negocio correctamente implementada.
- Arquitectura **coherente con el framework** (seguir sus convenciones idiomáticas, no forzar otra estructura).

### Arquitectura esperada en Django (MTV)

- **Model–Template–View**: modelos en `models.py`, vistas en `views.py`, plantillas en `templates/`, rutas en `urls.py`.
- Proyecto Django con apps separadas por dominio, por ejemplo:
  - `cuentas` — personas, usuarios, login Zero Knowledge, roles
  - `mesas` — juegos, mesas, competencias, turnos, asignaciones
  - `juego` — rondas, apuestas, procesamiento de resultados
  - `jugadores` — saldo, consignaciones/retiros, suspensiones, historial, notificaciones
- Lógica de negocio en un módulo `services.py` por app (no en las vistas ni en las plantillas); las vistas solo orquestan.
- Formularios con `django.forms` / `ModelForm` para validar entradas.
- Migraciones de Django (`makemigrations` / `migrate`) como única forma de crear el esquema.
- Datos de prueba con un management command (`python manage.py seed`) o fixtures.
- Base de datos: **SQLite por defecto; PostgreSQL configurable con `DB_ENGINE=postgresql` en `.env`**. Se recomienda PostgreSQL por soporte de constraints; SQLite sirve para desarrollo.

## Entregables

1. **Código fuente:** proyecto completo y funcional + instrucciones de instalación (README).
2. **Documento técnico:**
   - Descripción del framework
   - Arquitectura utilizada
   - Modelo de datos
   - Explicación de funcionalidades implementadas
   - Dificultades encontradas
3. **Evidencia de funcionamiento:** datos de prueba (seed) + capturas o demostración.

## Fechas

| Fecha | Hito |
|---|---|
| 2026-10-02 | Entrega de los 3 frameworks priorizados |
| 2026-10-05 | Asignación del framework |
| **2026-11-03** | **Entrega del proyecto** |
| 2026-11-09 y 2026-11-23 | Exposiciones |

## Exposición final (45 min)

- Introducción al framework
- Demo del sistema funcionando
- Explicación técnica de la solución
- Análisis crítico del framework: calidad, facilidad de uso, curva de aprendizaje, ventajas, desventajas, limitaciones
- Conclusiones y recomendaciones

Se evalúa **tanto la implementación como el análisis crítico**.

## Implicaciones para el desarrollo (guía para Claude Code)

- Priorizar que lo obligatorio funcione de punta a punta antes de pulir: login ZK + SHA-256, roles, 3 casos de uso con CRUD, interfaz por rol, 3 funcionalidades adicionales.
- Toda regla de negocio debe validarse en el **servidor** (y si es posible también en la BD), no solo en el frontend.
- Mantener un script de **datos de prueba** reproducible (usuarios de cada rol, mesas, juegos, turnos, jugadores en distintos estados).
- Ir anotando dificultades y decisiones técnicas: alimentan el documento técnico y el análisis crítico.
- Puntos de Django que conviene registrar para el análisis crítico: el hasher por defecto (PBKDF2) no cumple el requisito SHA-256 y hay que adaptar la autenticación; el admin de Django como ventaja para CRUDs; el ORM vs. reglas complejas en BD; manejo de transacciones con `transaction.atomic`; curva de aprendizaje de la estructura proyecto/apps.
- Instrucciones de instalación mínimas: crear `venv`, `pip install -r requirements.txt`, configurar `.env` (credenciales de BD, `SECRET_KEY`), `migrate`, `seed`, `runserver`.
