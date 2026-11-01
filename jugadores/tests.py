from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from casino.pruebas import EscenarioCasino, login_zk
from juego import services as juego
from jugadores import services
from jugadores.models import Configuracion, EstadoCuenta, Jugador, Movimiento, Notificacion

D = Decimal


class SuspensionesTests(TestCase):
    def setUp(self):
        self.e = EscenarioCasino()
        Configuracion.objects.update_or_create(clave=Configuracion.UMBRAL_PERDIDA_DIARIA, defaults={'valor': '1500'})

    def jugar_y_perder(self, jugador, montos):
        ronda = juego.abrir_ronda(self.e.mesa, self.e.crupier)
        for monto in montos:
            juego.registrar_apuesta(ronda, jugador, 'Rojo', D(monto), D(1), self.e.crupier)
        juego.cerrar_ronda(ronda, '2', self.e.crupier)  # 2 = negro → pierde
        return Jugador.objects.get(pk=jugador.pk)

    def test_perdidas_del_dia_superan_umbral(self):
        jugador = self.jugar_y_perder(self.e.jugador, [1000])
        self.assertEqual(jugador.estado, EstadoCuenta.ACTIVO)
        jugador = self.jugar_y_perder(jugador, [600])
        self.assertEqual(jugador.estado, EstadoCuenta.SUSPENDIDO)
        self.assertAlmostEqual(jugador.suspendido_hasta, timezone.now() + timedelta(hours=24), delta=timedelta(minutes=1))
        self.assertTrue(Notificacion.objects.filter(persona_id=jugador.pk, mensaje__contains='SUSPENDIDA').exists())
        self.assertEqual(jugador.historial_estados.first().estado_nuevo, EstadoCuenta.SUSPENDIDO)

    def test_suspension_vence_a_las_24_horas(self):
        services.solicitar_pausa(self.e.jugador)
        Jugador.objects.filter(pk=self.e.jugador.pk).update(suspendido_hasta=timezone.now() - timedelta(seconds=1))
        jugador = services.actualizar_estado(self.e.jugador.pk)
        self.assertEqual(jugador.estado, EstadoCuenta.ACTIVO)

    def test_empleado_con_ganancias_mayores_a_un_salario_queda_en_investigacion(self):
        empleado_jugador = services.habilitar_empleado_como_jugador(
            self.e.supervisor, codigo_cliente='E-1', edad=40, saldo_inicial=D(5000))  # salario 1000
        ronda = juego.abrir_ronda(self.e.mesa, self.e.crupier)
        juego.registrar_apuesta(ronda, empleado_jugador, 'Pleno 5', D(100), D(35), self.e.crupier)
        juego.cerrar_ronda(ronda, '5', self.e.crupier)
        empleado_jugador.refresh_from_db()
        self.assertEqual(empleado_jugador.estado, EstadoCuenta.INVESTIGACION)
        # Solo un administrador la cierra; las ganancias se cuentan desde cero tras el cierre.
        empleado_jugador = services.cerrar_investigacion(empleado_jugador, 'Revisado')
        self.assertEqual(empleado_jugador.estado, EstadoCuenta.ACTIVO)

    def test_empleado_con_perdidas_mayores_a_dos_salarios_se_suspende_sin_plazo(self):
        empleado_jugador = services.habilitar_empleado_como_jugador(
            self.e.supervisor, codigo_cliente='E-1', edad=40, saldo_inicial=D(5000))
        Configuracion.objects.filter(clave=Configuracion.UMBRAL_PERDIDA_DIARIA).update(valor='999999')
        empleado_jugador = self.jugar_y_perder(empleado_jugador, [1000, 1000, 500])  # 2500 > 2 × 1000
        self.assertEqual(empleado_jugador.estado, EstadoCuenta.SUSPENDIDO)
        self.assertIsNone(empleado_jugador.suspendido_hasta)
        # La deuda baja (las pérdidas salen de la ventana de 30 días) → reactivación automática.
        from juego.models import Ronda
        hace_un_mes = timezone.now() - timedelta(days=31)
        Ronda.objects.update(hora_inicio=hace_un_mes, hora_cierre=hace_un_mes)
        self.assertEqual(services.actualizar_estado(empleado_jugador.pk).estado, EstadoCuenta.ACTIVO)


class MovimientosTests(TestCase):
    def setUp(self):
        self.e = EscenarioCasino()

    def test_retiro_no_supera_saldo(self):
        with self.assertRaisesMessage(ValidationError, 'Saldo insuficiente'):
            services.registrar_movimiento(self.e.jugador, Movimiento.Tipo.RETIRO, D(6000))
        services.registrar_movimiento(self.e.jugador, Movimiento.Tipo.RETIRO, D(2000))
        self.assertEqual(Jugador.objects.get(pk=self.e.jugador.pk).saldo_fichas, D(3000))

    def test_solicitud_del_jugador_y_aprobacion(self):
        login_zk(self.client, 'jug')
        self.client.post('/jugadores/mis-movimientos/', {'tipo': 'Consignacion', 'monto': '1000', 'observacion': ''})
        movimiento = Movimiento.objects.get(estado=Movimiento.Estado.PENDIENTE)
        self.assertEqual(Jugador.objects.get(pk=self.e.jugador.pk).saldo_fichas, D(5000))
        self.client.post('/cuentas/logout/')
        login_zk(self.client, 'admin')
        self.client.post(f'/jugadores/movimientos/{movimiento.pk}/aprobar/')
        self.assertEqual(Jugador.objects.get(pk=self.e.jugador.pk).saldo_fichas, D(6000))

    def test_retiros_pendientes_comprometen_saldo(self):
        services.solicitar_movimiento(self.e.jugador, Movimiento.Tipo.RETIRO, D(4000))
        with self.assertRaises(ValidationError):
            services.solicitar_movimiento(self.e.jugador, Movimiento.Tipo.RETIRO, D(2000))

    def test_pausa_voluntaria_desde_la_web(self):
        login_zk(self.client, 'jug')
        self.client.post('/jugadores/pausa/')
        jugador = Jugador.objects.get(pk=self.e.jugador.pk)
        self.assertEqual(jugador.estado, EstadoCuenta.SUSPENDIDO)
        self.assertIsNotNone(jugador.suspendido_hasta)
