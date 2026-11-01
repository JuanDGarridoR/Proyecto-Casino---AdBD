from django.db import migrations

ROLES = ['Administrador', 'Supervisor', 'Crupier', 'Jugador']


def crear_grupos(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for rol in ROLES:
        Group.objects.get_or_create(name=rol)


def borrar_grupos(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('cuentas', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]
    operations = [migrations.RunPython(crear_grupos, borrar_grupos)]
