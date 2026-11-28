"""Hugging Face Multi-Account Fallback Manager for Afrigen.

Provides seamless failover across multiple Hugging Face accounts (e.g. 3 accounts).
If Account 1 encounters a rate limit (429), auth error (401/403), service outage,
or inference failure, the request automatically falls back to Account 2, then Account 3.

Configuration options (env):
  Account 1: HF_TOKEN_1 or HF_TOKEN or HUGGINGFACE_API_KEY or HUGGINGFACE_TOKEN
  Account 2: HF_TOKEN_2 or HUGGINGFACE_TOKEN_2 or HUGGINGFACE_API_KEY_2
  Account 3: HF_TOKEN_3 or HUGGINGFACE_TOKEN_3 or HUGGINGFACE_API_KEY_3
  Or comma-separated: HF_TOKENS="hf_tok1,hf_tok2,hf_tok3"
"""

import os
import time
import logging
import threading
from typing import List, Dict, Any, Optional, Callable, Tuple

logger = logging.getLogger(__name__)

# Lock for thread-safe state tracking
_state_lock = threading.Lock()

# Track cooldowns per token: token -> timestamp when cooldown ends
_token_cooldowns: Dict[str, float] = {}

# Default cooldown duration in seconds when rate limit (429) is hit
DEFAULT_RATE_LIMIT_COOLDOWN = 180.0  # 3 minutes
DEFAULT_AUTH_ERROR_COOLDOWN = 600.0  # 10 minutes
DEFAULT_GENERAL_ERROR_COOLDOWN = 60.0  # 1 minute


def _mask_token(token: Optional[str]) -> str:
    """Return a safely redacted token representation for logging."""
    if not token:
        return "None"
    token_str = str(token).strip()
    if len(token_str) <= 8:
        return "***"
    return f"{token_str[:4]}...{token_str[-4:]}"


def get_all_hf_tokens() -> List[str]:
    """Retrieve all configured Hugging Face tokens in priority order (1, 2, 3...).

    Checks explicit numbered variables first, comma-separated lists, and standard fallbacks.
    Returns a deduplicated list of non-empty tokens.
    """
    tokens: List[str] = []

    # 1. Comma-separated list in HF_TOKENS or HUGGINGFACE_TOKENS
    for env_var in ("HF_TOKENS", "HUGGINGFACE_TOKENS"):
        raw_list = os.environ.get(env_var, "").strip()
        if raw_list:
            for item in raw_list.split(","):
                clean = item.strip()
                if clean and clean not in tokens:
                    tokens.append(clean)

    # 2. Numbered variables: HF_TOKEN_1, HF_TOKEN_2, HF_TOKEN_3, etc.
    for i in range(1, 10):
        found = (
            os.environ.get(f"HF_TOKEN_{i}")
            or os.environ.get(f"HUGGINGFACE_TOKEN_{i}")
            or os.environ.get(f"HUGGINGFACE_API_KEY_{i}")
        )
        if found:
            clean = found.strip()
            if clean and clean not in tokens:
                tokens.append(clean)

    # 3. Standard single variable fallback for Account 1 if not already present
    primary = (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGINGFACE_API_KEY")
        or os.environ.get("HUGGINGFACE_TOKEN")
    )
    if primary:
        clean = primary.strip()
        if clean and clean not in tokens:
            tokens.insert(0, clean)

    return tokens


def get_hf_accounts() -> List[Dict[str, Any]]:
    """Return structured account metadata for all configured accounts."""
    tokens = get_all_hf_tokens()
    now = time.time()
    accounts = []

    with _state_lock:
        for idx, token in enumerate(tokens, start=1):
            cooldown_until = _token_cooldowns.get(token, 0.0)
            in_cooldown = cooldown_until > now
            remaining_cooldown = max(0.0, cooldown_until - now) if in_cooldown else 0.0

            accounts.append({
                "account_index": idx,
                "name": f"Account {idx}",
                "token": token,
                "masked_token": _mask_token(token),
                "in_cooldown": in_cooldown,
                "cooldown_remaining": round(remaining_cooldown, 1),
            })

    return accounts


def mark_token_failure(token: str, error: Any, cooldown_seconds: Optional[float] = None) -> None:
    """Record a failure for a token and place it in temporary cooldown."""
    if not token:
        return

    err_str = str(error).lower()
    if cooldown_seconds is None:
        if "429" in err_str or "rate limit" in err_str or "quota" in err_str:
            cooldown_seconds = DEFAULT_RATE_LIMIT_COOLDOWN
        elif "401" in err_str or "403" in err_str or "unauthorized" in err_str or "invalid token" in err_str:
            cooldown_seconds = DEFAULT_AUTH_ERROR_COOLDOWN
        else:
            cooldown_seconds = DEFAULT_GENERAL_ERROR_COOLDOWN

    with _state_lock:
        _token_cooldowns[token] = time.time() + cooldown_seconds

    logger.warning(
        "[HF Fallback] Account token %s placed in cooldown for %.0fs due to: %s",
        _mask_token(token), cooldown_seconds, str(error)[:120]
    )


