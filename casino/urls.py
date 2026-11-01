from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from cuentas.views import inicio

urlpatterns = [
    path('', inicio, name='inicio'),
    # El admin de Django usa el login Zero Knowledge propio (su login usa PBKDF2/check_password).
    path('admin/login/', RedirectView.as_view(url='/cuentas/login/?next=/admin/')),
    path('admin/', admin.site.urls),
    path('cuentas/', include('cuentas.urls')),
    path('mesas/', include('mesas.urls')),
    path('juego/', include('juego.urls')),
    path('jugadores/', include('jugadores.urls')),
]
