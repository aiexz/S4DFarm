from enum import Enum
from dataclasses import dataclass


class FlagStatus(Enum):
    QUEUED = 0
    SKIPPED = 1
    ACCEPTED = 2
    REJECTED = 3


@dataclass
class Flag:
    flag: str
    sploit: str
    team: str
    time: int
    status: FlagStatus
    checksystem_response: str


@dataclass
class SubmitResult:
    flag: str
    status: FlagStatus
    checksystem_response: str


@dataclass
class Execution:
    client_id: str
    sploit_id: str
    sploit_hash: str
    service: str
    team: str
    round: int
    start_time: float
    end_time: float
    duration: float
    exit_code: int
    timeout: bool
    flags_found: int
    output_preview: str
