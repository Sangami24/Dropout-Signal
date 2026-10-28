"""
FloraMind — Research-Grounded Dataset Generator
================================================
Generates a realistic acoustic cavitation dataset based on the
Tel Aviv University study (Khait et al., 2023, Cell):

  "Sounds emitted by plants under stress are airborne and informative"

Key calibration points from the paper:
  - Frequency range: 20–100 kHz (ultrasonic)
  - Drought-stressed tomato:  ~35 clicks/hour
  - Drought-stressed tobacco: ~11 clicks/hour
  - Well-watered plants:      <1 click/hour
  - Click duration:           1–5 ms
  - Mechanism:                xylem cavitation
  - ML accuracy:              ~70% stress-type classification from sound alone

The generator models a 5-day drought progression across 6 field sensors
with 5 crop species, diurnal temperature variation, and sub-ultrasonic
environmental noise events.

Output: data/acoustic_samples.csv  (~600 rows)
"""

import csv
import math
import os
import random
from datetime import datetime, timedelta, timezone

random.seed(42)

# ── Field layout: 6 sensors, each assigned a species & sector ────────
SENSORS = [
    {"sensor_id": "MIC-001", "plant_species": "solanum_lycopersicum", "sector": "A1"},  # tomato
    {"sensor_id": "MIC-002", "plant_species": "nicotiana_tabacum",    "sector": "A2"},  # tobacco
    {"sensor_id": "MIC-003", "plant_species": "zea_mays",            "sector": "B1"},  # maize / corn
    {"sensor_id": "MIC-004", "plant_species": "triticum_aestivum",   "sector": "B2"},  # wheat
    {"sensor_id": "MIC-005", "plant_species": "oryza_sativa",        "sector": "C1"},  # rice
    {"sensor_id": "MIC-006", "plant_species": "solanum_lycopersicum", "sector": "C2"},  # tomato (irrigated control)
]

# ── Species-specific acoustic profiles (calibrated to Khait et al.) ──
#    max_clicks_per_hour = peak click rate under severe drought
#    freq_center / freq_sigma = Gaussian params for frequency (kHz)
#    amp_base / amp_stress = amplitude range [well-watered → drought]
#    duration_mean / sigma = click duration in seconds
SPECIES_PROFILES = {
    "solanum_lycopersicum": {
        "max_clicks_per_hour": 35,   # Khait et al.: ~35 clicks/hr
        "freq_center_khz": 52.0,
        "freq_sigma_khz": 12.0,
        "amp_base": 0.15,
        "amp_stress": 1.10,
        "duration_mean_sec": 0.003,
        "duration_sigma_sec": 0.001,
    },
    "nicotiana_tabacum": {
        "max_clicks_per_hour": 11,   # Khait et al.: ~11 clicks/hr
        "freq_center_khz": 45.0,
        "freq_sigma_khz": 10.0,
        "amp_base": 0.12,
        "amp_stress": 0.85,
        "duration_mean_sec": 0.004,
        "duration_sigma_sec": 0.001,
    },
    "zea_mays": {
        "max_clicks_per_hour": 28,   # estimated from related literature
        "freq_center_khz": 58.0,
        "freq_sigma_khz": 14.0,
        "amp_base": 0.18,
        "amp_stress": 1.05,
        "duration_mean_sec": 0.002,
        "duration_sigma_sec": 0.001,
    },
    "triticum_aestivum": {
        "max_clicks_per_hour": 22,   # estimated
        "freq_center_khz": 40.0,
        "freq_sigma_khz": 9.0,
        "amp_base": 0.14,
        "amp_stress": 0.92,
        "duration_mean_sec": 0.003,
        "duration_sigma_sec": 0.001,
    },
    "oryza_sativa": {
        "max_clicks_per_hour": 18,   # estimated — rice is semi-aquatic
        "freq_center_khz": 48.0,
        "freq_sigma_khz": 11.0,
        "amp_base": 0.10,
        "amp_stress": 0.78,
        "duration_mean_sec": 0.003,
        "duration_sigma_sec": 0.001,
    },
}

