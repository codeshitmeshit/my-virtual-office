"""个人资产领域的最小 composition root。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .personal_asset_agent_access import PersonalAssetAgentAccess
from .personal_asset_agent_api import PersonalAssetAgentAPI
from .personal_asset_agent_auth import PersonalAssetAgentAuthenticator
from .personal_asset_http import PersonalAssetHTTPRoutes
from .personal_asset_feishu_onboarding import PersonalAssetFeishuOnboarding
from .personal_asset_oss_availability import PersonalAssetOssAvailability
from .personal_asset_oss_availability_http import PersonalAssetOssAvailabilityHTTP
from .personal_asset_service import PersonalAssetService
from .personal_asset_store import PersonalAssetStore
from .personal_asset_sync_http import PersonalAssetSyncHTTP
from .personal_asset_sync_service import PersonalAssetSyncService
from .personal_asset_sync_state import PersonalAssetSyncStateStore
from .personal_asset_sync_worker import PersonalAssetSyncWorker
from .oss_runtime import OssConfigurationUnavailable
from .oss_storage import OssStorageService


@dataclass(frozen=True, slots=True)
class PersonalAssetRuntime:
    store: PersonalAssetStore
    service: PersonalAssetService
    access: PersonalAssetAgentAccess
    agent_api: PersonalAssetAgentAPI
    authenticator: PersonalAssetAgentAuthenticator
    routes: PersonalAssetHTTPRoutes
    sync: PersonalAssetSyncService
    sync_worker: PersonalAssetSyncWorker | None


def build_personal_asset_runtime(
    *,
    status_dir: str | Path,
    decision_workflow: Any,
    clock: Callable[[], datetime] | None = None,
    oss_storage: OssStorageService | None = None,
    oss_context_provider: Callable[[], object] | None = None,
    start_sync_worker: bool = False,
    feishu_onboarding: PersonalAssetFeishuOnboarding | None = None,
) -> PersonalAssetRuntime:
    store = PersonalAssetStore(Path(status_dir) / "personal-assets.json", now=clock)

    def unavailable_context():
        raise OssConfigurationUnavailable("Alibaba Cloud OSS is not configured")

    context_provider = oss_context_provider or unavailable_context
    if oss_storage is None:
        oss_storage = OssStorageService(context_provider)
    sync_state = PersonalAssetSyncStateStore(
        Path(status_dir) / "personal-assets-sync.json", now=clock
    )
    sync = PersonalAssetSyncService(store, sync_state, oss_storage, now=clock)
    sync_worker = PersonalAssetSyncWorker(sync.run_once) if start_sync_worker else None
    if sync_worker is not None:
        sync.set_waker(sync_worker.wake)
        sync_worker.start()
        sync_worker.wake()
    service = PersonalAssetService(store, on_mutation=sync.on_profile_mutation)
    access = PersonalAssetAgentAccess(store, decision_workflow=decision_workflow, now=clock)
    agent_api = PersonalAssetAgentAPI(service, access)
    authenticator = PersonalAssetAgentAuthenticator()
    routes = PersonalAssetHTTPRoutes(
        service,
        agent_api,
        authenticator,
        PersonalAssetSyncHTTP(sync),
        PersonalAssetOssAvailabilityHTTP(
            PersonalAssetOssAvailability(context_provider, now=clock)
        ),
        feishu_onboarding,
    )
    return PersonalAssetRuntime(
        store, service, access, agent_api, authenticator, routes, sync, sync_worker
    )
