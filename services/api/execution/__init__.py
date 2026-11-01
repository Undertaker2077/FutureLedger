"""Secure execution gate for bank write operations."""

from .service import (
    BankAdapter,
    ExecutionError,
    ExecutionService,
    InMemoryBank,
    UnknownBankResult,
)
from .c_adapter import ExecutionGateAdapter
from .a_adapter import RoleABankAdapter

__all__ = [
    "BankAdapter",
    "ExecutionError",
    "ExecutionService",
    "InMemoryBank",
    "UnknownBankResult",
    "ExecutionGateAdapter",
    "RoleABankAdapter",
]
