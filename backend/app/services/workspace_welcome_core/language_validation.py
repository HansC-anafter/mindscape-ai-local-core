"""Locale validation helpers for workspace welcome messages."""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class LanguageValidationResult:
    is_valid: bool
    log_level: str | None = None
    message: str | None = None
    error: str | None = None


def _normalize_language(value: str | None) -> str | None:
    if value and "-" in value:
        return value.split("-")[0]
    return value


def _count_chars_in_ranges(
    value: str,
    ranges: Iterable[tuple[str, str]],
) -> int:
    return sum(1 for char in value if any(start <= char <= end for start, end in ranges))


def _minimum_locale_chars(value: str) -> float:
    return max(10, len(value) * 0.1)


def _invalid_language_result(
    *,
    locale: str,
    detected_lang: str | None,
    count: int,
    language_label: str,
) -> LanguageValidationResult:
    return LanguageValidationResult(
        is_valid=False,
        log_level="warning",
        message=(
            "LLM generated message appears to be in wrong language for locale "
            f"{locale} (detected: {detected_lang}, only {count} {language_label} "
            "chars), falling back to i18n"
        ),
        error="LLM generated message in wrong language",
    )


def validate_welcome_message_locale(
    welcome_message: str,
    locale: str,
    detected_lang: str | None,
) -> LanguageValidationResult:
    normalized_locale = _normalize_language(locale)
    normalized_detected = _normalize_language(detected_lang)

    if normalized_locale == "zh":
        if normalized_detected not in ["zh", "zh-TW", "zh-CN"]:
            char_count = _count_chars_in_ranges(
                welcome_message,
                [("\u4e00", "\u9fff")],
            )
            if char_count < _minimum_locale_chars(welcome_message):
                return _invalid_language_result(
                    locale=locale,
                    detected_lang=detected_lang,
                    count=char_count,
                    language_label="Chinese",
                )
    elif normalized_locale == "ja":
        if normalized_detected != "ja":
            char_count = _count_chars_in_ranges(
                welcome_message,
                [
                    ("\u3040", "\u309f"),
                    ("\u30a0", "\u30ff"),
                    ("\u4e00", "\u9faf"),
                ],
            )
            if char_count < _minimum_locale_chars(welcome_message):
                return _invalid_language_result(
                    locale=locale,
                    detected_lang=detected_lang,
                    count=char_count,
                    language_label="Japanese",
                )
    elif normalized_locale == "ko":
        if normalized_detected != "ko":
            char_count = _count_chars_in_ranges(
                welcome_message,
                [("\uac00", "\ud7a3")],
            )
            if char_count < _minimum_locale_chars(welcome_message):
                return _invalid_language_result(
                    locale=locale,
                    detected_lang=detected_lang,
                    count=char_count,
                    language_label="Korean",
                )
    elif normalized_locale == "en":
        if detected_lang and normalized_detected not in ["en", None]:
            return LanguageValidationResult(
                is_valid=True,
                log_level="debug",
                message=(
                    f"LLM generated message detected as {detected_lang} for "
                    "English locale, but allowing it"
                ),
            )
    elif detected_lang and normalized_detected != normalized_locale:
        return LanguageValidationResult(
            is_valid=True,
            log_level="warning",
            message=(
                f"LLM generated message detected as {detected_lang} for locale "
                f"{locale}, but allowing it (may be valid)"
            ),
        )

    return LanguageValidationResult(is_valid=True)
