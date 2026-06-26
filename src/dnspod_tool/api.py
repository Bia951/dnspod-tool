from __future__ import annotations

import json
from typing import Any

from .config import Credential
from .errors import ApiError, ConfigError
from .models import Domain, Record

DEFAULT_RECORD_LINE = "\u9ed8\u8ba4"


class DnspodClient:
    def __init__(self, credential: Credential, timeout: int = 10):
        self.credential = credential
        self.timeout = timeout
        self._sdk_client: Any | None = None

    def list_domains(self) -> list[Domain]:
        items = self._paged("DescribeDomainList", ["domains", "DomainList"])
        return [Domain.from_api(item) for item in items]

    def list_records(self, domain: str) -> list[Record]:
        items = self._paged("DescribeRecordList", ["records", "RecordList"], {"Domain": domain})
        return [Record.from_api(item) for item in items]

    def create_record(
        self,
        domain: str,
        name: str,
        record_type: str,
        value: str,
        line: str = DEFAULT_RECORD_LINE,
        mx: int | None = None,
        ttl: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "Domain": domain,
            "SubDomain": name,
            "RecordType": record_type,
            "RecordLine": line,
            "Value": value,
        }
        if mx is not None:
            params["MX"] = mx
        if ttl is not None:
            params["TTL"] = ttl
        return self._call("CreateRecord", params)

    def modify_record(
        self,
        domain: str,
        record_id: str,
        name: str,
        record_type: str,
        value: str,
        line: str = DEFAULT_RECORD_LINE,
        mx: int | None = None,
        ttl: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "Domain": domain,
            "RecordId": record_id,
            "SubDomain": name,
            "RecordType": record_type,
            "RecordLine": line,
            "Value": value,
        }
        if mx is not None:
            params["MX"] = mx
        if ttl is not None:
            params["TTL"] = ttl
        return self._call("ModifyRecord", params)

    def delete_record(self, domain: str, record_id: str) -> dict[str, Any]:
        return self._call("DeleteRecord", {"Domain": domain, "RecordId": record_id})

    def _paged(
        self,
        action: str,
        item_keys: list[str],
        params: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        base_params = params or {}
        while True:
            response = self._call(action, {**base_params, "Offset": offset, "Limit": limit})
            batch = _first_list(response, item_keys)
            items.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return items

    def _call(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        clean_params = {key: value for key, value in params.items() if value is not None}
        if "RecordId" in clean_params:
            clean_params["RecordId"] = self._normalize_record_id(clean_params["RecordId"])

        if self.credential.mode == "token":
            return self._token_call(action, clean_params)
        if self.credential.mode == "key":
            return self._sdk_call(action, clean_params)
        raise ConfigError(f"Unsupported credential mode: {self.credential.mode}")

    def _token_call(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            import requests
        except Exception as exc:
            raise ConfigError("The requests package is required for token API mode.") from exc

        api_map = {
            "DescribeDomainList": "Domain.List",
            "DescribeRecordList": "Record.List",
            "CreateRecord": "Record.Create",
            "DeleteRecord": "Record.Remove",
            "ModifyRecord": "Record.Modify",
        }
        url = f"https://dnsapi.cn/{api_map.get(action, action)}"
        payload = {"login_token": self.credential.login_token, "format": "json"}
        payload.update(_to_token_params(params))
        try:
            response = requests.post(url, data=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise ApiError(f"DNSPod token API request failed: {exc}") from exc

        status = data.get("status", {}) if isinstance(data, dict) else {}
        if str(status.get("code")) != "1":
            message = status.get("message") or data
            raise ApiError(f"DNSPod API error: {message}")
        return data

    def _sdk_call(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            from tencentcloud.dnspod.v20210323 import models
        except Exception as exc:
            raise ConfigError("The Tencent Cloud SDK package is required for key mode.") from exc

        method = getattr(self.sdk_client, action, None)
        request_class = getattr(models, action + "Request", None)
        if method is None or request_class is None:
            raise ApiError(f"Unsupported SDK action: {action}")

        request = request_class()
        request.from_json_string(json.dumps(params))
        try:
            response = method(request)
            return json.loads(response.to_json_string())
        except Exception as exc:
            raise ApiError(f"Tencent Cloud SDK request failed: {exc}") from exc

    @property
    def sdk_client(self) -> Any:
        if self._sdk_client is not None:
            return self._sdk_client
        if not self.credential.secret_id or not self.credential.secret_key:
            raise ConfigError("Tencent Cloud key credentials are incomplete.")
        try:
            from tencentcloud.common import credential
            from tencentcloud.dnspod.v20210323 import dnspod_client
        except Exception as exc:
            raise ConfigError("The Tencent Cloud SDK package is required for key mode.") from exc
        cred = credential.Credential(self.credential.secret_id, self.credential.secret_key)
        self._sdk_client = dnspod_client.DnspodClient(cred, "")
        return self._sdk_client

    def _normalize_record_id(self, record_id: Any) -> Any:
        if self.credential.mode == "key":
            try:
                return int(record_id)
            except (TypeError, ValueError):
                return record_id
        return str(record_id)


def _to_token_params(params: dict[str, Any]) -> dict[str, Any]:
    key_map = {
        "Domain": "domain",
        "SubDomain": "sub_domain",
        "RecordType": "record_type",
        "RecordLine": "record_line",
        "Value": "value",
        "RecordId": "record_id",
        "MX": "mx",
        "TTL": "ttl",
        "Status": "status",
        "Offset": "offset",
        "Limit": "length",
    }
    return {
        token_key: value
        for source_key, token_key in key_map.items()
        if (value := params.get(source_key)) is not None
    }


def _first_list(data: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []
