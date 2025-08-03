from django.conf import settings
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path, re_path, reverse
from django.views.generic import RedirectView
from .views import local_admin_login

app_name = "kirppuauth"

_urls = []


if not settings.KIRPPU_USE_SSO:
    _urls.append(path('login/', LoginView.as_view(
        template_name="kirppuauth/login.html",
        extra_context={
            "ask_pass": True,
            "submit": lambda: reverse('kirppuauth:local_login'),
        },
    ), name='local_login'))

_urls.append(path('profile/', RedirectView.as_view(pattern_name="home", permanent=False)))
_urls.append(re_path("logout/?", LogoutView.as_view(next_page="home"), name='local_logout'))

if settings.KIRPPU_SU_AS_USER:
    _urls.append(path('set_user', local_admin_login, name='local_admin_login'))


urlpatterns = _urls