# ── Simulation parameters ────────────────────────────────────────────
START_DATE = datetime(2026, 4, 1, 6, 0, 0, tzinfo=timezone.utc)  # Day 1 morning
NUM_DAYS = 5
HOURS_PER_DAY = 16  # 06:00–22:00 (sensors active during daylight)

# Soil moisture model: starts saturated, declines to drought
INITIAL_SOIL_MOISTURE = 45.0   # %
FINAL_SOIL_MOISTURE = 6.0      # % (severe drought by Day 5)
# Sensor MIC-006 stays irrigated (control group)
CONTROL_SENSOR = "MIC-006"
CONTROL_MOISTURE = 42.0        # stays high

# Diurnal temperature curve (affects cavitation rate)
# Peak stress at solar noon–3pm → more clicks
def diurnal_factor(hour: int) -> float:
    """Return a multiplier [0.3, 1.0] based on hour of day.
    Peak at 14:00 (solar noon +2h), lowest at 06:00 and 22:00."""
    return 0.3 + 0.7 * math.exp(-0.5 * ((hour - 14) / 3.5) ** 2)

# Environmental noise events (wind, machinery, insects < 20 kHz)
NOISE_PROBABILITY = 0.08  # 8% of time-slots get a noise event


def soil_moisture_at(day: int, hour: int, sensor_id: str) -> float:
    """Model soil moisture declining over 5 days with slight diurnal dip."""
    if sensor_id == CONTROL_SENSOR:
        return CONTROL_MOISTURE + random.gauss(0, 1.2)

    # Linear decline from Day 1 to Day 5
    progress = ((day - 1) * HOURS_PER_DAY + (hour - 6)) / (NUM_DAYS * HOURS_PER_DAY)
    base = INITIAL_SOIL_MOISTURE - progress * (INITIAL_SOIL_MOISTURE - FINAL_SOIL_MOISTURE)

    # Slight afternoon dip (evapotranspiration)
    afternoon_dip = 1.5 * diurnal_factor(hour)
    return max(2.0, base - afternoon_dip + random.gauss(0, 0.8))


def stress_level(soil_moisture: float) -> str:
    """Classify stress severity — this becomes the ML training label."""
    if soil_moisture >= 30.0:
        return "NORMAL"
    elif soil_moisture >= 15.0:
        return "WARNING"
    else:
        return "CRITICAL"


def click_rate(profile: dict, soil_moisture: float, hour: int) -> float:
    """Expected clicks per hour given moisture and time of day."""
    max_cph = profile["max_clicks_per_hour"]

    # Moisture → stress intensity: sigmoid mapping
    # At 45% moisture → near 0; at 10% → near max
    midpoint = 22.0  # inflection point (% soil moisture)
    steepness = 0.25
    stress_intensity = 1.0 / (1.0 + math.exp(steepness * (soil_moisture - midpoint)))

    return max_cph * stress_intensity * diurnal_factor(hour)


def generate_click(sensor: dict, profile: dict, ts: datetime, soil_m: float) -> dict:
    """Generate one acoustic click event."""
    # Frequency shifts higher under more stress (thinner water columns cavitate at higher freq)
    stress_shift = max(0, (30 - soil_m) / 30) * 8.0  # up to +8 kHz shift
    freq = random.gauss(
        profile["freq_center_khz"] + stress_shift,
        profile["freq_sigma_khz"]
    )
    freq = max(20.0, min(100.0, freq))  # clamp to ultrasonic range

    # Amplitude increases with stress
    stress_frac = max(0, (40 - soil_m) / 40)
    amp = profile["amp_base"] + stress_frac * (profile["amp_stress"] - profile["amp_base"])
    amp += random.gauss(0, 0.05)
    amp = max(0.05, round(amp, 3))

    # Duration
    dur = abs(random.gauss(profile["duration_mean_sec"], profile["duration_sigma_sec"]))
    dur = max(0.001, round(dur, 4))

    # Jitter the timestamp within the hour
    jitter_sec = random.randint(0, 3599)
    event_ts = ts + timedelta(seconds=jitter_sec)

    return {
        "sensor_id": sensor["sensor_id"],
        "timestamp": event_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "peak_frequency": round(freq, 1),
        "duration": round(dur, 4),
        "amplitude": amp,
        "plant_species": sensor["plant_species"],
        "soil_moisture_pct": round(soil_m, 1),
        "sector": sensor["sector"],
        "stress_label": stress_level(soil_m),
    }


