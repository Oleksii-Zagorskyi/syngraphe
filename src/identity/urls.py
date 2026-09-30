from django.urls import path

from identity.views import preferences, setup, signin

urlpatterns = [
    path("setup/", setup.setup, name="setup"),
    path("signin/", signin.signin, name="signin"),
    path("signout/", signin.signout, name="signout"),
    path("preferences/show-author/", preferences.show_author, name="preference_show_author"),
    path("preferences/outline-width/", preferences.outline_width, name="preference_outline_width"),
    path("preferences/panel-width/", preferences.panel_width, name="preference_panel_width"),
]
