from django.conf import settings
from django.http import HttpResponsePermanentRedirect
from django.http.request import split_domain_port, validate_host

from .models import Lab


def lab_slug_from_host(host, suffixes):
    host = host.split(":")[0].lower().removeprefix("www.")
    for suffix in suffixes:
        if host.endswith(suffix) and len(host) > len(suffix):
            return host[: -len(suffix)]
    return None


class LabMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        slug = lab_slug_from_host(request.get_host(), settings.LAB_HOST_SUFFIXES) or settings.DEFAULT_LAB_SLUG
        request.lab = Lab.objects.filter(slug=slug, is_active=True).first() if slug else None
        return self.get_response(request)


class StripWwwMiddleware:
    """Sends www.<host> to <host> so each lab has a single address."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.META.get("HTTP_HOST", "")
        if host.lower().startswith("www."):
            bare = host[4:]
            domain, _ = split_domain_port(bare)
            if domain and validate_host(domain, settings.ALLOWED_HOSTS):
                return HttpResponsePermanentRedirect(f"{request.scheme}://{bare}{request.get_full_path()}")
        return self.get_response(request)
