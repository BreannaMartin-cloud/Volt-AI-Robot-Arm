"""VOLT robot - calibration persistence.

Owns ``calibration.json``: the machine-specific record of everything
measured during calibration. ``config.py`` keeps safe factory defaults;
this module overlays the measured values on top of them at runtime, so
calibrating never requires editing config.py by hand.

File schema (all sections optional until saved)::

    {
      "CALIBRATED": true,
      "SERVO_TRIM_DEG":   {"base": 3, ...},
      "SOFT_LIMITS_DEG":  {"base": [10, 170], ...},
      "HOME_POSE":          {"base": 90, ...},
      "IDLE_POSE":          {"base": 90, ...},
      "SAFE_SHUTDOWN_POSE": {"base": 90, ...}
    }

``CALIBRATED`` is managed by this module: it becomes true automatically
once all three poses have been saved, and is never set by hand.

Every write backs up the previous file to ``calibration_backup.json``
and goes through an atomic replace, so a crash mid-save can never leave
a corrupt calibration.
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Any, Dict, Optional

import config
from utils import get_logger

log = get_logger("calibration")

#: calibrate.py pose-name -> file section.
POSE_KEYS: Dict[str, str] = {
    "home": "HOME_POSE",
    "idle": "IDLE_POSE",
    "shutdown": "SAFE_SHUTDOWN_POSE",
}

#: File sections that must exist before the robot counts as calibrated.
REQUIRED_SECTIONS = tuple(POSE_KEYS.values())

_TRIMS_KEY = "SERVO_TRIM_DEG"
_LIMITS_KEY = "SOFT_LIMITS_DEG"
_CALIBRATED_KEY = "CALIBRATED"


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def load() -> Optional[Dict[str, Any]]:
    """Parsed calibration.json, or None if absent/unreadable."""
    try:
        with open(config.CALIBRATION_FILE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None
    except (ValueError, OSError) as exc:
        log.error("calibration file unreadable (%s); ignoring it", exc)
        return None
    if not isinstance(data, dict):
        log.error("calibration file is not a JSON object; ignoring it")
        return None
    return data


def apply() -> bool:
    """Overlay calibration.json onto config's in-memory values.

    Safe to call repeatedly (idempotent). Unknown joints and malformed
    entries are skipped with a warning rather than trusted. Returns True
    if a calibration file was found and applied.
    """
    data = load()
    if data is None:
        log.info("no calibration file at %s; using config.py defaults",
                 config.CALIBRATION_FILE_PATH)
        return False

    for joint, trim in _joint_items(data.get(_TRIMS_KEY), "trim"):
        config.SERVO_TRIM_DEG[joint] = int(trim)

    for joint, pair in _joint_items(data.get(_LIMITS_KEY), "limits"):
        if (isinstance(pair, (list, tuple)) and len(pair) == 2
                and all(isinstance(v, (int, float)) for v in pair)):
            config.SOFT_LIMITS_DEG[joint] = (int(pair[0]), int(pair[1]))
        else:
            log.warning("skipping malformed limits for '%s': %r", joint, pair)

    for section, pose in (
        ("HOME_POSE", config.HOME_POSE),
        ("IDLE_POSE", config.IDLE_POSE),
        ("SAFE_SHUTDOWN_POSE", config.SAFE_SHUTDOWN_POSE),
    ):
        for joint, angle in _joint_items(data.get(section), section):
            pose[joint] = int(angle)  # mutate in place: NAMED_POSES aliases these

    config.CALIBRATED = bool(data.get(_CALIBRATED_KEY, False))
    log.info("calibration applied from %s (CALIBRATED=%s)",
             config.CALIBRATION_FILE_PATH, config.CALIBRATED)
    return True


def is_complete(data: Optional[Dict[str, Any]] = None) -> bool:
    """True when every required pose has been saved."""
    if data is None:
        data = load() or {}
    return all(section in data for section in REQUIRED_SECTIONS)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _update(sections: Dict[str, Any]) -> Dict[str, Any]:
    """Read-modify-write: merge ``sections`` in, recompute CALIBRATED,
    back up the previous file, and atomically write the result."""
    data = load() or {}
    data.update(sections)
    data[_CALIBRATED_KEY] = is_complete(data)

    if os.path.exists(config.CALIBRATION_FILE_PATH):
        shutil.copy2(config.CALIBRATION_FILE_PATH, config.CALIBRATION_BACKUP_PATH)

    tmp_path = config.CALIBRATION_FILE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp_path, config.CALIBRATION_FILE_PATH)

    config.CALIBRATED = data[_CALIBRATED_KEY]
    log.info("calibration saved: %s (CALIBRATED=%s)",
             sorted(sections), config.CALIBRATED)
    return data


def save_pose(name: str, pose: Dict[str, float]) -> Dict[str, Any]:
    """Persist ``pose`` as home/idle/shutdown; also updates config in memory."""
    section = POSE_KEYS.get(name)
    if section is None:
        raise KeyError(f"unknown pose '{name}'; options: {sorted(POSE_KEYS)}")
    clean = {joint: int(round(pose[joint])) for joint in config.JOINT_ORDER}
    target = {
        "HOME_POSE": config.HOME_POSE,
        "IDLE_POSE": config.IDLE_POSE,
        "SAFE_SHUTDOWN_POSE": config.SAFE_SHUTDOWN_POSE,
    }[section]
    target.update(clean)
    return _update({section: clean})


def save_trims() -> Dict[str, Any]:
    """Persist the current in-memory trims."""
    return _update({_TRIMS_KEY: dict(config.SERVO_TRIM_DEG)})


def save_limits() -> Dict[str, Any]:
    """Persist the current in-memory soft limits."""
    return _update(
        {_LIMITS_KEY: {j: list(v) for j, v in config.SOFT_LIMITS_DEG.items()}}
    )


def save_all() -> Dict[str, Any]:
    """Persist trims and limits together (poses are saved individually,
    since each one is a distinct physical position)."""
    return _update(
        {
            _TRIMS_KEY: dict(config.SERVO_TRIM_DEG),
            _LIMITS_KEY: {j: list(v) for j, v in config.SOFT_LIMITS_DEG.items()},
        }
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def describe() -> str:
    """Human-readable summary of the calibration file for 'show calibration'."""
    data = load()
    if data is None:
        return (
            f"No calibration file at {config.CALIBRATION_FILE_PATH}.\n"
            "Running on config.py factory defaults - robot is NOT calibrated."
        )
    lines = [f"Calibration file: {config.CALIBRATION_FILE_PATH}",
             f"CALIBRATED: {data.get(_CALIBRATED_KEY, False)}"]
    missing = [s for s in REQUIRED_SECTIONS if s not in data]
    if missing:
        lines.append(f"Still needed before CALIBRATED flips true: {missing}")
    for section in (_TRIMS_KEY, _LIMITS_KEY, *REQUIRED_SECTIONS):
        if section in data:
            lines.append(f"\n{section}:")
            for joint in config.JOINT_ORDER:
                if joint in data[section]:
                    lines.append(f"  {joint:<12} {data[section][joint]}")
    return "\n".join(lines)


def _joint_items(section: Any, label: str):
    """Yield (joint, value) pairs from a file section, skipping unknowns."""
    if not isinstance(section, dict):
        return
    for joint, value in section.items():
        if joint not in config.SERVO_CHANNELS:
            log.warning("skipping unknown joint '%s' in %s", joint, label)
            continue
        yield joint, value
