from __future__ import unicode_literals, print_function, absolute_import
from django.conf import settings
from django.contrib.auth.views import login, logout
from django.urls import path, reverse
from django.views.generic import RedirectView
from .views import local_admin_login

app_name = "kirppuauth"

_urls = []


if not settings.KIRPPU_USE_SSO:
    _urls.append(path('login/', login, name='local_login', kwargs={
        "template_name": "kirppuauth/login.html",
        "extra_context": {
            "ask_pass": True,
            "submit": lambda: reverse('kirppuauth:local_login'),
        },
    }))

_urls.append(path('profile/', RedirectView.as_view(pattern_name="home", permanent=False)))
_urls.append(path('logout/', logout, name='local_logout', kwargs={
    "next_page": "home",
}))

if settings.KIRPPU_SU_AS_USER:
    _urls.append(path('set_user', local_admin_login, name='local_admin_login'))


urlpatterns = _urls
