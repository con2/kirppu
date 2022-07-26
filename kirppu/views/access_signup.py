# -*- coding: utf-8 -*-
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _

from ..forms import AccessSignupForm
from ..models import AccessSignup, Event
from ..util import get_form


@login_required
def signup(request, event_slug: str):
    event = get_object_or_404(Event, slug=event_slug)
    if not event.access_signup:
        return HttpResponse(_("Signup is not enabled for the event"))

    if event.access_signup_token and request.GET.get("token") != event.access_signup_token:
        return HttpResponseForbidden()

    form_kwargs = {}
    try:
        instance = AccessSignup.objects.get(event=event, user=request.user)
        update_time = instance.update_time
        form_kwargs["initial"] = instance  # XXX: Django Form itself doesn't support this.
    except AccessSignup.DoesNotExist:
        instance = None
        update_time = None

    form = get_form(AccessSignupForm, request, **form_kwargs)
    if request.method == "POST" and form.is_valid():
        if form.has_changed():
            values = form.db_values()
            if instance is None:
                instance = AccessSignup(
                    event=event,
                    user=request.user,
                    **values
                )
                instance.save()
            else:
                for k, v in values.items():
                    setattr(instance, k, v)
                instance.save(update_fields=values.keys())
        return HttpResponseRedirect(reverse("kirppu:signup", kwargs=dict(event_slug=event_slug)))

    return render(request, "kirppu/access_signup.html", {
        "form": form,
        "update_time": update_time,
    })
