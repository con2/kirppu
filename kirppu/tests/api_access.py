# -*- coding: utf-8 -*-
import functools
import sys

from django.urls import reverse

from . import color
from kirppu.ajax_util import get_all_ajax_functions

__author__ = 'codez'


class Api(object):
    def __init__(self, client, event, debug=False):
        """
        :param client: Client to use.
        :param debug: If True, print when sending a request and received result.
        """
        if debug:
            _print = functools.partial(print, file=sys.stderr)
        else:
            def _print(*args):
                pass

        def gen(method, view):
            url = reverse(view, kwargs={"event_slug": event.slug if hasattr(event, "slug") else event})

            def callback(**data):
                _print(color(36, "---> " + method), color(36, url), repr(data))
                ret = getattr(client, method)(url, data=data)
                self._check_response(ret)
                _print(color(36, "<--- " + str(ret.status_code)), self._opt_json(ret))
                return ret
            callback.url = url
            callback.method = method
            return callback

        self._end_points = {}
        for name, func in get_all_ajax_functions():
            self._end_points[name] = gen(func.method.lower(), func.view)

    def __getattr__(self, function):
        if function == '__wrapped__':  # Placate inspect.is_wrapper
            return False
        return self._end_points[function]

    @staticmethod
    def _opt_json(response):
        try:
            return repr(response.json())
        except:
            return ""

    def _check_response(self, response):
        pass
