from django import forms

from cuentas.forms import EstiloBootstrapMixin
from jugadores.models import Jugador


class CampoJugador(forms.ModelChoiceField):
    def label_from_instance(self, jugador):
        return f'{jugador.codigo_cliente} — {jugador.persona.nombre_completo} ({jugador.estado})'


class ApuestaForm(EstiloBootstrapMixin, forms.Form):
    jugador = CampoJugador(queryset=Jugador.objects.select_related('persona'))
    tipo_apuesta = forms.CharField(max_length=100, label='Tipo de apuesta',
                                   widget=forms.TextInput(attrs={'list': 'sugerencias-apuesta'}))
    monto_apostado = forms.DecimalField(label='Monto (fichas)', max_digits=12, decimal_places=2, min_value=0.01)
    factor_pago = forms.DecimalField(label='Factor de pago (X:1)', max_digits=8, decimal_places=2, min_value=0.01)


class ApuestaEditarForm(EstiloBootstrapMixin, forms.Form):
    tipo_apuesta = forms.CharField(max_length=100, label='Tipo de apuesta',
                                   widget=forms.TextInput(attrs={'list': 'sugerencias-apuesta'}))
    monto_apostado = forms.DecimalField(label='Monto (fichas)', max_digits=12, decimal_places=2, min_value=0.01)
    factor_pago = forms.DecimalField(label='Factor de pago (X:1)', max_digits=8, decimal_places=2, min_value=0.01)


class CerrarRondaForm(EstiloBootstrapMixin, forms.Form):
    resultado = forms.CharField(
        max_length=100, label='Resultado ganador',
        help_text='Ej.: "17" en ruleta (se deducen color, paridad, mitad y docena) o '
                  '"Asiento 1, Asiento 3". Varias opciones ganadoras separadas por comas.',
    )


class ApuestaAlResultadoForm(ApuestaForm):
    """Fila del formset para juegos sin registro detallado (RN-24)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.required = False

    def clean(self):
        datos = super().clean()
        llenos = [k for k in ('jugador', 'tipo_apuesta', 'monto_apostado', 'factor_pago') if datos.get(k)]
        if llenos and len(llenos) < 4:
            raise forms.ValidationError('Complete todos los campos de la apuesta o deje la fila vacía.')
        return datos


ApuestasAlResultadoFormSet = forms.formset_factory(ApuestaAlResultadoForm, extra=5)
