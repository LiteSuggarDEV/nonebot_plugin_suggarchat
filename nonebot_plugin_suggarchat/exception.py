class SuggarChatException(Exception):
    """Base exception for SuggarChat plugin."""


class BlockException(SuggarChatException):
    pass


class CancelException(SuggarChatException):
    pass


class PassException(SuggarChatException):
    pass
