from .base import Attacker
from .dummy import DummyAttacker

ATTACKERS: dict[str, type[Attacker]] = {
    "dummy": DummyAttacker,
}
