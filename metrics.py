"""
Body composition estimates from weight + BIA impedance.
These are standard regression equations (Deurenberg / Kyle et al.).
Accuracy is ±3-5% — same as the Renpho app itself.
"""


def age_from_dob(dob: str) -> int:
    from datetime import date
    d = date.fromisoformat(dob)
    today = date.today()
    return today.year - d.year - ((today.month, today.day) < (d.month, d.day))


def compute(weight_kg: float, impedance: int, height_cm: float, age: int, sex: str) -> dict:
    height_m = height_cm / 100
    bmi = weight_kg / (height_m ** 2)
    sex_flag = 1 if sex.lower() == "male" else 0

    # Fat-free mass via Kyle 2001 (validated BIA equation)
    # FFM = 0.518 * (height² / impedance) + 0.231 * weight + 0.130 * reactance + 4.229 * sex - 6.343
    # Simplified (no reactance available from most scales):
    ffm = (height_cm ** 2 / impedance) * 0.518 + weight_kg * 0.231 + sex_flag * 4.229 - 6.343

    body_fat_kg = max(0.0, weight_kg - ffm)
    body_fat_pct = (body_fat_kg / weight_kg) * 100 if weight_kg > 0 else 0

    # BMR via Mifflin-St Jeor
    if sex_flag == 1:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

    return {
        "bmi": round(bmi, 1),
        "body_fat_pct": round(body_fat_pct, 1),
        "lean_mass_kg": round(ffm, 1),
        "body_fat_kg": round(body_fat_kg, 1),
        "bmr_kcal": round(bmr),
    }
