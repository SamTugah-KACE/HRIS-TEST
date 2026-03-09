from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple

from app.core.settings import get_settings
from app.services import automation_store


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    return cleaned.strip("._") or "file"


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", (value or "").strip())
    return cleaned or "unknown"


def _ext(name: str) -> str:
    suffix = Path(name).suffix.lower().strip()
    if not suffix or len(suffix) > 10:
        return ".bin"
    return suffix


@dataclass
class ProviderHealth:
    ok: bool
    checked_at: datetime
    detail: str


class BaseProvider:
    name = "base"

    def health_check(self, config: Dict[str, str]) -> Tuple[bool, str]:
        raise NotImplementedError()

    def write_bytes(self, *, relative_path: str, content: bytes, config: Dict[str, str]) -> str:
        raise NotImplementedError()

    def read_bytes(self, *, storage_uri: str, config: Dict[str, str]) -> bytes:
        raise NotImplementedError()


class LocalProvider(BaseProvider):
    name = "local"

    def health_check(self, config: Dict[str, str]) -> Tuple[bool, str]:
        settings = get_settings()
        base = Path(config.get("base_path") or settings.media_local_base_path)
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / ".healthcheck"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True, f"local_path={base}"
        except Exception as exc:
            return False, f"local_health_failed: {exc}"

    def write_bytes(self, *, relative_path: str, content: bytes, config: Dict[str, str]) -> str:
        settings = get_settings()
        base = Path(config.get("base_path") or settings.media_local_base_path)
        target = (base / relative_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return f"local://{relative_path}"

    def read_bytes(self, *, storage_uri: str, config: Dict[str, str]) -> bytes:
        settings = get_settings()
        base = Path(config.get("base_path") or settings.media_local_base_path)
        rel = storage_uri.replace("local://", "", 1).lstrip("/").strip()
        if not rel:
            raise RuntimeError("invalid_local_storage_uri")
        target = (base / rel).resolve()
        return target.read_bytes()


class S3Provider(BaseProvider):
    name = "s3"

    def _client(self, config: Dict[str, str]):
        try:
            import boto3
        except Exception as exc:
            raise RuntimeError("boto3_not_installed") from exc
        return boto3.client(
            "s3",
            region_name=config.get("region"),
            aws_access_key_id=config.get("access_key_id"),
            aws_secret_access_key=config.get("secret_access_key"),
            endpoint_url=config.get("endpoint_url"),
        )

    def health_check(self, config: Dict[str, str]) -> Tuple[bool, str]:
        bucket = str(config.get("bucket") or "").strip()
        if not bucket:
            return False, "s3_bucket_missing"
        try:
            client = self._client(config)
            client.head_bucket(Bucket=bucket)
            return True, f"s3_bucket={bucket}"
        except Exception as exc:
            return False, f"s3_health_failed: {exc}"

    def write_bytes(self, *, relative_path: str, content: bytes, config: Dict[str, str]) -> str:
        bucket = str(config.get("bucket") or "").strip()
        if not bucket:
            raise RuntimeError("s3_bucket_missing")
        prefix = str(config.get("prefix") or "").strip("/")
        object_key = f"{prefix}/{relative_path}".lstrip("/") if prefix else relative_path
        client = self._client(config)
        client.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=content,
        )
        endpoint = str(config.get("endpoint_url") or "").rstrip("/")
        if endpoint:
            return f"{endpoint}/{bucket}/{object_key}"
        return f"s3://{bucket}/{object_key}"

    def read_bytes(self, *, storage_uri: str, config: Dict[str, str]) -> bytes:
        raise RuntimeError("s3_read_not_implemented")


