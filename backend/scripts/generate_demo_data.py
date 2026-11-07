"""
PayDesk - demo data generator.

Makes FAKE payroll data for one month so we can build and test PayDesk
without touching any real company data.

Run from the backend folder (with .venv active):
    python scripts/generate_demo_data.py

Output folder: paydesk/samples/generated/
    drivers.xlsx               - File 1: driver list (750 drivers, 50 stations)
    deliveries.csv             - File 2: one row per delivered order
    adjustments.xlsx           - File 3: deductions + bonuses
    vehicles.xlsx              - File 4: who drove which vehicle, when
    drivers_with_errors.xlsx   - File 1 with planted mistakes (for testing checks)
"""

import calendar
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------- settings
YEAR = 2026
MONTH = 10                      # October 2026
DRIVERS_PER_STATION = 15
SEED = 42                       # same seed = same data every time

random.seed(SEED)

OUT_DIR = Path(__file__).resolve().parents[2] / "samples" / "generated"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DAYS_IN_MONTH = calendar.monthrange(YEAR, MONTH)[1]
MONTH_START = date(YEAR, MONTH, 1)
MONTH_END = date(YEAR, MONTH, DAYS_IN_MONTH)

# ---------------------------------------------------------------- stations
# City -> (code, warehouse districts). Station name = "City - District".
CITIES = {
    "Riyadh": ("RUH", ["Azizia", "Al Arid", "Al Narjis", "Al Sulaimania", "Al Malaz",
                       "Al Olaya", "Al Naseem", "Al Suwaidi", "Al Shifa", "Al Rawdah",
                       "Al Yasmin", "Al Hamra"]),
    "Jeddah": ("JED", ["Al Safa", "Al Rawdah", "Al Hamdaniyah", "Al Balad",
                       "Al Naeem", "Al Marwah", "Al Samer", "Obhur"]),
    "Dammam": ("DMM", ["Al Faisaliyah", "Al Shatea", "Al Badiyah", "Al Nakheel"]),
    "Makkah": ("MKH", ["Al Awali", "Azizia", "Al Shoqiyah"]),
    "Madinah": ("MED", ["Quba", "Azizia", "Al Iskan"]),
    "Khobar": ("KHB", ["Al Aqrabiyah", "Al Thuqbah"]),
    "Taif": ("TIF", ["Al Hawiyah", "Al Shuhada"]),
    "Tabuk": ("TUU", ["Al Muruj", "Al Faisaliyah"]),
    "Abha": ("AHB", ["Al Khalidiyah", "Al Mansak"]),
    "Buraidah": ("BUR", ["Al Iskan", "Al Rayyan"]),
    "Hail": ("HAS", ["Al Nuqrah", "Al Muntazah"]),
    "Jazan": ("GIZ", ["Al Rawdah", "Al Safa"]),
    "Al Ahsa": ("HOF", ["Al Mubarraz", "Al Hofuf"]),
    "Jubail": ("JUB", ["Industrial City", "Al Fanateer"]),
    "Yanbu": ("YNB", ["Al Sumairi", "Al Nakheel"]),
}

stations = []
for city, (code, districts) in CITIES.items():
    for i, district in enumerate(districts):
        stations.append({
            "station_code": f"{code}-{i + 1:02d}",
            "city": city,
            "station": f"{city} - {district}",
        })
assert len(stations) == 50

# ---------------------------------------------------------------- names
FIRST = ["Muhammad", "Ahmed", "Ali", "Usman", "Bilal", "Hamza", "Imran",
         "Asif", "Tariq", "Faisal", "Rahul", "Arjun", "Vijay", "Suresh",
         "Rakib", "Sohel", "Karim", "Mahmoud", "Omar", "Khaled", "Youssef",
         "Abdullah", "Fahad", "Saad", "Nasser", "Zubair", "Kamran", "Adnan",
         "Shahid", "Rizwan", "Anil", "Ravi", "Jamal", "Hassan", "Ibrahim"]
LAST = ["Khan", "Hussain", "Malik", "Chaudhry", "Butt", "Qureshi", "Sharma",
        "Nair", "Reddy", "Kumar", "Rahman", "Islam", "Hossain", "Mostafa",
        "Hassan", "Saleh", "Al-Harbi", "Al-Qahtani", "Al-Otaibi", "Siddiqui",
        "Iqbal", "Raza", "Akhtar", "Ansari", "Mirza", "Farooq", "Abbasi"]

