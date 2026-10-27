"""Explicit local data options keep large real files outside the repository."""


def pytest_addoption(parser):
    parser.addoption("--real-data-dir", default=None, help="Local delivered data directory")
    parser.addoption("--real-alias", default="scholarlens-papers-real")
    parser.addoption("--real-api", default="http://127.0.0.1:8001")
