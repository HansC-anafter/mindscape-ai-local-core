"""Trusted remote-ingress predicate without a second policy read."""

from .contracts import RootAdmissionRequest


def remote_entry_permitted(request: RootAdmissionRequest) -> bool:
    if request.entry == "local":
        return True
    return request.remote_ingress_verified