PLATE_LETTERS = list("ABJDRSXTEGKLZNHUV")


def fake_iqama() -> str:
    return "2" + "".join(random.choices("0123456789", k=9))


def fake_phone() -> str:
    return "05" + "".join(random.choices("0123456789", k=8))


def fake_iban() -> str:
    """Saudi-style IBAN with a valid checksum. Bank code 45 = SAB style."""
    bban = "45" + "".join(random.choices("0123456789", k=18))
    # IBAN check digits: move 'SA00' to the end, letters -> numbers (S=28, A=10)
    check = 98 - int(bban + "281000") % 97
    return f"SA{check:02d}{bban}"


def fake_plate(used: set) -> str:
    while True:
        plate = (
            "".join(random.choices("0123456789", k=4))
            + " "
            + "".join(random.choices(PLATE_LETTERS, k=3))
        )
        if plate not in used:
            used.add(plate)
            return plate


def random_day(start: date, end: date) -> date:
    return start + timedelta(days=random.randint(0, (end - start).days))


# ---------------------------------------------------------------- File 1: drivers
drivers = []
driver_no = 10001
for st in stations:
    for _ in range(DRIVERS_PER_STATION):
        driver_id = f"D{driver_no}"
        driver_no += 1

        # Most drivers joined before this month
        joining = random_day(date(2023, 1, 1), MONTH_START - timedelta(days=1))
        leaving = None
        r = random.random()
        if r < 0.05:                      # ~5% join mid-month
            joining = random_day(MONTH_START + timedelta(days=1), MONTH_END - timedelta(days=3))
        elif r < 0.08:                    # ~3% leave mid-month
            leaving = random_day(MONTH_START + timedelta(days=3), MONTH_END - timedelta(days=1))

        payment = "Bank" if random.random() < 0.6 else "Cash"
        drivers.append({
            "driver_id": driver_id,
            "name": f"{random.choice(FIRST)} {random.choice(LAST)}",
            "iqama_no": fake_iqama(),
            "city": st["city"],
            "station": st["station"],
            "station_code": st["station_code"],
            "joining_date": joining,
            "leaving_date": leaving,
            "payment_method": payment,
            "iban": fake_iban() if payment == "Bank" else None,
            "phone": fake_phone(),
        })

drivers_df = pd.DataFrame(drivers)


def active_range(d: dict) -> tuple[date, date]:
    start = max(d["joining_date"], MONTH_START)
    end = d["leaving_date"] or MONTH_END
    return start, end


# ---------------------------------------------------------------- File 4: vehicles
used_plates: set = set()
vehicles = []
driver_plates: dict[str, list[tuple[str, date, date]]] = {}

for d in drivers:
    start, end = active_range(d)
    plate = fake_plate(used_plates)
    # ~3% of drivers switch vehicle mid-month (tests date matching for fines)
    if random.random() < 0.03 and (end - start).days > 10:
        switch = start + timedelta(days=random.randint(5, (end - start).days - 3))
        plate2 = fake_plate(used_plates)
        periods = [(plate, start, switch - timedelta(days=1)), (plate2, switch, end)]
    else:
        periods = [(plate, start, end)]
    driver_plates[d["driver_id"]] = periods
    for p, f, t in periods:
        vehicles.append({"plate_no": p, "driver_id": d["driver_id"], "from_date": f, "to_date": t})

vehicles_df = pd.DataFrame(vehicles)

# ---------------------------------------------------------------- File 2: deliveries
tracking_counter = 5_000_000_000
delivery_rows = []
driver_trackings: dict[str, list[str]] = {}

for d in drivers:
    start, end = active_range(d)
    skill = random.uniform(10, 22)            # average deliveries per working day
    cod_share = random.uniform(0.3, 0.5)
    trackings = []
    day = start
    while day <= end:
        if random.random() > 0.15:            # ~15% days off
            for _ in range(max(0, int(random.gauss(skill, 4)))):
                tracking_counter += 1
                tn = f"SA{tracking_counter}"
                trackings.append(tn)
                delivery_rows.append((
                    d["driver_id"], day.isoformat(), tn,
                    "COD" if random.random() < cod_share else "Prepaid",
                ))
        day += timedelta(days=1)
    driver_trackings[d["driver_id"]] = trackings

deliveries_df = pd.DataFrame(delivery_rows, columns=["driver_id", "date", "tracking_no", "order_type"])

# ---------------------------------------------------------------- File 3: adjustments
adjustments = []
active_ids = [d["driver_id"] for d in drivers]
by_id = {d["driver_id"]: d for d in drivers}


