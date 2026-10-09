from django.db.models.signals import post_save
from django.dispatch import receiver

from chat.models import Conversation
from company.models import CompanyMembership
from docs.models import Document


@receiver(post_save, sender=CompanyMembership)
def attach_unassigned_user_data_to_single_company(sender, instance, **kwargs):
    active_company_ids = list(
        CompanyMembership.objects.filter(
            user_id=instance.user_id,
            status=CompanyMembership.Status.ACTIVE,
            company__is_active=True,
        )
        .values_list("company_id", flat=True)
        .distinct()[:2]
    )
    if len(active_company_ids) != 1:
        return

    company_id = active_company_ids[0]
    Conversation.objects.filter(
        user_id=instance.user_id,
        company__isnull=True,
    ).update(company_id=company_id)
    Document.objects.filter(
        uploaded_by_id=instance.user_id,
        company__isnull=True,
    ).update(company_id=company_id)
