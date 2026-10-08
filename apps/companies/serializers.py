from rest_framework import serializers
from .models import Company, CompanyMembership


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ('id', 'name', 'slug', 'description', 'website', 'is_active', 'created_at')
        read_only_fields = ('id', 'created_at')


class CompanyMembershipSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = CompanyMembership
        fields = ('id', 'company', 'username', 'role', 'status', 'joined_at')
        read_only_fields = ('id', 'joined_at')
