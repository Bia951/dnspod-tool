from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def pick(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return default


@dataclass(frozen=True)
class Domain:
    name: str
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Domain":
        return cls(name=str(pick(data, "name", "Name", default="")), raw=data)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name}


@dataclass(frozen=True)
class Record:
    record_id: str
    name: str
    record_type: str
    value: str
    line: str | None = None
    ttl: int | None = None
    mx: int | None = None
    status: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Record":
        return cls(
            record_id=str(pick(data, "id", "RecordId", "record_id", default="")),
            name=str(pick(data, "name", "Name", "SubDomain", default="")),
            record_type=str(pick(data, "type", "Type", "RecordType", default="")),
            value=str(pick(data, "value", "Value", default="")),
            line=pick(data, "line", "Line", "RecordLine"),
            ttl=_to_int_or_none(pick(data, "ttl", "TTL")),
            mx=_to_int_or_none(pick(data, "mx", "MX")),
            status=pick(data, "status", "Status"),
            raw=data,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.record_id,
            "name": self.name,
            "type": self.record_type,
            "value": self.value,
            "line": self.line,
            "ttl": self.ttl,
            "mx": self.mx,
            "status": self.status,
        }


def _to_int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
