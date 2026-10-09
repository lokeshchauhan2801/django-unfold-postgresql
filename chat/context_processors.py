"""Context processors for the chat app."""

from django.urls import reverse

from company.access import active_company_for_request
from chat.models import Conversation


def admin_chat_history(request):
    """Expose the signed-in user's recent conversations to admin templates.

    Used by the admin sidebar to render a ChatGPT-style history list (recent
    conversation titles) beneath the app navigation. Scoped to the user's
    active company so a company admin only ever sees their own company's
    conversations; a superuser sees whatever company is active for them.
    """

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"admin_chat_history": []}

    # Only build the list for admin pages to avoid overhead elsewhere.
    if not request.path.startswith("/admin/"):
        return {"admin_chat_history": []}

    company = active_company_for_request(request)
    conversations = (
        Conversation.objects.filter(user=user, company=company)
        .order_by("-updated_at")
        .values_list("pk", "title")[:30]
    )

    base_url = reverse("admin:chat_conversation_new")
    history = [
        {
            "title": title or "New chat",
            "url": f"{base_url}?conversation={pk}",
        }
        for pk, title in conversations
    ]
    return {"admin_chat_history": history}
