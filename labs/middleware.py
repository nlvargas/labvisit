from django.conf import settings

from .models import Lab


def lab_slug_from_host(host, suffixes):
    host = host.split(":")[0].lower()
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
