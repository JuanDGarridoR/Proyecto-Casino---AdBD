from django import forms

from cuentas.forms import EstiloBootstrapMixin

from .models import Jugador, Movimiento


class SolicitudMovimientoForm(EstiloBootstrapMixin, forms.Form):
    tipo = forms.ChoiceField(choices=Movimiento.Tipo.choices)
    monto = forms.DecimalField(label='Monto (fichas)', max_digits=12, decimal_places=2, min_value=0.01)
    observacion = forms.CharField(label='Observación', max_length=200, required=False)


class MovimientoAdminForm(SolicitudMovimientoForm):
    jugador = forms.ModelChoiceField(queryset=Jugador.objects.select_related('persona'))
    field_order = ['jugador', 'tipo', 'monto', 'observacion']


class UmbralForm(EstiloBootstrapMixin, forms.Form):
    umbral = forms.DecimalField(label='Umbral diario de pérdidas (fichas)', max_digits=12, decimal_places=2,
                                min_value=1, help_text='Si un jugador pierde más que este valor en un día, '
                                                       'su cuenta se suspende 24 horas (RN-25).')


class ObservacionForm(EstiloBootstrapMixin, forms.Form):
    observacion = forms.CharField(label='Observación', max_length=150, required=False)
