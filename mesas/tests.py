from datetime import time

from django.core.exceptions import ValidationError
from django.test import TestCase

from casino.pruebas import EscenarioCasino
from cuentas.models import Empleado
from mesas.models import AsignacionMesa, Juego, Mesa, Turno
from mesas.services import emitir_concepto, generar_turnos


class AsignacionesTests(TestCase):
    def setUp(self):
        self.e = EscenarioCasino()
        self.blackjack = Juego.objects.create(tipo_juego='Blackjack', registro_detallado=True)
        self.mesa_bj = Mesa.objects.create(juego=self.blackjack, monto_minimo=10, monto_maximo=100)
        self.fecha = self.e.turno.fecha

    def asignacion(self, turno, mesa, crupier, supervisor=None):
        return AsignacionMesa(turno=turno, mesa=mesa, crupier=crupier, supervisor=supervisor or self.e.supervisor)

    def test_turno_mayor_a_dos_horas_rechazado(self):
        with self.assertRaisesMessage(ValidationError, 'RN-10'):
            Turno(fecha=self.fecha.replace(year=2030), hora_inicio=time(8), hora_fin=time(10, 30)).full_clean()

    def test_turnos_solapados_rechazados(self):
        Turno.objects.create(fecha=self.fecha.replace(year=2030), hora_inicio=time(8), hora_fin=time(10))
        with self.assertRaisesMessage(ValidationError, 'solapa'):
            Turno(fecha=self.fecha.replace(year=2030), hora_inicio=time(9), hora_fin=time(11)).full_clean()

    def test_generar_turnos_del_dia(self):
        creados = generar_turnos(self.fecha.replace(year=2030), time(8), time(14), 90)
        self.assertEqual(len(creados), 4)
        self.assertTrue(all(t.duracion.total_seconds() <= 7200 for t in creados))

    def test_crupier_debe_conocer_el_juego(self):
        otro_turno = Turno.objects.create(fecha=self.fecha.replace(year=2030), hora_inicio=time(8), hora_fin=time(10))
        with self.assertRaisesMessage(ValidationError, 'RN-15'):
            self.asignacion(otro_turno, self.mesa_bj, self.e.crupier).full_clean()

    def test_crupier_una_mesa_por_turno(self):
        otra_ruleta = Mesa.objects.create(juego=self.e.ruleta, monto_minimo=10, monto_maximo=100)
        with self.assertRaisesMessage(ValidationError, 'RN-07'):
            self.asignacion(self.e.turno, otra_ruleta, self.e.crupier).full_clean()

    def test_crupier_no_repite_mesa_en_la_jornada(self):
        segundo = Turno.objects.create(fecha=self.fecha.replace(year=2030), hora_inicio=time(8), hora_fin=time(10))
        tercero = Turno.objects.create(fecha=self.fecha.replace(year=2030), hora_inicio=time(10), hora_fin=time(12))
        self.asignacion(segundo, self.e.mesa, self.e.crupier).save()
        with self.assertRaisesMessage(ValidationError, 'RN-09'):
            self.asignacion(tercero, self.e.mesa, self.e.crupier).full_clean()
        self.asignacion(tercero, self.e.mesa, self.e.crupier2).full_clean()  # rotación válida

    def test_supervisor_no_puede_ser_crupier(self):
        otro_turno = Turno.objects.create(fecha=self.fecha.replace(year=2030), hora_inicio=time(8), hora_fin=time(10))
        with self.assertRaises(ValidationError):
            self.asignacion(otro_turno, self.e.mesa, self.e.crupier, supervisor=self.e.crupier).full_clean()

    def test_concepto_solo_al_final_del_turno(self):
        with self.assertRaisesMessage(ValidationError, 'final del turno'):
            emitir_concepto(self.e.asignacion, self.e.supervisor, AsignacionMesa.Concepto.NEUTRO)
        pasado = Turno.objects.create(fecha=self.fecha.replace(year=2020), hora_inicio=time(8), hora_fin=time(10))
        a = AsignacionMesa.objects.create(turno=pasado, mesa=self.e.mesa, crupier=self.e.crupier,
                                          supervisor=self.e.supervisor)
        emitir_concepto(a, self.e.supervisor, AsignacionMesa.Concepto.FRAUDE)
        a.refresh_from_db()
        self.assertEqual(a.concepto_supervisor, 'Sospecha de fraude')
        otro_sup = self.e.empleado('sup9', '99', Empleado.Cargo.SUPERVISOR, [])
        with self.assertRaises(ValidationError):
            emitir_concepto(a, otro_sup, AsignacionMesa.Concepto.NEUTRO)