def mark_token_success(token: str) -> None:
    """Clear any cooldown for a token upon successful execution."""
    if not token:
        return
    with _state_lock:
        if token in _token_cooldowns:
            del _token_cooldowns[token]


def reset_cooldowns() -> None:
    """Clear all token cooldowns (useful for testing or manual reset)."""
    with _state_lock:
        _token_cooldowns.clear()


def get_active_hf_token() -> Optional[str]:
    """Return the first ready (non-cooldown) token, or the first configured token if all are cooling down."""
    accounts = get_hf_accounts()
    if not accounts:
        return None

    # Prefer first healthy account not in cooldown
    for acc in accounts:
        if not acc["in_cooldown"]:
            return acc["token"]

    # Fallback to the first account with lowest remaining cooldown
    sorted_by_cooldown = sorted(accounts, key=lambda a: a["cooldown_remaining"])
    return sorted_by_cooldown[0]["token"]


def execute_hf_with_fallback(
    operation: Callable[[str, Dict[str, Any]], Any],
    operation_name: str = "Hugging Face operation",
) -> Any:
    """Execute a callable across all configured HF accounts with automatic failover.

    Args:
        operation: Callable receiving (token, account_dict) and returning a result.
                   Can raise an Exception or return a dict with {"ok": False, "error": ...}
                   or {"success": False, "error": ...}.
        operation_name: Human-readable name for logging.

    Returns:
        The result of the operation from the first succeeding account.

    Raises:
        RuntimeError if all configured accounts fail or no accounts are configured.
    """
    accounts = get_hf_accounts()
    if not accounts:
        err = f"No Hugging Face accounts configured. Set HF_TOKEN, HF_TOKEN_2, HF_TOKEN_3."
        logger.error("[HF Fallback] %s failed: %s", operation_name, err)
        raise RuntimeError(err)

    # Sort accounts: healthy ones first (in priority order), then those in cooldown
    # (ordered by least cooldown time remaining)
    ordered_accounts = sorted(
        accounts,
        key=lambda a: (1 if a["in_cooldown"] else 0, a["cooldown_remaining"], a["account_index"])
    )

    total_accounts = len(ordered_accounts)
    attempted_errors: List[str] = []

    for attempt_num, acc in enumerate(ordered_accounts, start=1):
        idx = acc["account_index"]
        masked = acc["masked_token"]
        token = acc["token"]

        if acc["in_cooldown"]:
            logger.info(
                "[HF Fallback] Account %d (%s) is cooling down (%.1fs remaining), attempting anyway as fallback...",
                idx, masked, acc["cooldown_remaining"]
            )
        else:
            logger.info(
                "[HF Fallback] Trying Account %d/%d (%s) for %s...",
                idx, total_accounts, masked, operation_name
            )

        try:
            result = operation(token, acc)

            # Check if result is a dict with explicit failure indicators
            if isinstance(result, dict):
                # Handles {"ok": False, "error": ...} or {"success": False, "error": ...}
                has_failed = (result.get("ok") is False) or (result.get("success") is False)
                if has_failed:
                    err_msg = result.get("error") or "Unknown operation failure"
                    logger.warning(
                        "[HF Fallback] Account %d (%s) returned failure: %s",
                        idx, masked, str(err_msg)[:200]
                    )
                    mark_token_failure(token, err_msg)
                    attempted_errors.append(f"Account {idx} ({masked}): {err_msg}")

                    # If there are more accounts, fall back to next
                    if attempt_num < total_accounts:
                        next_acc = ordered_accounts[attempt_num]
                        logger.warning(
                            "[HF Fallback] Falling back from Account %d to Account %d (%s)...",
                            idx, next_acc["account_index"], next_acc["masked_token"]
                        )
                        continue
                    else:
                        logger.error(
                            "[HF Fallback] All %d Hugging Face accounts exhausted for %s.",
                            total_accounts, operation_name
                        )
                        return result

            # Success!
            mark_token_success(token)
            if attempt_num > 1:
                logger.info(
                    "[HF Fallback] Succeeded on Account %d (%s) after previous account(s) failed.",
                    idx, masked
                )
            return result

        except Exception as exc:
            err_msg = str(exc)
            logger.warning(
                "[HF Fallback] Account %d (%s) raised exception during %s: %s",
                idx, masked, operation_name, err_msg[:200]
            )
            mark_token_failure(token, exc)
            attempted_errors.append(f"Account {idx} ({masked}): {err_msg}")

            if attempt_num < total_accounts:
                next_acc = ordered_accounts[attempt_num]
                logger.warning(
                    "[HF Fallback] Failing over from Account %d to Account %d (%s)...",
                    idx, next_acc["account_index"], next_acc["masked_token"]
                )
                continue
            else:
                logger.error(
                    "[HF Fallback] All %d Hugging Face accounts failed for %s. Errors: %s",
                    total_accounts, operation_name, "; ".join(attempted_errors)
                )
                raise RuntimeError(
                    f"All {total_accounts} Hugging Face accounts failed for {operation_name}: {'; '.join(attempted_errors)}"
                ) from exc

    # If we get here, all failed
    raise RuntimeError(f"All {total_accounts} Hugging Face accounts failed for {operation_name}: {'; '.join(attempted_errors)}")