def add(driver_id, plate_no, kind, typ, amount, day, reference, note=""):
    adjustments.append({
        "driver_id": driver_id, "plate_no": plate_no, "kind": kind, "type": typ,
        "amount": amount, "date": day, "reference": reference, "note": note,
    })


# Traffic fines: plate number only - PayDesk must find the driver (File 4)
for i in range(120):
    did = random.choice(active_ids)
    plate, f, t = random.choice(driver_plates[did])
    add(None, plate, "Deduction", "Traffic fine", random.choice([100, 150, 300, 500, 1000]),
        random_day(f, t), f"TF-{8100000 + i}", "Speeding" if i % 3 else "Red light")

# Lost parcels: tracking number from that driver's own deliveries
for i in range(60):
    did = random.choice(active_ids)
    if not driver_trackings[did]:
        continue
    add(did, None, "Deduction", "Lost parcel", random.choice([50, 80, 120, 150, 250, 400]),
        random_day(*active_range(by_id[did])), random.choice(driver_trackings[did]))

# COD shortage
for i in range(40):
    did = random.choice(active_ids)
    add(did, None, "Deduction", "Shortage", random.randint(2, 50) * 10,
        random_day(*active_range(by_id[did])), f"SHT-{2000 + i}", "COD cash short at handover")

# Advances
for i in range(100):
    did = random.choice(active_ids)
    add(did, None, "Deduction", "Advance", random.choice([200, 300, 500]),
        random_day(*active_range(by_id[did])), f"ADV-{3000 + i}")

# Other (note is required)
OTHER_NOTES = ["Uniform not returned", "Damaged phone holder", "Lost delivery bag",
               "Fuel card misuse", "Vehicle damage - minor"]
for i in range(20):
    did = random.choice(active_ids)
    add(did, None, "Deduction", "Other", random.choice([50, 100, 150, 200]),
        random_day(*active_range(by_id[did])), f"OTH-{4000 + i}", random.choice(OTHER_NOTES))

# Bonuses
for i in range(30):
    did = random.choice(active_ids)
    add(did, None, "Bonus", "Bonus", random.choice([100, 150, 200, 300]),
        MONTH_END, f"BON-{5000 + i}", random.choice(["Top performer", "Perfect attendance"]))

# Two big cases: deductions bigger than 50% of salary (tests the cap + carry-over)
for did in random.sample(active_ids, 2):
    add(did, None, "Deduction", "Lost parcel", 2500,
        random_day(*active_range(by_id[did])),
        random.choice(driver_trackings[did]) if driver_trackings[did] else "SA0000000000",
        "High-value electronics parcel")

adjustments_df = pd.DataFrame(adjustments).sort_values(["date", "type"]).reset_index(drop=True)

# ---------------------------------------------------------------- errors version of File 1
errors_df = drivers_df.copy()
errors_df = pd.concat([errors_df, errors_df.iloc[[5]]], ignore_index=True)   # duplicate driver ID
bank_rows = errors_df.index[errors_df["payment_method"] == "Bank"]
errors_df.loc[bank_rows[0], "iban"] = None                                    # bank driver, no IBAN
errors_df.loc[10, "station"] = None                                           # missing station
errors_df.loc[20, "joining_date"] = None                                      # missing joining date
errors_df.loc[30, "payment_method"] = "Cheque"                                # unknown payment method

# ---------------------------------------------------------------- save
drivers_df.to_excel(OUT_DIR / "drivers.xlsx", index=False)
deliveries_df.to_csv(OUT_DIR / "deliveries.csv", index=False)
adjustments_df.to_excel(OUT_DIR / "adjustments.xlsx", index=False)
vehicles_df.to_excel(OUT_DIR / "vehicles.xlsx", index=False)
errors_df.to_excel(OUT_DIR / "drivers_with_errors.xlsx", index=False)

print(f"Month: {calendar.month_name[MONTH]} {YEAR}")
print(f"Stations:     {len(stations)}")
print(f"Drivers:      {len(drivers_df)}  (cash {sum(drivers_df.payment_method == 'Cash')}, "
      f"bank {sum(drivers_df.payment_method == 'Bank')})")
print(f"Deliveries:   {len(deliveries_df):,}")
print(f"Adjustments:  {len(adjustments_df)}")
print(f"Vehicles:     {len(vehicles_df)}")
print(f"Saved to:     {OUT_DIR}")
