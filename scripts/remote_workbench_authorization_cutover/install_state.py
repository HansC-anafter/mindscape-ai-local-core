"""Durable capability install receipt errors."""

from __future__ import annotations

from .io import CutoverError


class ActiveInstallAttemptError(CutoverError):
    """A fixed accepted-install receipt still points at a nonterminal job."""


class AcceptedInstallError(CutoverError):
    """Failure after durable intake, carrying whether a restore job is safe."""

    def __init__(self, message: str, *, install_id: str, state: str, terminal: bool) -> None:
        super().__init__(message)
        self.install_id = install_id
        self.state = state
        self.terminal = terminal