def generate_noise_event(sensor: dict, ts: datetime, soil_m: float) -> dict:
    """Generate a sub-ultrasonic noise event (wind, tractor, insects)."""
    freq = random.uniform(3.0, 19.5)  # below the 20 kHz ultrasonic floor
    amp = random.uniform(0.02, 0.35)
    dur = random.uniform(0.05, 0.5)   # noise is longer than cavitation clicks

    jitter_sec = random.randint(0, 3599)
    event_ts = ts + timedelta(seconds=jitter_sec)

    return {
        "sensor_id": sensor["sensor_id"],
        "timestamp": event_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "peak_frequency": round(freq, 1),
        "duration": round(dur, 4),
        "amplitude": round(amp, 3),
        "plant_species": sensor["plant_species"],
        "soil_moisture_pct": round(soil_m, 1),
        "sector": sensor["sector"],
        "stress_label": "NOISE",
    }


def main():
    rows = []

    for day in range(1, NUM_DAYS + 1):
        for hour_offset in range(HOURS_PER_DAY):
            hour = 6 + hour_offset  # 06:00 to 21:00
            ts = START_DATE + timedelta(days=day - 1, hours=hour_offset)

            for sensor in SENSORS:
                species = sensor["plant_species"]
                profile = SPECIES_PROFILES[species]
                soil_m = soil_moisture_at(day, hour, sensor["sensor_id"])

                # Calculate expected clicks this hour
                rate = click_rate(profile, soil_m, hour)
                # Poisson-sample the actual number of clicks
                n_clicks = random.randint(
                    max(0, int(rate * 0.6)),
                    max(0, int(rate * 1.4)) + 1
                )

                for _ in range(n_clicks):
                    rows.append(generate_click(sensor, profile, ts, soil_m))

                # Occasional noise events
                if random.random() < NOISE_PROBABILITY:
                    rows.append(generate_noise_event(sensor, ts, soil_m))

    # Sort by timestamp for natural streaming order
    rows.sort(key=lambda r: r["timestamp"])

    # Write CSV
    out_path = os.path.join(os.path.dirname(__file__), "data", "acoustic_samples.csv")
    fieldnames = [
        "sensor_id", "timestamp", "peak_frequency", "duration",
        "amplitude", "plant_species", "soil_moisture_pct",
        "sector", "stress_label",
    ]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Stats
    labels = {}
    species_counts = {}
    sensor_counts = {}
    for r in rows:
        labels[r["stress_label"]] = labels.get(r["stress_label"], 0) + 1
        species_counts[r["plant_species"]] = species_counts.get(r["plant_species"], 0) + 1
        sensor_counts[r["sensor_id"]] = sensor_counts.get(r["sensor_id"], 0) + 1

    print(f"\n{'='*60}")
    print(f"  FloraMind Dataset Generated — {len(rows):,} rows")
    print(f"  Output: {out_path}")
    print(f"{'='*60}")
    print(f"\n  Stress Labels:")
    for lbl, cnt in sorted(labels.items()):
        print(f"    {lbl:10s}: {cnt:5d}  ({cnt/len(rows)*100:.1f}%)")
    print(f"\n  By Species:")
    for sp, cnt in sorted(species_counts.items()):
        print(f"    {sp:30s}: {cnt:5d}")
    print(f"\n  By Sensor:")
    for sid, cnt in sorted(sensor_counts.items()):
        print(f"    {sid}: {cnt:5d}")
    print()


if __name__ == "__main__":
    main()
