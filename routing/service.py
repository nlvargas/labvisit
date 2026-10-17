from catalog.models import Exam


def estimate_minutes(order, exams=None):
    """Visit length: base, plus each distinct blood tube once, plus a fixed time for urine or stool."""
    lab = order.lab
    if exams is None:
        exams = order.selected_exams().select_related("container")
    tubes, unmapped, container = {}, False, False
    for exam in exams:
        if exam.sample_type in (Exam.SampleType.URINE, Exam.SampleType.STOOL):
            container = True
        elif exam.container_id:
            tubes[exam.container_id] = exam.container.minutes
        else:
            unmapped = True
    minutes = lab.service_base_min
    minutes += sum(lab.service_per_tube_min if m is None else m for m in tubes.values())
    if unmapped:
        minutes += lab.service_per_tube_min
    if container:
        minutes += lab.service_container_min
    return minutes


def service_minutes(order):
    return order.service_minutes if order.service_minutes is not None else estimate_minutes(order)
