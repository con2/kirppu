from django.conf import settings
from django.urls import include, path
from django.utils import timezone
from django.views.i18n import JavaScriptCatalog
from django.views.decorators.http import last_modified

from kirppu.views import index, MobileRedirect
from kirppu.views.frontpage import front_for_mobile_view

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

js_packages = (
    'kirppu',
)

last_modified_date = timezone.now()

urlpatterns = [
    path('', index, name='home'),
    path(r'kirppu/', include('kirppu.urls', namespace="kirppu")),
    path(r'accounts/', include('kirppuauth.urls', namespace="kirppuauth")),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    path(r'admin/', admin.site.urls),
    path(r'i18n/', include('django.conf.urls.i18n')),
    path(r'jsi18n/', last_modified(lambda req, **kw: last_modified_date)(
        JavaScriptCatalog.as_view(packages=js_packages)),
        name="javascript-catalog"),
    path('m/<slug:event_slug>/', MobileRedirect.as_view()),
    path('m/', front_for_mobile_view),
]

if settings.KIRPPU_USE_SSO:
    urlpatterns.append(
        path('', include('kompassi_oauth2.urls'))
    )
