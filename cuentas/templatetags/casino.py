from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()

CLASES_ESTADO = {
    'Activo': 'success', 'Suspendido': 'warning text-dark', 'Investigación': 'danger',
    'Pendiente': 'secondary', 'Ganada': 'success', 'Perdida': 'danger',
    'Aprobado': 'success', 'Rechazado': 'danger',
    'Genera ganancias': 'success', 'Genera pérdidas': 'warning text-dark',
    'Sospecha de fraude': 'danger', 'Comportamiento neutro': 'secondary',
}


@register.filter
def fichas(valor):
    """Formato colombiano: 1.234.567 o 1.234,50."""
    if valor in (None, ''):
        return '0'
    try:
        numero = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        return valor
    texto = f'{numero:,.0f}' if numero == numero.to_integral_value() else f'{numero:,.2f}'
    return texto.replace(',', '_').replace('.', ',').replace('_', '.')


@register.filter
def clase_estado(valor):
    return CLASES_ESTADO.get(valor, 'secondary')


@register.filter
def factor(valor):
    return f'{fichas(valor)}:1'
