DEFAULT_MAX_RETRY = 3


def normalize_max_retry(max_retry: int | None, default: int = DEFAULT_MAX_RETRY) -> int:
    if max_retry is None:
        return default
    return int(max_retry)


def should_retry_attempt(attempt: int, max_retry: int | None, default: int = DEFAULT_MAX_RETRY) -> bool:
    normalized = normalize_max_retry(max_retry, default)
    return normalized <= 0 or attempt < normalized


def format_retry_limit(max_retry: int | None, default: int = DEFAULT_MAX_RETRY) -> str:
    normalized = normalize_max_retry(max_retry, default)
    return "∞" if normalized <= 0 else str(normalized)


def retry_wait_seconds(attempt: int) -> int:
    return min(30, 2 ** min(attempt, 5))
