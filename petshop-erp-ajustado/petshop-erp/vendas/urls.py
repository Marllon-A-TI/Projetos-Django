from django.urls import path

from . import views

app_name = "vendas"

urlpatterns = [
    path("", views.VendaListView.as_view(), name="list"),
    path("nova/", views.VendaCreateView.as_view(), name="create"),
    path("<int:pk>/", views.VendaDetailView.as_view(), name="detail"),
]