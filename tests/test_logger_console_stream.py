from backend.utils.logger import _is_console_stream_available


class _Stream:
    def __init__(self, name="", closed=False, writable=True):
        self.name = name
        self.closed = closed
        self._writable = writable

    def writable(self):
        return self._writable


def test_console_stream_available_rejects_packaged_null_streams():
    assert not _is_console_stream_available(None)
    assert not _is_console_stream_available(_Stream("nul"))
    assert not _is_console_stream_available(_Stream("/dev/null"))
    assert not _is_console_stream_available(_Stream(closed=True))
    assert not _is_console_stream_available(_Stream(writable=False))
    assert _is_console_stream_available(_Stream("<stdout>"))
