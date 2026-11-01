from django.contrib import admin

from .models import Empleado, Persona, Usuario


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ('id_persona', 'documento', 'nombre_completo')
    search_fields = ('documento', 'nombre_completo')


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    # Las credenciales (salt/hash) solo se crean desde la interfaz propia con hash en el navegador.
    list_display = ('username', 'persona', 'is_active', 'is_staff', 'is_superuser')
    list_filter = ('is_active', 'groups')
    search_fields = ('username',)
    fields = ('username', 'persona', 'is_active', 'is_staff', 'is_superuser', 'groups', 'last_login')
    readonly_fields = ('last_login',)

    def has_add_permission(self, request):
        return False


@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = ('persona', 'cargo', 'salario')
    list_filter = ('cargo',)
