from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from casino.pruebas import EscenarioCasino, login_zk
from juego import services
from juego.models import Apuesta, Ronda
from jugadores.models import Jugador
from jugadores.services import solicitar_pausa

D = Decimal


class ApuestasTests(TestCase):
    def setUp(self):
        self.e = EscenarioCasino()
        self.ronda = services.abrir_ronda(self.e.mesa, self.e.crupier)

    def saldo(self, jugador=None):
        return Jugador.objects.get(pk=(jugador or self.e.jugador).pk).saldo_fichas

    def apostar(self, tipo='Rojo', monto=500, factor=1, jugador=None, crupier=None):
        return services.registrar_apuesta(self.ronda, jugador or self.e.jugador, tipo, D(monto), D(factor),
                                          crupier or self.e.crupier)

    def test_numero_correlativo_y_una_ronda_abierta(self):
        self.assertEqual(self.ronda.numero, 1)
        with self.assertRaisesMessage(ValidationError, 'ronda abierta'):
            services.abrir_ronda(self.e.mesa, self.e.crupier)

    def test_solo_el_crupier_asignado_opera_la_mesa(self):
        with self.assertRaisesMessage(ValidationError, 'no es el crupier asignado'):
            self.apostar(crupier=self.e.crupier2)

    def test_monto_fuera_de_limites(self):
        for monto in (99, 1001):
            with self.subTest(monto=monto), self.assertRaisesMessage(ValidationError, 'El monto debe estar entre'):
                self.apostar(monto=monto)
        self.apostar(monto=100)
        self.apostar(monto=1000)

    def test_saldo_insuficiente(self):
        pobre = self.e.nuevo_jugador('pobre', 'J-2', 150)
        with self.assertRaisesMessage(ValidationError, 'Saldo insuficiente'):
            self.apostar(monto=200, jugador=pobre)

    def test_monto_se_descuenta_al_apostar(self):
        self.apostar(monto=500)
        self.assertEqual(self.saldo(), D(4500))

    def test_jugador_suspendido_no_apuesta(self):
        solicitar_pausa(self.e.jugador)
        with self.assertRaisesMessage(ValidationError, 'Suspendido'):
            self.apostar()

    def test_procesamiento_automatico_ruleta(self):
        self.apostar('Pleno 17', 100, 35)
        self.apostar('Negro', 200, 1)
        self.apostar('Rojo', 300, 1)
        self.apostar('Par', 400, 1)
        services.cerrar_ronda(self.ronda, '17', self.e.crupier)
        estados = dict(Apuesta.objects.values_list('tipo_apuesta', 'estado'))
        self.assertEqual(estados, {'Pleno 17': 'Ganada', 'Negro': 'Ganada', 'Rojo': 'Perdida', 'Par': 'Perdida'})
        # 5000 − 1000 apostado + (3500 + 100) + (200 + 200)
        self.assertEqual(self.saldo(), D(8000))
        self.assertEqual(Apuesta.objects.get(tipo_apuesta='Pleno 17').premio, D(3500))
        ronda = Ronda.objects.get(pk=self.ronda.pk)
        self.assertIsNotNone(ronda.hora_cierre)
        with self.assertRaisesMessage(ValidationError, 'cerrada'):
            self.apostar()

    def test_modificar_y_anular_apuesta(self):
        apuesta = self.apostar(monto=500)
        services.modificar_apuesta(apuesta, 'Negro', D(800), D(1), self.e.crupier)
        self.assertEqual(self.saldo(), D(4200))
        services.anular_apuesta(apuesta, self.e.crupier)
        self.assertEqual(self.saldo(), D(5000))
        self.assertFalse(Apuesta.objects.exists())

    def test_juego_sin_registro_detallado(self):
        ronda = services.abrir_ronda(self.e.mesa_poker, self.e.crupier2)
        with self.assertRaisesMessage(ValidationError, 'no permite registro detallado'):
            services.registrar_apuesta(ronda, self.e.jugador, 'Mano J-1', D(500), D(1), self.e.crupier2)
        otro = self.e.nuevo_jugador('otro', 'J-3', 5000)
        services.cerrar_ronda(ronda, 'Mano J-1', self.e.crupier2, [
            {'jugador': self.e.jugador, 'tipo_apuesta': 'Mano J-1', 'monto_apostado': D(500), 'factor_pago': D(1)},
            {'jugador': otro, 'tipo_apuesta': 'Mano J-3', 'monto_apostado': D(500), 'factor_pago': D(1)},
        ])
        self.assertEqual(self.saldo(), D(5500))
        self.assertEqual(self.saldo(otro), D(4500))

    def test_flujo_web_del_crupier(self):
        login_zk(self.client, 'crup')
        url = f'/juego/ronda/{self.ronda.pk}/apostar/'
        self.client.post(url, {'jugador': self.e.jugador.pk, 'tipo_apuesta': 'Rojo', 'monto_apostado': '5000',
                               'factor_pago': '1'})
        self.assertFalse(Apuesta.objects.exists())  # supera el máximo de la mesa
        self.client.post(url, {'jugador': self.e.jugador.pk, 'tipo_apuesta': 'Rojo', 'monto_apostado': '500',
                               'factor_pago': '1'})
        self.assertEqual(Apuesta.objects.count(), 1)
        respuesta = self.client.post(f'/juego/ronda/{self.ronda.pk}/cerrar/', {'resultado': '3'})
        self.assertRedirects(respuesta, f'/juego/ronda/{self.ronda.pk}/')
        self.assertEqual(Apuesta.objects.get().estado, 'Ganada')
