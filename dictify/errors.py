class Cancelled(Exception):
    """Raised inside a background job when the user cancels it."""


class NoAudioError(Exception):
    """The file has no decodable audio stream."""
