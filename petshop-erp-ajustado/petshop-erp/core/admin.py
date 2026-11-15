from django.contrib import admin

admin.site.site_header = "Pet Shop ERP"
admin.site.site_title = "Pet Shop ERP"
admin.site.index_title = "Administração do sistema"


class ImutavelAdminMixin:
    """Registro que, depois de criado, não pode ser alterado nem excluído."""

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SomenteLeituraAdminMixin(ImutavelAdminMixin):
    """Registro apenas para consulta: sem adicionar, alterar nem excluir."""

    def has_add_permission(self, request):
        return False