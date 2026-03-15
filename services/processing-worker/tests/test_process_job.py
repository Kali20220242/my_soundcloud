import worker


class FakeRedis:
    def __init__(self) -> None:
        self.items: list[tuple[str, str]] = []

    def lpush(self, queue: str, payload: str) -> None:
        self.items.append((queue, payload))


class FakeS3:
    def __init__(self) -> None:
        self.copies = []

    def copy_object(self, **kwargs) -> None:  # noqa: ANN003
        self.copies.append(kwargs)


def test_process_job_publishes_when_object_exists(monkeypatch) -> None:
    fake_s3 = FakeS3()
    updates: list[tuple[str, dict]] = []

    monkeypatch.setattr(worker, "s3_client", fake_s3)
    monkeypatch.setattr(worker, "object_exists", lambda bucket, key: True)
    monkeypatch.setattr(worker, "update_track", lambda track_id, endpoint, payload: updates.append((endpoint, payload)))

    redis_client = FakeRedis()
    worker.process_job(
        redis_client,
        {
            "track_id": "track-1",
            "object_key": "raw/alice/file.mp3",
            "bucket": "tracks",
            "retries": 0,
        },
    )

    assert fake_s3.copies
    assert updates
    endpoint, payload = updates[0]
    assert endpoint == "publish"
    assert payload["processed_object_key"] == "processed/alice/file.mp3"


def test_process_job_requeues_when_object_missing(monkeypatch) -> None:
    monkeypatch.setattr(worker, "object_exists", lambda bucket, key: False)
    monkeypatch.setattr(worker, "mark_failed", lambda track_id, error_message: None)

    redis_client = FakeRedis()
    worker.process_job(
        redis_client,
        {
            "track_id": "track-1",
            "object_key": "raw/alice/file.mp3",
            "bucket": "tracks",
            "retries": 0,
        },
    )

    assert len(redis_client.items) == 1
