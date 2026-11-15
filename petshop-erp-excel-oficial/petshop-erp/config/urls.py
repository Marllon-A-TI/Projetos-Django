"""
Rotas principais do projeto Pet Shop ERP.
Cada app tem o seu próprio urls.py com app_name (namespace).
"""

from decouple import config
from django.contrib import admin
from django.urls import include, path

# O endereço do admin pode ser trocado no .env (DJANGO_ADMIN_URL) para
# dificultar varreduras automáticas em produção.
ADMIN_URL = (config("DJANGO_ADMIN_URL", default="admin/") or "admin/").strip("/") + "/"

urlpatterns = [
    path(ADMIN_URL, admin.site.urls),
    path("", include("core.urls")),
    path("contas/", include("accounts.urls")),
    path("produtos/", include("produtos.urls")),
    path("estoque/", include("estoque.urls")),
    path("vendas/", include("vendas.urls")),
    path("financeiro/", include("financeiro.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("logs/", include("logs.urls")),
]