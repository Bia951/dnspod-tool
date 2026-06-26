from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .errors import ConfigError, CredentialNotFound

SERVICE_NAME = "dnspod-tool"
CONFIG_FILE_NAME = "config.json"
CREDENTIALS_FILE_NAME = "credentials.json"
DEFAULT_PROFILE = "default"

Storage = Literal["auto", "keyring", "file"]
Mode = Literal["token", "key"]


@dataclass(frozen=True)
class Credential:
    mode: Mode
    token_id: str | None = None
    token: str | None = None
    secret_id: str | None = None
    secret_key: str | None = None
    source: str = "unknown"

    @property
    def login_token(self) -> str:
        if self.mode != "token" or not self.token_id or not self.token:
            raise ConfigError("DNSPod token credentials are incomplete.")
        return f"{self.token_id},{self.token}"

    def to_file_payload(self) -> dict[str, str]:
        if self.mode == "token":
            if not self.token_id or not self.token:
                raise ConfigError("DNSPod token credentials are incomplete.")
            return {
                "version": "1",
                "mode": "token",
                "token_id": self.token_id,
                "token": self.token,
            }
        if not self.secret_id or not self.secret_key:
            raise ConfigError("Tencent Cloud key credentials are incomplete.")
        return {
            "version": "1",
            "mode": "key",
            "secret_id": self.secret_id,
            "secret_key": self.secret_key,
        }


class CredentialStore:
    def __init__(self, config_dir: Path | None = None, profile: str = DEFAULT_PROFILE):
        self.base_config_dir = config_dir or default_config_dir()
        self.profile = validate_profile_name(profile)
        self.config_dir = profile_config_dir(self.base_config_dir, self.profile)
        self.config_path = self.config_dir / CONFIG_FILE_NAME
        self.credentials_path = self.config_dir / CREDENTIALS_FILE_NAME

    def load(self) -> Credential:
        env_credential = credential_from_env()
        if env_credential:
            return env_credential

        metadata = self._read_json(self.config_path)
        preferred_storage = metadata.get("storage")
        preferred_mode = metadata.get("mode")

        if preferred_storage == "keyring":
            credential = self._load_keyring(preferred_mode)
            if credential:
                return credential
        if preferred_storage == "file":
            credential = self._load_file()
            if credential:
                return credential

        credential = self._load_keyring(preferred_mode)
        if credential:
            return credential

        credential = self._load_file()
        if credential:
            return credential

        raise CredentialNotFound(
            "No credentials found. Use environment variables or run "
            "`dnspod auth token` / `dnspod auth key` first."
        )

    def save(self, credential: Credential, storage: Storage = "auto") -> str:
        if storage in ("auto", "keyring"):
            try:
                self._save_keyring(credential)
                self._write_metadata("keyring", credential.mode)
                return "keyring"
            except ConfigError:
                if storage == "keyring":
                    raise

        self._save_file(credential)
        self._write_metadata("file", credential.mode)
        return "file"

    def clear(self, storage: Literal["all", "keyring", "file"] = "all") -> None:
        if storage in ("all", "keyring"):
            self._clear_keyring()
        if storage in ("all", "file"):
            self._clear_file_credentials()

    def status(self) -> dict[str, Any]:
        try:
            credential = self.load()
        except CredentialNotFound:
            return {
                "configured": False,
                "mode": None,
                "source": None,
                "profile": self.profile,
                "default_domain": self.get_default_domain(),
                "config_dir": str(self.config_dir),
            }
        return {
            "configured": True,
            "mode": credential.mode,
            "source": credential.source,
            "profile": self.profile,
            "default_domain": self.get_default_domain(),
            "config_dir": str(self.config_dir),
        }

    def get_default_domain(self) -> str | None:
        value = self._read_json(self.config_path).get("default_domain")
        return str(value) if value else None

    def set_default_domain(self, domain: str | None) -> None:
        metadata = self._read_json(self.config_path)
        if domain:
            metadata["default_domain"] = domain
        else:
            metadata.pop("default_domain", None)
        metadata["version"] = "1"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(self.config_path, metadata)
        _chmod_owner_only(self.config_path)

    def _load_file(self) -> Credential | None:
        payload = self._read_json(self.credentials_path)
        mode = payload.get("mode")
        if mode == "token":
            token_id = payload.get("token_id")
            token = payload.get("token")
            if token_id and token:
                return Credential(
                    mode="token",
                    token_id=token_id,
                    token=token,
                    source=f"file:{self.credentials_path}",
                )
        if mode == "key":
            secret_id = payload.get("secret_id")
            secret_key = payload.get("secret_key")
            if secret_id and secret_key:
                return Credential(
                    mode="key",
                    secret_id=secret_id,
                    secret_key=secret_key,
                    source=f"file:{self.credentials_path}",
                )
        return None

    def _save_file(self, credential: Credential) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        payload = credential.to_file_payload()
        self._write_json(self.credentials_path, payload)
        _chmod_owner_only(self.credentials_path)

    def _load_keyring(self, preferred_mode: str | None = None) -> Credential | None:
        keyring = _load_keyring_module()
        if keyring is None:
            return None

        modes = [preferred_mode] if preferred_mode in ("token", "key") else ["token", "key"]
        for mode in modes:
            try:
                if mode == "token":
                    token_id = keyring.get_password(SERVICE_NAME, self._keyring_username("token_id"))
                    token = keyring.get_password(SERVICE_NAME, self._keyring_username("token"))
                    if token_id and token:
                        return Credential(
                            mode="token",
                            token_id=token_id,
                            token=token,
                            source="keyring",
                        )
                if mode == "key":
                    secret_id = keyring.get_password(SERVICE_NAME, self._keyring_username("secret_id"))
                    secret_key = keyring.get_password(SERVICE_NAME, self._keyring_username("secret_key"))
                    if secret_id and secret_key:
                        return Credential(
                            mode="key",
                            secret_id=secret_id,
                            secret_key=secret_key,
                            source="keyring",
                        )
            except Exception:
                return None
        return None

    def _save_keyring(self, credential: Credential) -> None:
        keyring = _load_keyring_module()
        if keyring is None:
            raise ConfigError("The keyring package is not available.")
        try:
            if credential.mode == "token":
                keyring.set_password(SERVICE_NAME, self._keyring_username("token_id"), credential.token_id or "")
                keyring.set_password(SERVICE_NAME, self._keyring_username("token"), credential.token or "")
                self._delete_keyring_password(keyring, "secret_id")
                self._delete_keyring_password(keyring, "secret_key")
            else:
                keyring.set_password(SERVICE_NAME, self._keyring_username("secret_id"), credential.secret_id or "")
                keyring.set_password(SERVICE_NAME, self._keyring_username("secret_key"), credential.secret_key or "")
                self._delete_keyring_password(keyring, "token_id")
                self._delete_keyring_password(keyring, "token")
        except Exception as exc:
            raise ConfigError(
                "System keyring is unavailable. On headless Linux, use "
                "environment variables or `--storage file`."
            ) from exc

    def _clear_keyring(self) -> None:
        keyring = _load_keyring_module()
        if keyring is None:
            return
        for username in ("token_id", "token", "secret_id", "secret_key"):
            self._delete_keyring_password(keyring, username)

    def _delete_keyring_password(self, keyring: Any, username: str) -> None:
        try:
            keyring.delete_password(SERVICE_NAME, self._keyring_username(username))
        except Exception:
            pass

    def _write_metadata(self, storage: str, mode: str) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        metadata = self._read_json(self.config_path)
        metadata.update({"version": "1", "storage": storage, "mode": mode})
        self._write_json(self.config_path, metadata)
        _chmod_owner_only(self.config_path)

    def _keyring_username(self, username: str) -> str:
        if self.profile == DEFAULT_PROFILE:
            return username
        return f"{self.profile}:{username}"

    def _clear_file_credentials(self) -> None:
        self._unlink_if_exists(self.credentials_path)
        metadata = self._read_json(self.config_path)
        for key in ("storage", "mode"):
            metadata.pop(key, None)
        if metadata:
            metadata["version"] = "1"
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self._write_json(self.config_path, metadata)
            _chmod_owner_only(self.config_path)
        else:
            self._unlink_if_exists(self.config_path)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON configuration file: {path}") from exc
        if not isinstance(payload, dict):
            raise ConfigError(f"Invalid configuration shape: {path}")
        return payload

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        tmp_path.replace(path)

    @staticmethod
    def _unlink_if_exists(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def default_config_dir() -> Path:
    override = os.environ.get("DNSPOD_TOOL_CONFIG_DIR")
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / SERVICE_NAME

    if sys_platform() == "darwin":
        return Path.home() / "Library" / "Application Support" / SERVICE_NAME

    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base).expanduser() if base else Path.home() / ".config") / SERVICE_NAME


