from django.urls import path

from tenancy import views

urlpatterns = [
    path("administration/platform/tenants/", views.tenants, name="tenants"),
    path("administration/platform/tenants/new/", views.tenant_new, name="tenant_new"),
    path("administration/platform/hosts/", views.hosts, name="hosts"),
    path("administration/platform/administrators/", views.administrators, name="administrators"),
]
