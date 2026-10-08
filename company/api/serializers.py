from rest_framework import serializers

from company.models import Company, CompanyMembership


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "logo",
            "website",
            "is_active",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        )
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "updated_by")


class CompanyMembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyMembership
        fields = ("id", "user", "company", "role", "status", "joined_at")
        read_only_fields = ("id", "joined_at")
