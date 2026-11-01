from django.test import TestCase

from casino.pruebas import PASSWORD, EscenarioCasino, login_zk
from cuentas.models import Usuario, sha256_hex


class LoginZeroKnowledgeTests(TestCase):
    def setUp(self):
        self.e = EscenarioCasino()

    def test_login_correcto_con_desafio_respuesta(self):
        respuesta = login_zk(self.client, 'jug')
        self.assertRedirects(respuesta, '/', fetch_redirect_response=False)
        self.assertEqual(self.client.session['rol_activo'], 'Jugador')

    def test_password_incorrecta_rechazada(self):
        login_zk(self.client, 'jug', 'otra-clave')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_respuesta_no_reutilizable(self):
        """Repetir R capturado no sirve: el nonce es de un solo uso."""
        desafio = self.client.post('/cuentas/desafio/', {'username': 'jug'}).json()
        r = sha256_hex(sha256_hex(desafio['salt'] + PASSWORD) + desafio['nonce'])
        self.client.post('/cuentas/login/', {'username': 'jug', 'respuesta': r})
        self.client.post('/cuentas/logout/')
        self.client.post('/cuentas/login/', {'username': 'jug', 'respuesta': r})
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_servidor_no_guarda_password_en_claro(self):
        usuario = Usuario.objects.get(username='jug')
        self.assertEqual(usuario.password_hash, sha256_hex(usuario.salt + PASSWORD))
        self.assertFalse(usuario.has_usable_password())

    def test_usuario_inexistente_recibe_salt_ficticio(self):
        datos = self.client.post('/cuentas/desafio/', {'username': 'nadie'}).json()
        self.assertEqual(len(datos['salt']), 32)

    def test_registro_rechaza_menor_de_edad(self):
        self.client.get('/cuentas/registro/')
        salt = self.client.session['zk_salt_registro']
        respuesta = self.client.post('/cuentas/registro/', {
            'username': 'nino', 'documento': '999', 'nombre_completo': 'Niño', 'codigo_cliente': 'J-9',
            'edad': 15, 'saldo_inicial': 0, 'password_hash': sha256_hex(salt + PASSWORD),
        })
        self.assertContains(respuesta, 'menores de edad')
        self.assertFalse(Usuario.objects.filter(username='nino').exists())


class ControlDeAccesoTests(TestCase):
    def setUp(self):
        self.e = EscenarioCasino()

    def test_jugador_no_accede_a_funciones_de_administrador(self):
        login_zk(self.client, 'jug')
        for url in ['/mesas/', '/cuentas/empleados/', '/jugadores/movimientos/', '/juego/mis-mesas/']:
            self.assertRedirects(self.client.get(url), '/', fetch_redirect_response=False)

    def test_menu_muestra_solo_funciones_del_rol(self):
        login_zk(self.client, 'crup')
        pagina = self.client.get('/juego/mis-mesas/')
        self.assertContains(pagina, 'Mis mesas')
        self.assertNotContains(pagina, 'Empleados')

    def test_anonimo_redirigido_al_login(self):
        self.assertRedirects(self.client.get('/mesas/'), '/cuentas/login/?next=/mesas/', fetch_redirect_response=False)

    def test_paginas_principales_por_rol(self):
        rutas = {
            'admin': ['/cuentas/admin/', '/mesas/', '/mesas/juegos/', '/mesas/turnos/', f'/mesas/turnos/{self.e.turno.pk}/',
                      '/cuentas/empleados/', '/cuentas/empleados/nuevo/', '/jugadores/', '/jugadores/movimientos/',
                      '/juego/ganancias/', '/jugadores/configuracion/', f'/jugadores/{self.e.jugador.pk}/',
                      '/mesas/asignaciones/nueva/', '/mesas/turnos/generar/'],
            'sup': ['/mesas/supervision/', f'/mesas/supervision/{self.e.asignacion.pk}/'],
            'crup': ['/juego/mis-mesas/', f'/juego/mesa/{self.e.mesa.pk}/'],
            'jug': ['/jugadores/panel/', '/jugadores/mis-movimientos/', '/jugadores/mi-historial/',
                    '/jugadores/notificaciones/', '/jugadores/pausa/'],
        }
        for usuario, urls in rutas.items():
            self.client.post('/cuentas/logout/')
            login_zk(self.client, usuario)
            for url in urls:
                with self.subTest(usuario=usuario, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)
