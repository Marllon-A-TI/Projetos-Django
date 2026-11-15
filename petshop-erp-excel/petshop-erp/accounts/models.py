"""
O app accounts usa o modelo de usuário padrão do Django
(django.contrib.auth.models.User) com Grupos e Permissões.

Aqui ficam apenas os nomes oficiais dos grupos, usados pelos demais apps
e criados na Etapa 10.
"""

GRUPO_ADMINISTRADOR = "Administrador"
GRUPO_VENDEDOR = "Vendedor"

GRUPOS = (GRUPO_ADMINISTRADOR, GRUPO_VENDEDOR)