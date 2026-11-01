from django.contrib import admin

from .models import Apuesta, Ronda


class ApuestaInline(admin.TabularInline):
    model = Apuesta
    extra = 0
    readonly_fields = ('jugador', 'tipo_apuesta', 'monto_apostado', 'factor_pago', 'estado', 'premio')
    can_delete = False


@admin.register(Ronda)
class RondaAdmin(admin.ModelAdmin):
    # Solo lectura: las rondas y apuestas se operan con los servicios (validaciones y saldos).
    list_display = ('id_ronda', 'mesa', 'numero', 'hora_inicio', 'hora_cierre', 'resultado')
    list_filter = ('mesa',)
    inlines = [ApuestaInline]

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Apuesta)
class ApuestaAdmin(admin.ModelAdmin):
    list_display = ('id_apuesta', 'jugador', 'ronda', 'tipo_apuesta', 'monto_apostado', 'factor_pago', 'estado', 'premio')
    list_filter = ('estado',)

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False
