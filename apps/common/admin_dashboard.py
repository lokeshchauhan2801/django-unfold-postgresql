VISIBLE_ADMIN_MODELS = {
    ("audit", "auditlog"),
    ("auth", "user"),
    ("chat", "conversation"),
    ("chat", "message"),
    ("common", "systemsetting"),
    ("companies", "company"),
    ("companies", "companymembership"),
    ("documents", "document"),
    ("users", "userprofile"),
}


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
