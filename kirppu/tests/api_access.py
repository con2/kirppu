# -*- coding: utf-8 -*-
import functools
import sys

from django.urls import reverse

from kirppu.ajax_util import get_all_ajax_functions

from . import color

_print = functools.partial(print, file=sys.stderr)


class Api(object):
    def __init__(self, client, event, debug=False):
        """
        :param client: Client to use.
        :param debug: If True, print when sending a request and received result.
        """
        def gen(method, view):
            url = reverse(view, kwargs={"event_slug": event.slug if hasattr(event, "slug") else event})

            def callback(**data):
                if debug:
                    _print(color(36, f"---> {method} {url}"), repr(data))
                ret = getattr(client, method)(url, data=data)
                self._check_response(ret)
                if debug:
                    _print(color(36, f"<--- {ret.status_code}"), self._response_json(ret))
                return ret
            callback.url = url
            callback.method = method
            return callback

        end_points = {}
        for name, func in get_all_ajax_functions():
            end_points[name] = gen(func.method.lower(), func.view)
        self._end_points = end_points

    def __getattr__(self, function):
        if function == '__wrapped__':  # Placate inspect.is_wrapper
            return False
        return self._end_points[function]

    @staticmethod
    def _response_json(response) -> str:
        try:
            return repr(response.json())
        except ValueError:
            content = response.content
            return repr(content[:256]) + ("..." if len(content) > 256 else "")

    def _check_response(self, response):
        pass
