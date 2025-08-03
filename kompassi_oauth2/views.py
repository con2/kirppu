import typing

import requests
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse
from django.shortcuts import redirect, resolve_url
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import View
from requests_oauthlib import OAuth2Session


def get_session(request, **kwargs):
    return OAuth2Session(
        settings.KOMPASSI_OAUTH2_CLIENT_ID,
        redirect_uri=request.build_absolute_uri(reverse('oauth2_callback_view')),
        scope=settings.KOMPASSI_OAUTH2_SCOPE,  # XXX hardcoded scope
        **kwargs
    )


def get_redirect_url(request, redirect_to, fallback):
    # Ensure the user-originating redirection url is safe.
    if not url_has_allowed_host_and_scheme(url=redirect_to, allowed_hosts={request.get_host()}):
        redirect_to = resolve_url(fallback)
    return redirect_to


class LoginView(View):
    def get(self, request):
        authorization_url, state = get_session(request).authorization_url(settings.KOMPASSI_OAUTH2_AUTHORIZATION_URL)
        request.session['oauth_state'] = state
        request.session['oauth_next'] = request.GET.get('next', None)
        return redirect(authorization_url)


class CallbackView(View):
    def get(self, request):
        if 'oauth_state' not in request.session or 'oauth_next' not in request.session:
            return HttpResponse('OAuth2 callback accessed outside OAuth2 authorization flow', status=400)

        error = request.GET.get("error", None)
        if error:
            if error == "access_denied":
                # User pressed "cancel" on authorization.
                pass
            # TODO: Maybe set message?
            self._finish(request)
            return redirect("/")

        session = get_session(request, state=request.session['oauth_state'])
        token = session.fetch_token(
            settings.KOMPASSI_OAUTH2_TOKEN_URL,
            client_secret=settings.KOMPASSI_OAUTH2_CLIENT_SECRET,
            authorization_response=request.build_absolute_uri(),
        )

        # Store tokens for later revoke in logout.
        request.session['oauth_tokens'] = token

        next_url = request.session['oauth_next']

        self._finish(request)

        user = authenticate(request=request, oauth2_session=session)
        if user is not None and user.is_active:
            login(request, user)
            return redirect(get_redirect_url(request, next_url, settings.LOGIN_REDIRECT_URL))
        else:
            return HttpResponse('OAuth2 login failed', status=403)

    @staticmethod
    def _finish(request):
        del request.session['oauth_state']
        del request.session['oauth_next']


class LogoutView(View):
    @staticmethod
    def post(request):
        next_url: str = request.POST.get("next", None)
        next_url = get_redirect_url(request, next_url, "/")

        if "oauth_tokens" not in request.session:
            logout(request)
            return redirect(next_url)

        token: typing.Dict[str, str] = request.session["oauth_tokens"]

        # Server returns always 200.
        requests.post(settings.KOMPASSI_OAUTH2_REVOKE_URL, {
            "token": token["access_token"],
            "token_type_hint": "access_token",
            "client_id": settings.KOMPASSI_OAUTH2_CLIENT_ID,
            "client_secret": settings.KOMPASSI_OAUTH2_CLIENT_SECRET,
        })

        del request.session["oauth_tokens"]
        logout(request)

        return redirect(next_url)
