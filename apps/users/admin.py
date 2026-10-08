from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(ModelAdmin):
    list_display = ('user', 'display_name', 'created_at')
    search_fields = ('user__username', 'user__email', 'display_name')
    readonly_fields = ('id', 'created_at', 'updated_at')
    autocomplete_fields = ['user']
