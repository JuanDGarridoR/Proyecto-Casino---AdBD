from django.urls import path

from . import views

app_name = 'juego'

urlpatterns = [
    path('mis-mesas/', views.mis_mesas, name='mis_mesas'),
    path('mesa/<int:pk>/', views.panel_mesa, name='panel_mesa'),
    path('mesa/<int:pk>/abrir/', views.abrir_ronda, name='abrir_ronda'),
    path('ronda/<int:pk>/', views.ronda_detalle, name='ronda_detalle'),
    path('ronda/<int:pk>/apostar/', views.registrar_apuesta, name='registrar_apuesta'),
    path('ronda/<int:pk>/cerrar/', views.cerrar_ronda, name='cerrar_ronda'),
    path('ronda/<int:pk>/eliminar/', views.ronda_eliminar, name='ronda_eliminar'),
    path('apuesta/<int:pk>/editar/', views.apuesta_editar, name='apuesta_editar'),
    path('apuesta/<int:pk>/anular/', views.apuesta_anular, name='apuesta_anular'),
    path('ganancias/', views.reporte_ganancias, name='reporte_ganancias'),
]
