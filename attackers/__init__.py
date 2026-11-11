from .base import Attacker
from .dummy import DummyAttacker

ATTACKERS: dict[str, type[Attacker]] = {
    # TODO(attacker): register the real attacker here, e.g. "llm": LLMAttacker,
    "dummy": DummyAttacker,
}
