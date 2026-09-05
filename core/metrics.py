"""Metric values retain the reason telemetry is unavailable."""

import math

DOWN = "down"
MISSING = "missing"
INVALID = "invalid"
ERROR = "error"
STATUS_TEXT = {DOWN: "中断", MISSING: "无数据", INVALID: "数据异常", ERROR: "查询失败"}


def valid_metric(value, *, maximum=None):
    if value is None:
        return MISSING
    if isinstance(value, str) and value.lower() in STATUS_TEXT:
        return value.lower()
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return INVALID
    if not math.isfinite(number) or number < 0 or (maximum is not None and number > maximum):
        return INVALID
    return number
