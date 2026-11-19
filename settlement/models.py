from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Participant:
    id: str
    name: str
    registration_order: int

    def __post_init__(self):
        name = self.name.strip()
        if not name:
            raise ValueError("참여자 이름을 입력하세요.")
        object.__setattr__(self, "name", name)


@dataclass(frozen=True)
class Share:
    participant_id: str
    amount: int | None = None


@dataclass(frozen=True)
class Expense:
    id: str
    title: str
    payer_id: str
    amount: int
    split_type: Literal["equal", "exact"]
    shares: tuple[Share, ...]


@dataclass(frozen=True)
class Transfer:
    id: str
    sender_id: str
    receiver_id: str
    amount: int


@dataclass
class Balance:
    paid: int = 0
    owed: int = 0
    sent: int = 0
    received: int = 0

    @property
    def net(self) -> int:
        return self.paid - self.owed + self.sent - self.received
