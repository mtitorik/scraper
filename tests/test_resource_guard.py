import pytest
from scraper_app.core.resource_guard import ResourceGuard


def test_resource_guard_limits_and_pause_calculation():
    guard = ResourceGuard(max_cores=4, max_cpu_percent=40, max_ram_gb=2.0)

    assert guard.max_cores == 4
    assert guard.max_cpu_percent == 40
    assert guard.max_ram_gb == 2.0

    # Test update
    guard.update_limits(max_cores=2, max_cpu_percent=50, max_ram_gb=3.0)
    assert guard.max_cores == 2
    assert guard.max_cpu_percent == 50
    assert guard.max_ram_gb == 3.0

    # Live metrics dictionary structure
    metrics = guard.get_live_metrics()
    assert "cpu_percent" in metrics
    assert "memory_mb" in metrics
    assert "memory_gb" in metrics
    assert "memory_percent_of_cap" in metrics
    assert "should_recycle" in metrics
