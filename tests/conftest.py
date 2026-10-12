import os
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--live", action="store_true", help="Run tests against the real CAU account and school APIs"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="Real CAU integration is opt-in: pytest --live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
