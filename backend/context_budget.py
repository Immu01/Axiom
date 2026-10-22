"""Keeps the conversation sent to the model inside a size budget.

The newest messages are prioritized; the oldest ones are dropped first.
Size is measured in characters (roughly 4 characters = 1 token), because it is
fast, needs no tokenizer library, and works the same for every provider.
"""
import os
import copy


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


# ~48,000 characters is roughly 12,000 tokens, which fits the free-tier limits of most providers.
CONTEXT_CHAR_BUDGET = _int_env("CONTEXT_CHAR_BUDGET", 48_000)
# An attached image is counted as this many characters (its base64 data is not sent as text).
IMAGE_COST = 2_000


def message_cost(m) -> int:
    return len(m.content) + IMAGE_COST * len(getattr(m, "images", None) or [])


def _fit_message(message, budget: int):
    images = list(getattr(message, "images", None) or [])
    image_count = min(len(images), budget // IMAGE_COST)
    images = images[:image_count]
    text_budget = budget - IMAGE_COST * image_count
    content = message.content
    if len(content) > text_budget:
        marker = "[Message shortened to fit the model context budget.]"
        content = (
            content[: text_budget - len(marker)] + marker
            if text_budget >= len(marker)
            else content[:text_budget]
        )
    if hasattr(message, "model_copy"):
        return message.model_copy(update={"content": content, "images": images})
    fitted = copy.copy(message)
    fitted.content = content
    if hasattr(fitted, "images"):
        fitted.images = images
    return fitted


def trim_messages(messages, budget: int | None = None):
    """Returns (kept_messages, number_dropped). A budget of 0 or less disables trimming."""
    if budget is None:
        budget = CONTEXT_CHAR_BUDGET
    if budget <= 0 or not messages:
        return list(messages), 0

    newest = messages[-1]
    if message_cost(newest) > budget:
        newest = _fit_message(newest, budget)
    kept, used = [newest], message_cost(newest)
    for m in reversed(messages[:-1]):
        cost = message_cost(m)
        if used + cost > budget:
            break
        kept.append(m)
        used += cost
    kept.reverse()

    # Some providers reject a conversation that does not start with a user turn.
    while len(kept) > 1 and kept[0].role != "user":
        kept.pop(0)

    return kept, len(messages) - len(kept)
