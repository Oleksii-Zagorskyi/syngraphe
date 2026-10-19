from django.urls import path

from tenancy import settings_page, views

urlpatterns = [
    path("administration/platform/tenants/", views.tenants, name="tenants"),
    path("administration/platform/tenants/new/", views.tenant_new, name="tenant_new"),
    path("administration/platform/hosts/", views.hosts, name="hosts"),
    path("administration/platform/administrators/", views.administrators, name="administrators"),
    path("organisation/switch/", views.switch, name="switch_organisation"),
    path(
        "administration/tenant/settings/",
        settings_page.tenant_settings,
        name="tenant_settings",
    ),
    path(
        "administration/platform/administrators/grant/",
        views.administration_grant,
        name="administration_grant",
    ),
    path(
        "administration/platform/administrators/<uuid:user_id>/revoke/",
        views.administration_revoke,
        name="administration_revoke",
    ),
    path(
        "administration/platform/tenants/<int:number>/block/",
        views.tenant_block,
        name="tenant_block",
    ),
    path(
        "administration/platform/tenants/<int:number>/lift/", views.tenant_lift, name="tenant_lift"
    ),
    path(
        "administration/platform/tenants/<int:number>/appoint/",
        views.tenant_appoint,
        name="tenant_appoint",
    ),
]
