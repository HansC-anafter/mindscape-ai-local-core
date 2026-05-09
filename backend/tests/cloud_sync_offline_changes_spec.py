from backend.app.services.cloud_sync.offline_changes import OfflineChangeTracker


class FakeInstanceStore:
    def __init__(self):
        self.change_reads = []

    def list_instances(self, instance_type=None):
        instances = [
            {
                "instance_type": "workspace",
                "instance_id": "ws-1",
                "has_local_changes": True,
            },
            {
                "instance_type": "asset",
                "instance_id": "asset-1",
                "has_local_changes": False,
            },
            {
                "instance_type": "conversation",
                "instance_id": "thread-1",
                "has_local_changes": True,
            },
        ]
        if instance_type:
            return [item for item in instances if item["instance_type"] == instance_type]
        return instances

    def get_local_changes(self, instance_type, instance_id):
        self.change_reads.append((instance_type, instance_id))
        return {
            ("workspace", "ws-1"): [{"change_id": "a"}, {"change_id": "b"}],
            ("conversation", "thread-1"): [{"change_id": "c"}],
        }.get((instance_type, instance_id), [])


def test_pending_change_count_skips_instances_without_local_changes():
    store = FakeInstanceStore()
    tracker = OfflineChangeTracker(instance_store=store)

    assert tracker.get_pending_change_count() == 3
    assert store.change_reads == [
        ("workspace", "ws-1"),
        ("conversation", "thread-1"),
    ]


def test_pending_change_count_supports_specific_instance():
    store = FakeInstanceStore()
    tracker = OfflineChangeTracker(instance_store=store)

    assert tracker.get_pending_change_count("workspace", "ws-1") == 2
    assert store.change_reads == [("workspace", "ws-1")]
