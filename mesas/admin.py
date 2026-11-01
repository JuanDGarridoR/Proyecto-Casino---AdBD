from django.contrib import admin

from .models import AsignacionMesa, Competencia, Juego, Mesa, Turno


@admin.register(Juego)
class JuegoAdmin(admin.ModelAdmin):
    list_display = ('tipo_juego', 'registro_detallado')


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ('id_mesa', 'juego', 'monto_minimo', 'monto_maximo')
    list_filter = ('juego',)


@admin.register(Competencia)
class CompetenciaAdmin(admin.ModelAdmin):
    list_display = ('empleado', 'juego')
    list_filter = ('juego',)


@admin.register(Turno)
class TurnoAdmin(admin.ModelAdmin):
    list_display = ('id_turno', 'fecha', 'hora_inicio', 'hora_fin')
    date_hierarchy = 'fecha'


@admin.register(AsignacionMesa)
class AsignacionMesaAdmin(admin.ModelAdmin):
    list_display = ('turno', 'mesa', 'crupier', 'supervisor', 'concepto_supervisor')
    list_filter = ('turno__fecha', 'concepto_supervisor')
