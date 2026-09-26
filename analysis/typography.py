"""Типографика текстов, которые сервис показывает диспетчеру: ёлочки, тире, десятичная запятая.

Исходные таблицы (справочник организаторов, расписание transport.mos.ru, external/events_2025.csv)
остаются как есть: их читают шаги модели. Правится только то, что уходит в artifacts/.
"""

import re


def quotes(text: str) -> str:
    """Метро "ВДНХ" -> Метро «ВДНХ»."""
    return re.sub(r'(^|[\s(«])"', r"\1«", text).replace('"', "»")


def dashes(text: str) -> str:
    """Конечные остановки через тире, диапазоны чисел через короткое тире."""
    return re.sub(r"(\d)-(\d)", "\\1–\\2", text.replace(" - ", " — "))


def decimals(text: str) -> str:
    """0.38 -> 0,38 и 10.6 тыс. -> 10,6 тыс.; даты вида 06.09 не трогает."""
    text = re.sub(r"(?<![\d.])0\.(\d)", r"0,\1", text)
    return re.sub(r"(\d)\.(\d) тыс", r"\1,\2 тыс", text)


def for_people(text: str) -> str:
    return decimals(dashes(quotes(text)))
