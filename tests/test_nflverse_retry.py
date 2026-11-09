"""nflverse downloads retry GitHub's brief server errors (the Oct 6 daily run died on one)."""

from nflreadpy.downloader import get_downloader

from betlab.sources import nflverse  # noqa: F401  (mounts the retry adapter)


def test_shared_session_retries_server_errors():
    retry = get_downloader().session.get_adapter("https://github.com/nflverse/x.parquet").max_retries
    assert retry.total >= 3
    assert {500, 502} <= set(retry.status_forcelist)
