from django.urls import path

from . import views

app_name = "produtos"

urlpatterns = [
    path("", views.ProdutoListView.as_view(), name="list"),
    path("novo/", views.ProdutoCreateView.as_view(), name="create"),
    path("importar/", views.ProdutoImportarView.as_view(), name="importar"),
    path("exportar/", views.ProdutoExportarView.as_view(), name="exportar"),
    path("<int:pk>/", views.ProdutoDetailView.as_view(), name="detail"),
    path("<int:pk>/editar/", views.ProdutoUpdateView.as_view(), name="update"),
    path(
        "<int:pk>/ativo/",
        views.ProdutoAlternarAtivoView.as_view(),
        name="alternar_ativo",
    ),
    path("<int:pk>/excluir/", views.ProdutoDeleteView.as_view(), name="delete"),
]