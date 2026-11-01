"""
Datos de prueba reproducibles:  python manage.py seed [--reset]

Crea usuarios de cada rol, juegos, mesas, turnos de ayer (finalizados) y de hoy
(el turno en curso se calcula según la hora actual), historial de apuestas y
jugadores en distintos estados. Todo pasa por los servicios y validaciones del sistema.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from cuentas.models import Empleado, Rol, Usuario, generar_salt, sha256_hex
from cuentas.services import crear_empleado
from juego import services as juego_services
from juego.models import Apuesta, Ronda
from jugadores import services as jugadores_services
from jugadores.models import Configuracion, Jugador, Movimiento
from mesas.models import AsignacionMesa, Juego, Mesa, Turno

PASSWORD = 'Casino123*'
D = Decimal


def credenciales():
    salt = generar_salt()
    return {'salt': salt, 'password_hash': sha256_hex(salt + PASSWORD)}


class Command(BaseCommand):
    help = 'Carga datos de prueba (usuarios de cada rol, mesas, turnos, rondas, apuestas y estados).'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Borra todos los datos antes de cargar.')

    def handle(self, *args, reset=False, **options):
        if Usuario.objects.exists() and not reset:
            raise CommandError('La base de datos ya tiene datos. Use "python manage.py seed --reset" para recargarla.')
        if reset:
            call_command('flush', interactive=False, verbosity=0)
        with transaction.atomic():
            self.preparar_catalogos()
            self.crear_personal()
            self.crear_turnos()
        # Las operaciones con servicios manejan sus propias transacciones.
        self.crear_jugadores()
        self.crear_historial_ayer()
        self.operar_turno_actual()
        self.resumen()

    # ------------------------------------------------------------------ catálogos

    def preparar_catalogos(self):
        for rol in Rol:
            Group.objects.get_or_create(name=rol.value)
        Configuracion.objects.update_or_create(clave=Configuracion.UMBRAL_PERDIDA_DIARIA,
                                               defaults={'valor': settings.CASINO_UMBRAL_PERDIDA_DEFECTO})
        self.ruleta = Juego.objects.create(tipo_juego='Ruleta', registro_detallado=True)
        self.blackjack = Juego.objects.create(tipo_juego='Blackjack', registro_detallado=True)
        self.poker = Juego.objects.create(tipo_juego='Póker', registro_detallado=False)
        self.m1 = Mesa.objects.create(juego=self.ruleta, monto_minimo=D(5000), monto_maximo=D(500000))
        self.m2 = Mesa.objects.create(juego=self.blackjack, monto_minimo=D(10000), monto_maximo=D(1000000))
        self.m3 = Mesa.objects.create(juego=self.poker, monto_minimo=D(20000), monto_maximo=D(2000000))
        self.m4 = Mesa.objects.create(juego=self.ruleta, monto_minimo=D(50000), monto_maximo=D(5000000))

    def crear_personal(self):
        def empleado(username, documento, nombre, cargo, salario, juegos, jugador=None):
            return crear_empleado(username=username, documento=documento, nombre_completo=nombre, cargo=cargo,
                                  salario=D(salario), juegos=juegos, datos_jugador=jugador, **credenciales())

        admin = empleado('admin', '1000000001', 'Ana María Restrepo', Empleado.Cargo.ADMINISTRADOR, 6000000, [])
        usuario_admin = admin.persona.usuario
        usuario_admin.is_superuser = True
        usuario_admin.save(update_fields=['is_superuser'])

        self.sup1 = empleado('sup1', '1000000011', 'Laura Gómez', Empleado.Cargo.SUPERVISOR, 3200000,
                             [self.ruleta, self.blackjack])
        self.sup2 = empleado('sup2', '1000000012', 'Carlos Rincón', Empleado.Cargo.SUPERVISOR, 3200000,
                             [self.blackjack, self.poker],
                             jugador={'codigo_cliente': 'E-SUP2', 'edad': 41, 'saldo_inicial': D(500000)})
        self.c1 = empleado('crup1', '1000000021', 'Andrea Ruiz', Empleado.Cargo.CRUPIER, 2500000,
                           [self.ruleta, self.blackjack])
        self.c2 = empleado('crup2', '1000000022', 'Miguel Torres', Empleado.Cargo.CRUPIER, 2500000,
                           [self.ruleta, self.poker])
        self.c3 = empleado('crup3', '1000000023', 'Sofía Herrera', Empleado.Cargo.CRUPIER, 2500000,
                           [self.blackjack, self.poker],
                           jugador={'codigo_cliente': 'E-CRU3', 'edad': 27, 'saldo_inicial': D(300000)})
        self.c4 = empleado('crup4', '1000000024', 'Daniel Castro', Empleado.Cargo.CRUPIER, 2500000,
                           [self.ruleta, self.blackjack, self.poker],
                           jugador={'codigo_cliente': 'E-CRU4', 'edad': 35, 'saldo_inicial': D(6000000)})

    # ------------------------------------------------------------------ turnos y asignaciones

    def turno(self, fecha, inicio, fin):
        t = Turno(fecha=fecha, hora_inicio=inicio, hora_fin=fin)
        t.full_clean()
        t.save()
        return t

    def asignar(self, turno, mesa, crupier, supervisor, concepto=None):
        a = AsignacionMesa(turno=turno, mesa=mesa, crupier=crupier, supervisor=supervisor,
                           concepto_supervisor=concepto)
        a.full_clean()  # valida RN-07, RN-09, RN-15
        a.save()
        return a

    def crear_turnos(self):
        ahora = timezone.localtime()
        self.ayer = ahora.date() - timedelta(days=1)
        C = AsignacionMesa.Concepto
        # Ayer: dos turnos finalizados con rotación de crupieres.
        self.y1 = self.turno(self.ayer, time(18), time(20))
        self.asignar(self.y1, self.m1, self.c1, self.sup1, C.GANANCIAS)
        self.asignar(self.y1, self.m2, self.c3, self.sup2, C.NEUTRO)
        self.asignar(self.y1, self.m3, self.c2, self.sup2, C.GANANCIAS)
        self.asignar(self.y1, self.m4, self.c4, self.sup1, C.PERDIDAS)
        self.y2 = self.turno(self.ayer, time(20), time(22))
        self.asignar(self.y2, self.m1, self.c4, self.sup1)  # conceptos pendientes para la demo del supervisor
        self.asignar(self.y2, self.m2, self.c1, self.sup2)
        self.asignar(self.y2, self.m3, self.c3, self.sup2)
        self.asignar(self.y2, self.m4, self.c2, self.sup1)

        # Hoy: turno en curso (desde la hora en punto actual, máx. 2 h) y el siguiente.
        hora = ahora.hour
        fin = time(hora + 2) if hora + 2 < 24 else time(23, 59)
        self.hoy_actual = self.turno(ahora.date(), time(hora), fin)
        self.asignar(self.hoy_actual, self.m1, self.c2, self.sup1)
        self.asignar(self.hoy_actual, self.m2, self.c1, self.sup2)
        self.asignar(self.hoy_actual, self.m3, self.c3, self.sup2)
        self.asignar(self.hoy_actual, self.m4, self.c4, self.sup1)
        if hora + 4 <= 23:
            siguiente = self.turno(ahora.date(), time(hora + 2), time(hora + 4))
            self.asignar(siguiente, self.m1, self.c1, self.sup1)
            self.asignar(siguiente, self.m2, self.c3, self.sup2)
            self.asignar(siguiente, self.m3, self.c2, self.sup2)
            # M4 queda sin asignar: todos los crupieres que conocen ruleta ya la atendieron hoy o están ocupados.

    # ------------------------------------------------------------------ jugadores

    def crear_jugadores(self):
        def jugador(username, documento, nombre, codigo, edad, saldo):
            return jugadores_services.registrar_jugador(
                username=username, documento=documento, nombre_completo=nombre, codigo_cliente=codigo,
                edad=edad, saldo_inicial=D(saldo), **credenciales())

        self.j1 = jugador('jugador1', '2000000001', 'Valentina Ortiz', 'J-0001', 30, 3000000)
        self.j2 = jugador('jugador2', '2000000002', 'Santiago Mejía', 'J-0002', 45, 2000000)
        self.j3 = jugador('jugador3', '2000000003', 'Camila Rojas', 'J-0003', 23, 800000)
        self.j4 = jugador('jugador4', '2000000004', 'Felipe Navarro', 'J-0004', 52, 1500000)
        self.e_sup2 = Jugador.objects.get(codigo_cliente='E-SUP2')
        self.e_cru3 = Jugador.objects.get(codigo_cliente='E-CRU3')
        self.e_cru4 = Jugador.objects.get(codigo_cliente='E-CRU4')
        try:
            jugador('menor', '2000000099', 'Tomás Menor', 'J-0099', 16, 0)
        except ValidationError as e:
            self.stdout.write(self.style.WARNING(f'Registro de menor de edad rechazado (esperado): {" ".join(e.messages)}'))

    def ronda_pasada(self, mesa, numero, inicio, resultado, apuestas):
        """Historial: ronda ya cerrada, procesada con la misma regla de comparación del sistema."""
        ronda = Ronda.objects.create(mesa=mesa, numero=numero, hora_inicio=inicio,
                                     hora_cierre=inicio + timedelta(minutes=4), resultado=resultado)
        ganadores = juego_services.resultados_ganadores(mesa.juego, resultado)
        for jugador, tipo, monto, factor in apuestas:
            gana = juego_services.normalizar(tipo) in ganadores
            premio = D(monto) * D(factor) if gana else D(0)
            Apuesta.objects.create(jugador=jugador, ronda=ronda, tipo_apuesta=tipo, monto_apostado=D(monto),
                                   factor_pago=D(factor), premio=premio,
                                   estado=Apuesta.Estado.GANADA if gana else Apuesta.Estado.PERDIDA)
            Jugador.objects.filter(pk=jugador.pk).update(saldo_fichas=F('saldo_fichas') + (premio if gana else -D(monto)))

    def crear_historial_ayer(self):
        en = lambda h, m: timezone.make_aware(datetime.combine(self.ayer, time(h, m)))
        self.ronda_pasada(self.m1, 1, en(18, 10), '17', [
            (self.j1, 'Pleno 17', 10000, 35), (self.j2, 'Rojo', 50000, 1), (self.j4, 'Impar', 20000, 1)])
        self.ronda_pasada(self.m1, 2, en(18, 40), '32', [
            (self.j1, 'Negro', 30000, 1), (self.j2, 'Rojo', 60000, 1)])
        self.ronda_pasada(self.m2, 1, en(18, 20), 'Asiento 1, Asiento 3', [
            (self.j1, 'Asiento 1', 100000, 1), (self.j2, 'Asiento 2', 100000, 1)])
        self.ronda_pasada(self.m3, 1, en(19, 15), 'Mano J-0004', [
            (self.j4, 'Mano J-0004', 50000, 1), (self.j1, 'Mano J-0001', 50000, 1)])
        # Supervisor que juega y gana más de 1 salario → Investigación (RN-30)
        self.ronda_pasada(self.m4, 1, en(18, 30), '17', [(self.e_sup2, 'Pleno 17', 100000, 35)])
        # Crupier que juega y pierde más de 2 salarios → Suspendido sin plazo (RN-29)
        self.ronda_pasada(self.m4, 2, en(20, 15), '0', [(self.e_cru4, 'Rojo', 2600000, 1)])
        self.ronda_pasada(self.m4, 3, en(20, 30), '0', [(self.e_cru4, 'Negro', 2600000, 1)])
        self.ronda_pasada(self.m2, 2, en(20, 45), 'Asiento 2', [(self.e_cru3, 'Asiento 2', 20000, 1)])
        for j in Jugador.objects.all():
            jugadores_services.actualizar_estado(j.pk)

    def operar_turno_actual(self):
        # Ronda cerrada hoy en la mesa 1 (crupier crup2): jugador2 pierde 900.000, cerca del umbral de 1.000.000.
        ronda = juego_services.abrir_ronda(self.m1, self.c2)
        juego_services.registrar_apuesta(ronda, self.j2, 'Pleno 7', D(400000), D(35), self.c2)
        juego_services.registrar_apuesta(ronda, self.j2, 'Negro', D(500000), D(1), self.c2)
        juego_services.registrar_apuesta(ronda, self.j1, 'Rojo', D(100000), D(1), self.c2)
        juego_services.cerrar_ronda(ronda, '1', self.c2)
        # Ronda abierta con una apuesta pendiente para la demo del crupier.
        ronda = juego_services.abrir_ronda(self.m1, self.c2)
        juego_services.registrar_apuesta(ronda, self.j1, 'Par', D(50000), D(1), self.c2)
        # Pausa voluntaria (RN-26) y solicitud de retiro pendiente.
        jugadores_services.solicitar_pausa(self.j3)
        jugadores_services.solicitar_movimiento(self.j4, Movimiento.Tipo.RETIRO, D(200000), 'Retiro en caja')
        jugadores_services.solicitar_movimiento(self.j1, Movimiento.Tipo.CONSIGNACION, D(500000), 'Transferencia')

    # ------------------------------------------------------------------ resumen

    def resumen(self):
        self.stdout.write(self.style.SUCCESS('\nDatos de prueba cargados. Contraseña de todos los usuarios: ' + PASSWORD))
        filas = [
            ('admin', 'Administrador', ''),
            ('sup1', 'Supervisor', 'Mesas 1 y 4'),
            ('sup2', 'Supervisor + Jugador', 'Jugador E-SUP2 en Investigación'),
            ('crup1', 'Crupier', 'Mesa 2 (Blackjack) en el turno actual'),
            ('crup2', 'Crupier', 'Mesa 1 (Ruleta) en el turno actual, ronda abierta'),
            ('crup3', 'Crupier + Jugador', 'Mesa 3 (Póker) en el turno actual; jugador E-CRU3 activo'),
            ('crup4', 'Crupier + Jugador', 'Mesa 4 (Ruleta VIP); jugador E-CRU4 suspendido por deuda'),
            ('jugador1', 'Jugador', 'Activo, con saldo'),
            ('jugador2', 'Jugador', 'Activo, cerca del umbral diario de pérdidas'),
            ('jugador3', 'Jugador', 'Suspendido 24 h (pausa voluntaria)'),
            ('jugador4', 'Jugador', 'Activo, retiro pendiente'),
        ]
        for usuario, rol, nota in filas:
            self.stdout.write(f'  {usuario:<10} {rol:<22} {nota}')
        for j in Jugador.objects.select_related('persona').order_by('codigo_cliente'):
            self.stdout.write(f'  [{j.codigo_cliente}] {j.persona.nombre_completo:<20} saldo={j.saldo_fichas:>12,.0f} estado={j.estado}')
