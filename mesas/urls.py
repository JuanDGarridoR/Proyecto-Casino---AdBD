from django.urls import path

from . import views

app_name = 'mesas'

urlpatterns = [
    path('juegos/', views.juegos_lista, name='juegos'),
    path('juegos/nuevo/', views.juego_crear, name='juego_crear'),
    path('juegos/<int:pk>/editar/', views.juego_editar, name='juego_editar'),
    path('juegos/<int:pk>/eliminar/', views.juego_eliminar, name='juego_eliminar'),
    path('', views.mesas_lista, name='mesas'),
    path('nueva/', views.mesa_crear, name='mesa_crear'),
    path('<int:pk>/editar/', views.mesa_editar, name='mesa_editar'),
    path('<int:pk>/eliminar/', views.mesa_eliminar, name='mesa_eliminar'),
    path('turnos/', views.turnos_lista, name='turnos'),
    path('turnos/nuevo/', views.turno_crear, name='turno_crear'),
    path('turnos/generar/', views.turno_generar, name='turno_generar'),
    path('turnos/<int:pk>/', views.turno_detalle, name='turno_detalle'),
    path('turnos/<int:pk>/editar/', views.turno_editar, name='turno_editar'),
    path('turnos/<int:pk>/eliminar/', views.turno_eliminar, name='turno_eliminar'),
    path('asignaciones/nueva/', views.asignacion_crear, name='asignacion_crear'),
    path('asignaciones/<int:pk>/editar/', views.asignacion_editar, name='asignacion_editar'),
    path('asignaciones/<int:pk>/eliminar/', views.asignacion_eliminar, name='asignacion_eliminar'),
    path('supervision/', views.supervision, name='supervision'),
    path('supervision/<int:pk>/', views.supervision_detalle, name='supervision_detalle'),
]
