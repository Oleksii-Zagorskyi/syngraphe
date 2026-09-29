from django.urls import path

from access import views

urlpatterns = [
    path("administration/tenant/groups/", views.groups, name="groups"),
    path(
        "administration/tenant/groups/<uuid:group_id>/rights/",
        views.group_rights,
        name="group_rights",
    ),
    path(
        "administration/tenant/groups/<uuid:group_id>/members/",
        views.group_members,
        name="group_members",
    ),
    path("administration/tenant/document-links/", views.document_links, name="document_links"),
    path(
        "administration/tenant/document-links/<int:number>/",
        views.document_link,
        name="document_link",
    ),
]
