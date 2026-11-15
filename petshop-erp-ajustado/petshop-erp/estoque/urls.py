from django.urls import path

from . import views

app_name = "estoque"

urlpatterns = [
    path("", views.MovimentacaoListView.as_view(), name="list"),
    path("nova/", views.MovimentacaoCreateView.as_view(), name="create"),
]