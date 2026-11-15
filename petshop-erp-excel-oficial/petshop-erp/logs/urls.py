from django.urls import path

from . import views

app_name = "logs"

urlpatterns = [
    path("", views.LogAcaoListView.as_view(), name="list"),
]