VISIBLE_ADMIN_MODELS = {
    ("accounts", "user"),
    ("company", "company"),
    ("company", "companymembership"),
    ("scrapper", "document"),
    ("scrapper", "documentchunk"),
    ("scrapper", "queuemessage"),
    ("chat", "conversation"),
    ("chat", "message"),
    ("documents", "document"),
    ("audit", "auditlog"),
    ("basics", "systemsetting"),
}


def is_system_admin(request):
    return request.user.is_superuser


def admin_dashboard(_request, context):
    visible_apps = []
    for app in context["app_list"]:
        models = [
            model
            for model in app["models"]
            if (app["app_label"], model["object_name"].lower()) in VISIBLE_ADMIN_MODELS
        ]
        if models:
            visible_apps.append({**app, "models": models})

    context["app_list"] = visible_apps
    return context
