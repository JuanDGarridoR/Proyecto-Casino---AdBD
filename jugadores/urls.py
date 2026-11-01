from django.urls import path

from . import views

app_name = 'jugadores'

urlpatterns = [
    path('panel/', views.panel, name='panel'),
    path('pausa/', views.pausa, name='pausa'),
    path('mis-movimientos/', views.mis_movimientos, name='mis_movimientos'),
    path('mis-movimientos/<int:pk>/cancelar/', views.cancelar_movimiento, name='cancelar_movimiento'),
    path('mi-historial/', views.mi_historial, name='mi_historial'),
    path('notificaciones/', views.notificaciones, name='notificaciones'),
    path('', views.jugadores_lista, name='lista'),
    path('<int:pk>/', views.jugador_historial, name='historial'),
    path('<int:pk>/cerrar-investigacion/', views.cerrar_investigacion, name='cerrar_investigacion'),
    path('movimientos/', views.movimientos, name='movimientos'),
    path('movimientos/nuevo/', views.movimiento_nuevo, name='movimiento_nuevo'),
    path('movimientos/<int:pk>/editar/', views.movimiento_editar, name='movimiento_editar'),
    path('movimientos/<int:pk>/<str:accion>/', views.movimiento_accion, name='movimiento_accion'),
    path('configuracion/', views.configuracion, name='configuracion'),
]
