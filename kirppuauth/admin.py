from django.contrib.auth.admin import UserAdmin
from django.contrib import admin

from .models import User


class KirppuUserAdmin(UserAdmin):
    fieldsets = list(UserAdmin.fieldsets)
    fieldsets[0] = (None, {"fields": ("username", "password", "kompassi_sub")})

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        fields.append("kompassi_sub")
        return fields


admin.site.register(User, KirppuUserAdmin)
