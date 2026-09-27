"""Compatibility adapters for optional upstream systems."""


class CapabilityUnavailableError(RuntimeError):
    """An optional upstream capability has not been configured and verified."""
