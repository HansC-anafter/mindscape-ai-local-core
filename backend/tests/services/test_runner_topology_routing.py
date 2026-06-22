from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.services.runner_topology import (
    RunnerProfile,
    resolve_target_runner_profile,
    resolve_task_routing_target,
    runner_profile_can_claim_task,
)

BATCH_PLAYBOOK = "browser_batch_collect"
DETAIL_PLAYBOOK = "browser_detail_collect"
FOLLOWING_PLAYBOOK = "browser_following_collect"
VISION_PLAYBOOK = "vision_reference_analyze"
REFRESH_PLAYBOOK = "browser_reference_refresh"
CAPABILITY_CODE = "content_refs"
MANAGED_BATCH_PLAYBOOKS = {BATCH_PLAYBOOK, DETAIL_PLAYBOOK}


def _build_task(
    *,
    pack_id: str = DETAIL_PLAYBOOK,
    queue_shard: str = "browser_local",
    resource_class: str = "browser",
    capability_code: str | None = CAPABILITY_CODE,
    runner_profile_hint: str | None = None,
) -> Task:
    ctx = {
        "queue_partition": queue_shard,
        "resource_class": resource_class,
        "playbook_code": pack_id,
    }
    if pack_id in MANAGED_BATCH_PLAYBOOKS:
        ctx["task_family"] = "browser_batch"
        ctx["managed_runner_role"] = "managed_browser_batch"
        ctx["fairness_lane_key"] = pack_id
    if capability_code:
        ctx["capability_code"] = capability_code
    if runner_profile_hint:
        ctx["runner_profile_hint"] = runner_profile_hint
    return Task(
        id="task-1",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-1",
        pack_id=pack_id,
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard=queue_shard,
        execution_context=ctx,
        created_at=_utc_now(),
    )


def test_resolve_task_routing_target_normalizes_legacy_queue_alias():
    task = _build_task(pack_id=FOLLOWING_PLAYBOOK, queue_shard="ig_browser")

    target = resolve_task_routing_target(task)

    assert target.queue_partition == "browser_local"
    assert target.resource_class == "browser"
    assert target.capability_code == CAPABILITY_CODE


def test_resolve_task_routing_target_infers_browser_resource_class_from_queue():
    task = _build_task(
        pack_id=FOLLOWING_PLAYBOOK,
        queue_shard="ig_browser",
        resource_class="",
    )

    target = resolve_task_routing_target(task)

    assert target.queue_partition == "browser_local"
    assert target.resource_class == "browser"


def test_batch_browser_playbooks_route_to_default_local_browser():
    task = _build_task(pack_id=DETAIL_PLAYBOOK, queue_shard="ig_browser")

    target = resolve_task_routing_target(task)

    assert target.queue_partition == "default_local_browser"
    assert target.resource_class == "browser"
    assert resolve_target_runner_profile(task) == "default_local_browser"


def test_non_batch_default_local_hint_does_not_route_to_default_local_browser():
    task = _build_task(
        pack_id=VISION_PLAYBOOK,
        queue_shard="default_local",
        resource_class="compute",
    )

    target = resolve_task_routing_target(task)

    assert target.queue_partition == "default_local"
    assert target.resource_class == "compute"
    assert resolve_target_runner_profile(task) == "default_local"


def test_default_local_browser_profile_rejects_non_batch_default_local_work():
    profile = RunnerProfile(
        profile_code="default_local_browser",
        display_name="Default Local Browser",
        dispatch_mode="docker_local",
        accepted_resource_classes=("browser",),
        accepted_queue_partitions=("default_local_browser",),
    )
    task = _build_task(
        pack_id=FOLLOWING_PLAYBOOK,
        queue_shard="default_local",
        resource_class="browser",
    )

    assert not runner_profile_can_claim_task(profile, task)


def test_resolve_target_runner_profile_prefers_runner_profile_hint():
    task = _build_task(runner_profile_hint="gpu_training")

    assert resolve_target_runner_profile(task) == "gpu_training"


