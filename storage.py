from __future__ import annotations

"""MongoDB storage and ntfy.sh push notifications."""
import json
import certifi
from datetime import datetime, timezone
from pathlib import Path
from pymongo import MongoClient

_mongo_client: MongoClient | None = None


def _get_collection(cfg: dict):
    global _mongo_client
    mongo_cfg = cfg.get("mongodb", {})
    uri = mongo_cfg.get("uri", "")
    if not uri:
        return None
    if _mongo_client is None:
        _mongo_client = MongoClient(uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=8000)
    return _mongo_client[mongo_cfg.get("database", "health")][mongo_cfg.get("collection", "weight")]


def save_to_mongo(cfg: dict, entry: dict):
    try:
        col = _get_collection(cfg)
        if col is None:
            return
        doc = {k: v for k, v in entry.items()}
        col.insert_one(doc)
        print("Saved to MongoDB", flush=True)
    except Exception as e:
        print(f"MongoDB error: {e}", flush=True)
        push_alert(cfg, "MongoDB save failed", f"Reading saved locally but failed to reach MongoDB: {e}", tags="warning,x")


def save_to_file(cfg: dict, entry: dict):
    log_path = Path(__file__).parent / cfg.get("log_file", "weights.json")
    history = []
    if log_path.exists():
        try:
            history = json.loads(log_path.read_text())
        except Exception:
            pass
    history.append(entry)
    log_path.write_text(json.dumps(history, indent=2))


def push_alert(cfg: dict, title: str, message: str, tags: str = "warning"):
    topic = cfg.get("ntfy", {}).get("topic", "")
    if not topic:
        return
    try:
        import requests
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=message,
            headers={"Title": title, "Tags": tags},
            timeout=5,
        )
    except Exception as e:
        print(f"ntfy error: {e}")


def push_notify(cfg: dict, weight_kg: float, metrics: dict | None = None):
    topic = cfg.get("ntfy", {}).get("topic", "")
    if not topic:
        return
    lines = [f"Weight: {weight_kg:.2f} kg"]
    if metrics:
        lines.append(f"BMI: {metrics.get('bmi', '?')}  |  Body fat: {metrics.get('body_fat_pct', '?')}%")
    try:
        import requests
        requests.post(
            f"https://ntfy.sh/{topic}",
            data="\n".join(lines),
            headers={"Title": f"{weight_kg:.2f} kg"},
            timeout=5,
        )
        print(f"Push sent → ntfy.sh/{topic}")
    except Exception as e:
        print(f"ntfy error: {e}")


def save_reading(cfg: dict, weight_kg: float, impedance: int | None, metrics: dict | None):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # Raw BIA data from scale
        "raw": {
            "weight_kg": weight_kg,
            "impedance_ohm": impedance,
        },
        # Convenience top-level fields
        "weight_kg": weight_kg,
        "impedance": impedance,
    }
    if metrics:
        entry["metrics"] = metrics
        # Keep flat fields for backwards compat
        entry.update(metrics)

    save_to_file(cfg, entry)
    save_to_mongo(cfg, entry)
    push_notify(cfg, weight_kg, metrics)
