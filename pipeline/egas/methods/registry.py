from __future__ import annotations

from egas.contract import Contract
from egas.methods.base import Method
from egas.methods.generic import GenericMethod
from egas.methods.star import StarMethod

_REGISTRY = {
    "star": StarMethod,
    "generic": GenericMethod,
}


def get_method(contract: Contract) -> Method:
    try:
        cls = _REGISTRY[contract.method]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"unknown method {contract.method!r}; known: {known}") from exc
    return cls(contract)