def test_resolve_target_runner_profile_keeps_following_on_general_browser_runner():
    task = _build_task(pack_id=FOLLOWING_PLAYBOOK)

    target = resolve_task_routing_target(task)

    assert target.queue_partition == "browser_local"
    assert target.runner_profile_hint is None
    assert resolve_target_runner_profile(task) == "browser_local"


def test_general_browser_task_stays_on_browser_runner():
    task = _build_task(pack_id=REFRESH_PLAYBOOK)

    assert resolve_target_runner_profile(task) == "browser_local"


def test_runner_profile_can_claim_task_checks_partition_and_resource_class():
    browser_profile = RunnerProfile(
        profile_code="browser_local",
        display_name="Browser",
        dispatch_mode="docker_local",
        accepted_resource_classes=("browser",),
        accepted_queue_partitions=("browser_local",),
    )

    assert runner_profile_can_claim_task(
        browser_profile,
        _build_task(
            pack_id=FOLLOWING_PLAYBOOK,
            queue_shard="ig_browser",
            resource_class="browser",
        ),
    )
    assert not runner_profile_can_claim_task(
        browser_profile,
        _build_task(queue_shard="vision_local", resource_class="compute"),
    )


def test_runner_profile_can_claim_task_accepts_browser_queue_without_resource_class():
    browser_profile = RunnerProfile(
        profile_code="browser_local",
        display_name="Browser",
        dispatch_mode="docker_local",
        accepted_resource_classes=("browser",),
        accepted_queue_partitions=("browser_local",),
    )

    assert runner_profile_can_claim_task(
        browser_profile,
        _build_task(
            pack_id=FOLLOWING_PLAYBOOK,
            queue_shard="ig_browser",
            resource_class="",
        ),
    )


def test_runner_profile_can_claim_task_rejects_mismatched_profile_hint():
    browser_profile = RunnerProfile(
        profile_code="browser_local",
        display_name="Browser",
        dispatch_mode="docker_local",
        accepted_resource_classes=("browser",),
        accepted_queue_partitions=("browser_local",),
    )

    assert not runner_profile_can_claim_task(
        browser_profile,
        _build_task(runner_profile_hint="vision_local"),
    )


def test_general_browser_profile_can_claim_following_without_explicit_profile_hint():
    browser_profile = RunnerProfile(
        profile_code="browser_local",
        display_name="Browser",
        dispatch_mode="docker_local",
        accepted_resource_classes=("browser",),
        accepted_queue_partitions=("browser_local",),
    )
    task = _build_task(pack_id=FOLLOWING_PLAYBOOK)

    assert runner_profile_can_claim_task(browser_profile, task)


def test_default_local_browser_profile_can_claim_batch_detail():
    profile = RunnerProfile(
        profile_code="default_local_browser",
        display_name="Default Local Browser",
        dispatch_mode="docker_local",
        accepted_resource_classes=("browser",),
        accepted_queue_partitions=("default_local_browser",),
    )
    task = _build_task(pack_id=DETAIL_PLAYBOOK, queue_shard="browser_local")

    assert runner_profile_can_claim_task(profile, task)


def test_runner_profile_can_claim_task_respects_capability_filter():
    training_profile = RunnerProfile(
        profile_code="gpu_training",
        display_name="GPU Training",
        dispatch_mode="external_runtime",
        accepted_resource_classes=("compute",),
        accepted_queue_partitions=("default_local",),
        accepted_capability_codes=("character_training",),
    )

    assert runner_profile_can_claim_task(
        training_profile,
        _build_task(
            pack_id="character_training_submit",
            queue_shard="default_local",
            resource_class="compute",
            capability_code="character_training",
            runner_profile_hint="gpu_training",
        ),
    )
    assert not runner_profile_can_claim_task(
        training_profile,
        _build_task(
            pack_id=FOLLOWING_PLAYBOOK,
            queue_shard="default_local",
            resource_class="compute",
            capability_code=CAPABILITY_CODE,
            runner_profile_hint="gpu_training",
        ),
    )
