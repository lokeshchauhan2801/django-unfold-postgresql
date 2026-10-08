from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Company, CompanyMembership


@admin.register(Company)
class CompanyAdmin(ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'description')
    readonly_fields = ('id', 'created_at', 'updated_at')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(ModelAdmin):
    list_display = ('user', 'company', 'role', 'status', 'joined_at')
    list_filter = ('role', 'status', 'company')
    search_fields = ('user__username', 'user__email', 'company__name')
    readonly_fields = ('id', 'joined_at', 'created_at', 'updated_at')
    autocomplete_fields = ['company']
