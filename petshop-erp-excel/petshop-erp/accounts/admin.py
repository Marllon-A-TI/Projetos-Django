from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import GRUPO_ADMINISTRADOR

User = get_user_model()

try:
    admin.site.unregister(User)
except NotRegistered:
    pass


@admin.register(User)
class UsuarioAdmin(UserAdmin):
    """
    O perfil de acesso vem do grupo (Administrador ou Vendedor).
    Somente administradores entram no /admin (is_staff), e isso é
    recalculado automaticamente ao salvar.
    """

    list_display = (
        "username",
        "nome_completo",
        "email",
        "perfil",
        "is_active",
        "last_login",
    )
    list_filter = ("is_active", "groups")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)
    filter_horizontal = ("groups",)
    readonly_fields = ("last_login", "date_joined")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Dados pessoais", {"fields": ("first_name", "last_name", "email")}),
        ("Acesso", {"fields": ("is_active", "groups")}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "first_name",
                    "last_name",
                    "email",
                    "groups",
                    "usable_password",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("groups")

    @admin.display(description="Nome")
    def nome_completo(self, obj):
        return obj.get_full_name() or "-"

    @admin.display(description="Perfil")
    def perfil(self, obj):
        return ", ".join(grupo.name for grupo in obj.groups.all()) or "-"

    def has_delete_permission(self, request, obj=None):
        # Usuários têm histórico (vendas, movimentações, logs): desative-os.
        return False

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        usuario = form.instance
        deve_ser_staff = (
            usuario.is_superuser
            or usuario.groups.filter(name=GRUPO_ADMINISTRADOR).exists()
        )
        if usuario.is_staff != deve_ser_staff:
            usuario.is_staff = deve_ser_staff
            usuario.save(update_fields=["is_staff"])