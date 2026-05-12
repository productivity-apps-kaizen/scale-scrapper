"""
Main Renpho scale BLE listener.

Architecture: continuously scans for the scale appearing on BLE, then
connects and reads. This is the hands-off model — just step on the scale
and the script does the rest. No phone, no button press.

Usage:
    python3 listener.py              # watch until one reading, then exit
    python3 listener.py --daemon     # watch forever (use this for Pi / systemd)

macOS note: CoreBluetooth doesn't expose MAC addresses. The script uses
the device's local name ("RENPHO...") to identify the scale instead.
The 'scale_mac' in config.json is optional on Mac; required on Linux/Pi.

Requires config.json — copy config.json.example and fill it in.
"""

from __future__ import annotations

import asyncio
import json
import sys
import platform
from datetime import datetime, timedelta
from pathlib import Path

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice

from storage import save_reading
from metrics import compute as compute_metrics, age_from_dob


CANDIDATE_NOTIFY_UUIDS = [
    "0000fff4-0000-1000-8000-00805f9b34fb",  # Renpho standard
    "0000ffd7-0000-1000-8000-00805f9b34fb",  # some Renpho variants
    "00002a9d-0000-1000-8000-00805f9b34fb",  # Bluetooth SIG Weight Measurement
]

# After a successful reading, ignore the scale for this long (avoid double-logging)
COOLDOWN = timedelta(minutes=5)

IS_MACOS = platform.system() == "Darwin"


def load_config() -> dict:
    path = Path(__file__).parent / "config.json"
    if not path.exists():
        print("ERROR: config.json not found.")
        print("       Copy config.json.example to config.json and fill it in.")
        sys.exit(1)
    return json.loads(path.read_text())


def decode_packet(data: bytes) -> tuple[float | None, int | None, bool]:
    """
    Renpho ES-26 protocol (55 AA header).

    Type 0x07 — weight packet (13 bytes):
      [0-1] = 55 AA magic
      [4]   = 0x07
      [5]   = stable flag  (1 = final/stable reading)
      [8-9] = weight big-endian ÷ 100  → kg

    Type 0x0C — BIA / impedance packet (18 bytes):
      [4]   = 0x0C
      [8-9] = impedance little-endian  → Ω

    Returns (weight_kg, impedance, is_stable).
    """
    if len(data) < 5 or data[0] != 0x55 or data[1] != 0xAA:
        return None, None, False

    packet_type = data[4]

    if packet_type == 0x07 and len(data) >= 13:
        weight_raw = (data[8] << 8) | data[9]
        weight_kg = weight_raw / 100.0
        stable = data[5] == 1
        if 20.0 <= weight_kg <= 300.0:
            return weight_kg, None, stable

    if packet_type == 0x0C and len(data) >= 11:
        impedance = int.from_bytes(data[8:10], byteorder="little")
        if 100 <= impedance <= 2000:
            return None, impedance, False

    return None, None, False



def device_matches(device: BLEDevice, cfg: dict) -> bool:
    """Return True if this BLE device looks like our scale."""
    hint = cfg.get("scale_name_hint", "RENPHO").upper()
    name_match = device.name and hint in device.name.upper()

    if IS_MACOS:
        # On macOS, MAC addresses aren't exposed — match by name only
        return bool(name_match)

    mac = cfg.get("scale_mac", "").strip().upper()
    if mac and mac != "XX:XX:XX:XX:XX:XX":
        return device.address.upper() == mac

    return bool(name_match)


