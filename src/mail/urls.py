from django.urls import path

from mail.views import platform, tenant

urlpatterns = [
    path("administration/platform/mail/", platform.mail, name="platform_mail"),
    path("administration/platform/mail/test/", platform.test, name="platform_mail_test"),
    path("administration/tenant/sending-address/", tenant.sending_address, name="sending_address"),
    path("administration/tenant/sending-address/test/", tenant.test, name="sending_address_test"),
]
