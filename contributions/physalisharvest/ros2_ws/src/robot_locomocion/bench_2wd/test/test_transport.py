from bench_2wd.smoke_test import run_probe, standalone_receiver


def test_transport(monkeypatch):
    monkeypatch.setenv('ROS_DOMAIN_ID', '84')
    monkeypatch.setenv('ROS_AUTOMATIC_DISCOVERY_RANGE', 'LOCALHOST')
    with standalone_receiver():
        run_probe()
