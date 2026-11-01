import hmac

from django.contrib.auth.backends import BaseBackend

from .models import Usuario, sha256_hex

SESION_NONCE = 'zk_nonce'
SESION_USUARIO = 'zk_username'


class ZeroKnowledgeBackend(BaseBackend):
    """
    Autenticación desafío–respuesta:
      - el servidor guarda H = SHA256(salt + password) (calculado en el navegador);
      - en cada login entrega un nonce aleatorio de un solo uso;
      - el navegador envía R = SHA256(H + nonce);
      - aquí se recalcula SHA256(H_guardado + nonce) y se compara en tiempo constante.
    Ni la contraseña ni H viajan durante el login, y R no es reutilizable.
    """

    def authenticate(self, request, username=None, respuesta=None, **kwargs):
        if request is None or not username or not respuesta:
            return None
        # El nonce se consume siempre: un intento fallido invalida el desafío.
        nonce = request.session.pop(SESION_NONCE, None)
        usuario_desafio = request.session.pop(SESION_USUARIO, None)
        if not nonce or usuario_desafio != username:
            return None
        try:
            usuario = Usuario.objects.get(username=username)
        except Usuario.DoesNotExist:
            return None
        esperado = sha256_hex(usuario.password_hash + nonce)
        if hmac.compare_digest(esperado, respuesta.lower()) and usuario.is_active:
            return usuario
        return None

    def get_user(self, user_id):
        try:
            usuario = Usuario.objects.get(pk=user_id)
        except Usuario.DoesNotExist:
            return None
        return usuario if usuario.is_active else None

    # Permisos del admin de Django: el superusuario ya los tiene todos vía PermissionsMixin.
    def has_perm(self, user_obj, perm, obj=None):
        return user_obj.is_active and user_obj.is_superuser
