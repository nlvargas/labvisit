def lab(request):
    return {"lab": getattr(request, "lab", None)}
