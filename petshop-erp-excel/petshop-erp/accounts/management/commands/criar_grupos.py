from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from accounts.models import GRUPO_ADMINISTRADOR, GRUPO_VENDEDOR

APPS_ADMINISTRADOR = ("produtos", "estoque", "vendas", "financeiro", "logs")

PERMISSOES_VENDEDOR = (
    ("produtos", "view_produto"),
    ("vendas", "add_venda"),
    ("vendas", "view_venda"),
    ("vendas", "add_itemvenda"),
    ("vendas", "view_itemvenda"),
)


class Command(BaseCommand):
    help = (
        "Cria ou atualiza os grupos Administrador e Vendedor com as suas "
        "permissões. Pode ser executado quantas vezes for preciso."
    )

    def handle(self, *args, **options):
        permissoes_admin = Permission.objects.filter(
            Q(content_type__app_label__in=APPS_ADMINISTRADOR)
            | Q(content_type__app_label="auth", content_type__model__in=("user", "group"))
        )
        if not permissoes_admin.exists():
            raise CommandError(
                "Nenhuma permissão encontrada. Execute "
                "'python manage.py migrate' antes deste comando."
            )

        permissoes_vendedor = []
        for app, codigo in PERMISSOES_VENDEDOR:
            try:
                permissoes_vendedor.append(
                    Permission.objects.get(
                        content_type__app_label=app, codename=codigo
                    )
                )
            except Permission.DoesNotExist:
                raise CommandError(
                    f"Permissão {app}.{codigo} não encontrada. "
                    "Execute 'python manage.py migrate' antes deste comando."
                )

        grupo_admin, _ = Group.objects.get_or_create(name=GRUPO_ADMINISTRADOR)
        grupo_admin.permissions.set(permissoes_admin)

        grupo_vendedor, _ = Group.objects.get_or_create(name=GRUPO_VENDEDOR)
        grupo_vendedor.permissions.set(permissoes_vendedor)

        superusuarios = get_user_model().objects.filter(is_superuser=True)
        for usuario in superusuarios:
            usuario.groups.add(grupo_admin)

        self.stdout.write(
            self.style.SUCCESS(
                f"{GRUPO_ADMINISTRADOR}: {grupo_admin.permissions.count()} permissões | "
                f"{GRUPO_VENDEDOR}: {grupo_vendedor.permissions.count()} permissões | "
                f"superusuários no grupo {GRUPO_ADMINISTRADOR}: {superusuarios.count()}"
            )
        )