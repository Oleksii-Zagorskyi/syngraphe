from django.urls import path

from identity.views import account, preferences, setup, signin, tokens, users

urlpatterns = [
    path("setup/", setup.setup, name="setup"),
    path("signin/", signin.signin, name="signin"),
    path("signout/", signin.signout, name="signout"),
    path("account/", account.account, name="account"),
    path("account/block/", account.block_account, name="block_account"),
    path("preferences/show-author/", preferences.show_author, name="preference_show_author"),
    path("preferences/outline-width/", preferences.outline_width, name="preference_outline_width"),
    path("preferences/panel-width/", preferences.panel_width, name="preference_panel_width"),
    path("preferences/outline-shut/", preferences.outline_shut, name="preference_outline_shut"),
    path("preferences/panel-shut/", preferences.panel_shut, name="preference_panel_shut"),
    path(
        "preferences/folder-tree-width/",
        preferences.folder_tree_width,
        name="preference_folder_tree_width",
    ),
    path("administration/tenant/users/", users.users, name="users"),
    path("administration/tenant/users/invite/", users.invite, name="invite"),
    path("administration/tenant/users/<uuid:membership_id>/", users.member, name="member"),
    path(
        "administration/tenant/users/<uuid:membership_id>/groups/",
        users.member_groups,
        name="member_groups",
    ),
    path(
        "administration/tenant/users/<uuid:membership_id>/block/",
        users.block,
        name="block_membership",
    ),
    path(
        "administration/tenant/users/<uuid:membership_id>/lift/",
        users.lift,
        name="lift_membership_block",
    ),
    path("invitation/<str:token>/", tokens.accept_invitation, name="accept_invitation"),
    path("reset/", tokens.reset_request, name="reset_request"),
    path("reset/<str:token>/", tokens.reset_password, name="reset_password"),
]