class TenantStorageService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.providers = {
            "local": LocalProvider(),
            "s3": S3Provider(),
        }
        self._health_cache: Dict[str, ProviderHealth] = {}

    def _provider_order(self, tenant_id: str) -> List[Tuple[str, Dict[str, str]]]:
        tenant_cfg = automation_store.get_tenant_setting(tenant_id=tenant_id, setting_key="storage_stack") or {}
        providers = tenant_cfg.get("providers") if isinstance(tenant_cfg, dict) else None
        result: List[Tuple[str, Dict[str, str]]] = []
        if isinstance(providers, list):
            for item in providers:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip().lower()
                cfg = item.get("config") if isinstance(item.get("config"), dict) else {}
                if name:
                    result.append((name, {str(k): str(v) for k, v in cfg.items() if v is not None}))
        if result:
            return result

        ordered = [p.strip().lower() for p in str(self.settings.storage_provider_stack or "").split(",") if p.strip()]
        for name in ordered:
            if name == "s3":
                result.append(
                    (
                        "s3",
                        {
                            "bucket": str(self.settings.s3_bucket or ""),
                            "region": str(self.settings.s3_region or ""),
                            "access_key_id": str(self.settings.s3_access_key_id or ""),
                            "secret_access_key": str(self.settings.s3_secret_access_key or ""),
                            "endpoint_url": str(self.settings.s3_endpoint_url or ""),
                            "prefix": str(self.settings.s3_prefix or ""),
                        },
                    )
                )
            elif name == "local":
                result.append(("local", {"base_path": str(self.settings.media_local_base_path)}))
        if not result:
            result = [("local", {"base_path": str(self.settings.media_local_base_path)})]
        return result

    def _healthy(self, provider_name: str, config: Dict[str, str]) -> Tuple[bool, str]:
        now = datetime.now(timezone.utc)
        key = f"{provider_name}|{hashlib.sha256(str(sorted(config.items())).encode('utf-8')).hexdigest()}"
        cached = self._health_cache.get(key)
        ttl = max(1, int(self.settings.storage_healthcheck_ttl_seconds))
        if cached and (now - cached.checked_at).total_seconds() < ttl:
            return cached.ok, cached.detail

        provider = self.providers.get(provider_name)
        if provider is None:
            detail = f"provider_not_supported:{provider_name}"
            self._health_cache[key] = ProviderHealth(ok=False, checked_at=now, detail=detail)
            return False, detail
        ok, detail = provider.health_check(config)
        self._health_cache[key] = ProviderHealth(ok=ok, checked_at=now, detail=detail)
        return ok, detail

    def store_document(
        self,
        *,
        tenant_id: str,
        owner_type: str,
        owner_id: str,
        document_key: str,
        file_name: str,
        content: bytes,
        content_type: Optional[str],
    ) -> Dict[str, str]:
        tenant_id_safe = _safe_id(tenant_id)
        owner_id_safe = _safe_id(owner_id)
        owner_type_safe = _safe_id(owner_type)
        doc_key_safe = _safe_id(document_key)
        stem = _safe_name(Path(file_name or "upload.bin").stem)
        extension = _ext(file_name or "upload.bin")
        content_hash = hashlib.sha256(content).hexdigest()
        unique_name = f"{stem}_{doc_key_safe}_{content_hash[:12]}{extension}"
        relative_path = f"{tenant_id_safe}/{owner_type_safe}/{owner_id_safe}/{unique_name}"

        chain = self._provider_order(tenant_id)
        errors: List[str] = []
        for provider_name, cfg in chain:
            ok, detail = self._healthy(provider_name, cfg)
            if not ok:
                errors.append(f"{provider_name}:unhealthy:{detail}")
                continue
            provider = self.providers.get(provider_name)
            if not provider:
                errors.append(f"{provider_name}:missing")
                continue
            try:
                uri = provider.write_bytes(relative_path=relative_path, content=content, config=cfg)
                row = automation_store.upsert_media_document(
                    tenant_id=tenant_id,
                    owner_type=owner_type,
                    owner_id=owner_id,
                    document_key=document_key,
                    file_name=file_name,
                    content_type=content_type,
                    provider_name=provider_name,
                    storage_uri=uri,
                    file_size_bytes=len(content),
                    content_hash_sha256=content_hash,
                )
                return {
                    "provider_name": provider_name,
                    "storage_uri": uri,
                    "document_key": document_key,
                    "version": str(row.get("version")),
                }
            except Exception as exc:
                errors.append(f"{provider_name}:write_failed:{exc}")
                continue
        raise RuntimeError(f"No storage provider available for tenant '{tenant_id}': {' | '.join(errors)}")

    def load_document(
        self,
        *,
        tenant_id: str,
        owner_type: str,
        owner_id: str,
        document_key: str,
    ) -> Optional[Dict[str, object]]:
        row = automation_store.get_media_document(
            tenant_id=tenant_id,
            owner_type=owner_type,
            owner_id=owner_id,
            document_key=document_key,
        )
        if not row:
            return None
        provider_name = str(row.get("provider_name") or "").strip().lower()
        provider = self.providers.get(provider_name)
        if not provider:
            raise RuntimeError(f"unknown_provider:{provider_name}")

        config: Dict[str, str] = {}
        if provider_name == "local":
            config = {"base_path": str(self.settings.media_local_base_path)}
        elif provider_name == "s3":
            config = {
                "bucket": str(self.settings.s3_bucket or ""),
                "region": str(self.settings.s3_region or ""),
                "access_key_id": str(self.settings.s3_access_key_id or ""),
                "secret_access_key": str(self.settings.s3_secret_access_key or ""),
                "endpoint_url": str(self.settings.s3_endpoint_url or ""),
                "prefix": str(self.settings.s3_prefix or ""),
            }
        payload = provider.read_bytes(storage_uri=str(row.get("storage_uri") or ""), config=config)
        return {
            "file_name": str(row.get("file_name") or "download.bin"),
            "content_type": str(row.get("content_type") or "application/octet-stream"),
            "content": payload,
            "provider_name": provider_name,
            "storage_uri": str(row.get("storage_uri") or ""),
            "version": int(row.get("version") or 1),
        }
