from django.urls import path

from . import views

app_name = "financeiro"

urlpatterns = [
    # --- Contas a pagar ---
    path(
        "contas-a-pagar/",
        views.ContaPagarListView.as_view(),
        name="pagar_list",
    ),
    path(
        "contas-a-pagar/nova/",
        views.ContaPagarCreateView.as_view(),
        name="pagar_create",
    ),
    path(
        "contas-a-pagar/<int:pk>/editar/",
        views.ContaPagarUpdateView.as_view(),
        name="pagar_update",
    ),
    path(
        "contas-a-pagar/<int:pk>/baixa/",
        views.ContaPagarBaixaView.as_view(),
        name="pagar_baixa",
    ),
    path(
        "contas-a-pagar/<int:pk>/cancelar/",
        views.ContaPagarCancelarView.as_view(),
        name="pagar_cancelar",
    ),
    path(
        "contas-a-pagar/<int:pk>/excluir/",
        views.ContaPagarDeleteView.as_view(),
        name="pagar_delete",
    ),
    # --- Contas a receber ---
    path(
        "contas-a-receber/",
        views.ContaReceberListView.as_view(),
        name="receber_list",
    ),
    path(
        "contas-a-receber/nova/",
        views.ContaReceberCreateView.as_view(),
        name="receber_create",
    ),
    path(
        "contas-a-receber/<int:pk>/editar/",
        views.ContaReceberUpdateView.as_view(),
        name="receber_update",
    ),
    path(
        "contas-a-receber/<int:pk>/baixa/",
        views.ContaReceberBaixaView.as_view(),
        name="receber_baixa",
    ),
    path(
        "contas-a-receber/<int:pk>/cancelar/",
        views.ContaReceberCancelarView.as_view(),
        name="receber_cancelar",
    ),
    path(
        "contas-a-receber/<int:pk>/excluir/",
        views.ContaReceberDeleteView.as_view(),
        name="receber_delete",
    ),
    # --- Fluxo de caixa ---
    path("caixa/", views.FluxoCaixaListView.as_view(), name="caixa_list"),
    path("caixa/novo/", views.FluxoCaixaCreateView.as_view(), name="caixa_create"),
]