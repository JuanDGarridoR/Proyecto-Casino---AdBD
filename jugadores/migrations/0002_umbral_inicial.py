from django.conf import settings
from django.db import migrations


def crear_umbral(apps, schema_editor):
    Configuracion = apps.get_model('jugadores', 'Configuracion')
    Configuracion.objects.get_or_create(
        clave='umbral_perdida_diaria', defaults={'valor': settings.CASINO_UMBRAL_PERDIDA_DEFECTO},
    )


class Migration(migrations.Migration):
    dependencies = [('jugadores', '0001_initial')]
    operations = [migrations.RunPython(crear_umbral, migrations.RunPython.noop)]