def default_profile() -> str:
    return validate_profile_name(os.environ.get("DNSPOD_TOOL_PROFILE", DEFAULT_PROFILE))


def profile_config_dir(base_config_dir: Path, profile: str) -> Path:
    if profile == DEFAULT_PROFILE:
        return base_config_dir
    return base_config_dir / "profiles" / profile


def validate_profile_name(profile: str | None) -> str:
    value = (profile or DEFAULT_PROFILE).strip()
    if not value:
        return DEFAULT_PROFILE
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise ConfigError("Profile names may not contain path separators.")
    return value


def sys_platform() -> str:
    import sys

    return sys.platform


def credential_from_env() -> Credential | None:
    token_id = os.environ.get("DNSPOD_TOKEN_ID") or os.environ.get("DNSPOD_ID")
    token = os.environ.get("DNSPOD_TOKEN")
    if token and not token_id and "," in token:
        token_id, token = token.split(",", 1)
    if token_id and token:
        return Credential(mode="token", token_id=token_id, token=token, source="environment")

    secret_id = os.environ.get("TENCENTCLOUD_SECRET_ID")
    secret_key = os.environ.get("TENCENTCLOUD_SECRET_KEY")
    if secret_id and secret_key:
        return Credential(mode="key", secret_id=secret_id, secret_key=secret_key, source="environment")

    return None


def _load_keyring_module() -> Any | None:
    try:
        import keyring
    except Exception:
        return None
    return keyring


def _chmod_owner_only(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        path.chmod(0o600)
    except OSError:
        pass
