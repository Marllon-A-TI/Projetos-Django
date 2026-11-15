from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("senha/", views.AlterarSenhaView.as_view(), name="alterar_senha"),
    path("usuarios/", views.UsuarioListView.as_view(), name="usuario_list"),
    path("usuarios/novo/", views.UsuarioCreateView.as_view(), name="usuario_create"),
    path(
        "usuarios/<int:pk>/editar/",
        views.UsuarioUpdateView.as_view(),
        name="usuario_update",
    ),
    path(
        "usuarios/<int:pk>/senha/",
        views.UsuarioSenhaView.as_view(),
        name="usuario_senha",
    ),
]