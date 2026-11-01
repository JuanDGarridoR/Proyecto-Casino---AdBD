from django.contrib import admin

from .models import Configuracion, HistorialEstado, Jugador, Movimiento, Notificacion


@admin.register(Jugador)
class JugadorAdmin(admin.ModelAdmin):
    list_display = ('codigo_cliente', 'persona', 'edad', 'saldo_fichas', 'estado', 'suspendido_hasta')
    list_filter = ('estado',)
    search_fields = ('codigo_cliente', 'persona__nombre_completo', 'persona__documento')
    # El saldo y el estado solo cambian mediante los servicios (movimientos, apuestas, suspensiones).
    readonly_fields = ('saldo_fichas', 'estado', 'suspendido_hasta')


@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ('id_movimiento', 'jugador', 'tipo', 'monto', 'estado', 'fecha')
    list_filter = ('tipo', 'estado')

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(Configuracion)
admin.site.register(HistorialEstado)
admin.site.register(Notificacion)
