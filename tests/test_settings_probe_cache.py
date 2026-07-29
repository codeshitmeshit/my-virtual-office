from services.settings_probe_cache import SettingsProbeCache


def test_settings_probe_cache_reuses_value_within_ttl():
    now = 100.0
    calls = 0

    def clock():
        return now

    def compute():
        nonlocal calls
        calls += 1
        return {"calls": calls}

    cache = SettingsProbeCache(clock=clock)

    first = cache.get("probe", 10, compute)
    second = cache.get("probe", 10, compute)

    assert first == {"calls": 1}
    assert second == {"calls": 1}
    assert calls == 1


def test_settings_probe_cache_expires_and_invalidates_by_prefix():
    now = 100.0
    calls = 0

    def clock():
        return now

    def compute():
        nonlocal calls
        calls += 1
        return calls

    cache = SettingsProbeCache(clock=clock)

    assert cache.get("hermes:a", 5, compute) == 1
    now = 106.0
    assert cache.get("hermes:a", 5, compute) == 2
    assert cache.get("openclaw:a", 5, compute) == 3
    cache.invalidate("hermes:")

    assert cache.get("hermes:a", 5, compute) == 4
    assert cache.get("openclaw:a", 5, compute) == 3

