"""
Body composition estimates from weight + BIA impedance.

Formula: Segal et al. 1988 (validated for whole-body and consumer foot-to-foot BIA).
Chosen over Kyle 2001 which was calibrated for clinical whole-body BIA and
significantly overestimates body fat on consumer foot-to-foot scales (Renpho ES-26).

Accuracy: ±3-5% for general population.
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

    # Fat-free mass via Segal et al. 1988
    # Males:   FFM = 0.00066360 * H² - 0.02117 * Z + 0.62854 * weight - 0.12380 * age + 9.33285
    # Females: FFM = 0.00091186 * H² - 0.01466 * Z + 0.29990 * weight - 0.07012 * age + 9.37938
    if sex_flag == 1:
        ffm = 0.00066360 * height_cm**2 - 0.02117 * impedance + 0.62854 * weight_kg - 0.12380 * age + 9.33285
    else:
        ffm = 0.00091186 * height_cm**2 - 0.01466 * impedance + 0.29990 * weight_kg - 0.07012 * age + 9.37938

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