async def read_from_scale(device: BLEDevice, cfg: dict) -> tuple[float | None, int | None]:
    """Connect to the scale and collect one stable reading. Returns (weight_kg, impedance)."""
    weight = None
    impedance = None
    done = asyncio.Event()

    def handle(char: BleakGATTCharacteristic, data: bytes):
        nonlocal weight, impedance
        w, z, stable = decode_packet(data)

        if z is not None:
            impedance = z

        if w is not None:
            print(f"  Weight: {w:.2f} kg  stable={stable}")
            weight = w
            if stable:
                done.set()

    try:
        async with BleakClient(device, timeout=15.0) as client:
            subscribed = False
            for uuid in CANDIDATE_NOTIFY_UUIDS:
                try:
                    await client.start_notify(uuid, handle)
                    subscribed = True
                except Exception:
                    pass

            if not subscribed:
                for service in client.services:
                    for char in service.characteristics:
                        if "notify" in char.properties:
                            try:
                                await client.start_notify(char.uuid, handle)
                                subscribed = True
                            except Exception:
                                pass

            if not subscribed:
                print("  No notifiable characteristics found. Run discover.py to debug.")
                return None, None

            try:
                await asyncio.wait_for(done.wait(), timeout=45.0)
            except asyncio.TimeoutError:
                print("  Timed out waiting for stable reading.")

    except Exception as e:
        print(f"  Connection error: {e}")

    return weight, impedance


async def process_reading(cfg: dict, weight: float, impedance: int | None):
    print(f"\n==> Weight: {weight:.1f} kg")

    metrics = None
    user = cfg.get("user", {})
    age = age_from_dob(user["dob"]) if user.get("dob") else user.get("age")
    if impedance and user.get("height_cm") and age and user.get("sex"):
        metrics = compute_metrics(
            weight_kg=weight,
            impedance=impedance,
            height_cm=user["height_cm"],
            age=age,
            sex=user["sex"],
        )
        print(f"    BMI:       {metrics['bmi']}")
        print(f"    Body fat:  {metrics['body_fat_pct']}%")
        print(f"    Lean mass: {metrics['lean_mass_kg']} kg")
        print(f"    BMR:       {metrics['bmr_kcal']} kcal/day")

    await asyncio.to_thread(save_reading, cfg, weight, impedance, metrics)


def seconds_until_window(start_hour: int) -> float:
    """Seconds until the next occurrence of start_hour:00."""
    now = datetime.now()
    target = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def in_active_window(cfg: dict) -> bool:
    window = cfg.get("active_window", {})
    if not window:
        return True
    start = window.get("start_hour", 6)
    end = window.get("end_hour", 10)
    hour = datetime.now().hour
    return start <= hour < end


async def watch(cfg: dict, one_shot: bool):
    """
    Core loop: continuously scan for the scale appearing on BLE.
    When found, connect and read. In daemon mode, loop forever.
    Outside the active window, sleeps until it opens.
    """
    hint = cfg.get("scale_name_hint", "RENPHO")
    window = cfg.get("active_window", {})
    start_hour = window.get("start_hour", 6)
    end_hour = window.get("end_hour", 10)

    print(f"Watching for '{hint}' scale via BLE...")
    if IS_MACOS:
        print("(macOS detected — identifying scale by name, not MAC address)")
    if window:
        print(f"Active window: {start_hour:02d}:00 – {end_hour:02d}:00\n")
    else:
        print("Just step on the scale whenever you like.\n")

    last_reading_at: datetime | None = None

    while True:
        if not in_active_window(cfg):
            secs = seconds_until_window(start_hour)
            wake = datetime.now() + timedelta(seconds=secs)
            print(f"Outside active window. Sleeping until {wake.strftime('%H:%M')}...")
            await asyncio.sleep(secs)
            print(f"Active window open. Watching for scale...\n")
            continue

        devices = await BleakScanner.discover(timeout=5.0)

        for device in devices:
            if not device_matches(device, cfg):
                continue

            if last_reading_at and datetime.now() - last_reading_at < COOLDOWN:
                continue

            print(f"Scale detected: {device.name}  ({device.address})")
            weight, impedance = await read_from_scale(device, cfg)

            if weight is not None:
                last_reading_at = datetime.now()
                await process_reading(cfg, weight, impedance)
                if one_shot:
                    return
                print(f"\nCooldown active for {COOLDOWN.seconds // 60} min. Watching again...\n")
            break

        await asyncio.sleep(1)


if __name__ == "__main__":
    one_shot = "--daemon" not in sys.argv
    cfg = load_config()
    asyncio.run(watch(cfg, one_shot=one_shot))
