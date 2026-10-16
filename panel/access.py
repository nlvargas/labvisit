from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import Http404

from labs.models import LabMember


def is_staff_of(user, lab):
    if not user.is_authenticated or lab is None:
        return False
    return user.is_superuser or LabMember.objects.filter(user=user, lab=lab).exists()


def lab_staff_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.lab is None:
            raise Http404("Lab not found")
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not is_staff_of(request.user, request.lab):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper
