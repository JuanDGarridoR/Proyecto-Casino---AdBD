"""Utilidades compartidas por las pruebas de las apps."""
from datetime import time, timedelta
from decimal import Decimal

from django.utils import timezone

from cuentas.models import Empleado, generar_salt, sha256_hex
from cuentas.services import crear_empleado
from jugadores.services import registrar_jugador
from mesas.models import AsignacionMesa, Juego, Mesa, Turno

PASSWORD = 'Clave1234*'


def credenciales(password=PASSWORD):
    salt = generar_salt()
    return {'salt': salt, 'password_hash': sha256_hex(salt + password)}


def login_zk(client, username, password=PASSWORD):
    """Reproduce lo que hace static/js/zk.js en el navegador."""
    desafio = client.post('/cuentas/desafio/', {'username': username}).json()
    h = sha256_hex(desafio['salt'] + password)
    return client.post('/cuentas/login/', {'username': username, 'respuesta': sha256_hex(h + desafio['nonce'])})


class EscenarioCasino:
    """Ruleta con una mesa, un crupier y un supervisor asignados al turno en curso, y un jugador."""

    def __init__(self):
        self.ruleta = Juego.objects.create(tipo_juego='Ruleta', registro_detallado=True)
        self.poker = Juego.objects.create(tipo_juego='Póker', registro_detallado=False)
        self.mesa = Mesa.objects.create(juego=self.ruleta, monto_minimo=Decimal(100), monto_maximo=Decimal(1000))
        self.mesa_poker = Mesa.objects.create(juego=self.poker, monto_minimo=Decimal(100), monto_maximo=Decimal(5000))
        self.admin = self.empleado('admin', '1', Empleado.Cargo.ADMINISTRADOR, [])
        self.crupier = self.empleado('crup', '2', Empleado.Cargo.CRUPIER, [self.ruleta, self.poker])
        self.crupier2 = self.empleado('crup2', '3', Empleado.Cargo.CRUPIER, [self.ruleta, self.poker])
        self.supervisor = self.empleado('sup', '4', Empleado.Cargo.SUPERVISOR, [self.ruleta, self.poker])
        ahora = timezone.localtime()
        inicio = (ahora - timedelta(minutes=30)).time() if ahora.hour or ahora.minute >= 30 else time(0)
        fin = min(ahora + timedelta(minutes=60), ahora.replace(hour=23, minute=59, second=0))
        self.turno = Turno.objects.create(fecha=ahora.date(), hora_inicio=inicio, hora_fin=fin.time())
        self.asignacion = AsignacionMesa.objects.create(mesa=self.mesa, turno=self.turno, crupier=self.crupier,
                                                        supervisor=self.supervisor)
        AsignacionMesa.objects.create(mesa=self.mesa_poker, turno=self.turno, crupier=self.crupier2,
                                      supervisor=self.supervisor)
        self.jugador = self.nuevo_jugador('jug', 'J-1', 5000)

    def empleado(self, username, documento, cargo, juegos, salario=1000):
        return crear_empleado(username=username, documento=documento, nombre_completo=username.title(),
                              cargo=cargo, salario=Decimal(salario), juegos=juegos, **credenciales())

    def nuevo_jugador(self, username, codigo, saldo, edad=30):
        return registrar_jugador(username=username, documento=f'D-{codigo}', nombre_completo=username.title(),
                                 codigo_cliente=codigo, edad=edad, saldo_inicial=Decimal(saldo), **credenciales())
