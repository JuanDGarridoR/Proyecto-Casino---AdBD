from django.urls import path

from . import views

app_name = 'cuentas'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('desafio/', views.desafio, name='desafio'),
    path('logout/', views.logout_view, name='logout'),
    path('registro/', views.registro, name='registro'),
    path('rol/<str:rol>/', views.cambiar_rol, name='cambiar_rol'),
    path('admin/', views.panel_admin, name='panel_admin'),
    path('empleados/', views.empleados_lista, name='empleados'),
    path('empleados/nuevo/', views.empleado_crear, name='empleado_crear'),
    path('empleados/<int:pk>/editar/', views.empleado_editar, name='empleado_editar'),
    path('empleados/<int:pk>/eliminar/', views.empleado_eliminar, name='empleado_eliminar'),
    path('empleados/<int:pk>/jugador/', views.empleado_habilitar_jugador, name='empleado_habilitar_jugador'),
]
