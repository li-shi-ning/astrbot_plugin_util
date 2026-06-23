from __future__ import annotations

import random
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def load_love_messages(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        return ()
    return tuple(
        line
        for raw_line in path.read_text(encoding="utf-8").splitlines()
        if (line := raw_line.strip())
    )

def choose_love_message(
    messages: Sequence[str],
    rng: random.Random | Any = random,
) -> str | None:
    return rng.choice(messages) if messages else None


def format_love_message(message: str) -> str:
    return message.strip()
