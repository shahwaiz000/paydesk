"""
PayDesk - demo data generator.

Makes FAKE payroll data for one month so we can build and test PayDesk
without touching any real company data.

Run from the backend folder (with .venv active):
    python scripts/generate_demo_data.py

Output folder: paydesk/samples/generated/  (current month)
              paydesk/samples/generated/2026-09/  (previous month, for comparisons)
    drivers.xlsx               - File 1: driver list (750 drivers, 50 stations)
    deliveries.csv             - File 2: one row per delivered order
    adjustments.xlsx           - File 3: deductions + bonuses
    vehicles.xlsx              - File 4: who drove which vehicle, when
    drivers_with_errors.xlsx   - File 1 with planted mistakes (for testing checks)
    adjustments_with_errors.xlsx - File 3 with planted mistakes
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


# Things that stay the same for a driver every month
driver_skill = {d["driver_id"]: random.uniform(10, 22) for d in drivers}       # deliveries per day
driver_cod_share = {d["driver_id"]: random.uniform(0.3, 0.5) for d in drivers}
used_plates: set = set()
driver_main_plate = {d["driver_id"]: fake_plate(used_plates) for d in drivers}
tracking_counter = 5_000_000_000
OTHER_NOTES = ["Uniform not returned", "Damaged phone holder", "Lost delivery bag",
               "Fuel card misuse", "Vehicle damage - minor"]


def generate_month(year: int, month: int, big_cases: list[str]):
    """Vehicles, deliveries and adjustments for one month."""
    global tracking_counter
    m_start = date(year, month, 1)
    m_end = date(year, month, calendar.monthrange(year, month)[1])

    def active_range(d: dict):
        start = max(d["joining_date"], m_start)
        end = min(d["leaving_date"] or m_end, m_end)
        return (start, end) if start <= end else None

    active = [d for d in drivers if active_range(d)]
    by_id = {d["driver_id"]: d for d in active}

    # File 4: vehicles - ~3% switch vehicle mid-month (tests date matching for fines)
    vehicles, driver_plates = [], {}
    for d in active:
        start, end = active_range(d)
        plate = driver_main_plate[d["driver_id"]]
        if random.random() < 0.03 and (end - start).days > 10:
            switch = start + timedelta(days=random.randint(5, (end - start).days - 3))
            periods = [(plate, start, switch - timedelta(days=1)), (fake_plate(used_plates), switch, end)]
        else:
            periods = [(plate, start, end)]
        driver_plates[d["driver_id"]] = periods
        for p, f, t in periods:
            vehicles.append({"plate_no": p, "driver_id": d["driver_id"], "from_date": f, "to_date": t})

    # File 2: deliveries - each month a driver is a bit better or worse,
    # and ~6% are absent for a week (gives "unusual change" cases to review)
    rows, trackings = [], {}
    for d in active:
        did = d["driver_id"]
        start, end = active_range(d)
        skill = driver_skill[did] * random.gauss(1, 0.12)
        absent = set()
        if random.random() < 0.06 and (end - start).days > 14:
            a = start + timedelta(days=random.randint(0, (end - start).days - 10))
            absent = {a + timedelta(days=i) for i in range(random.randint(7, 10))}
        trackings[did] = []
        day = start
        while day <= end:
            if day not in absent and random.random() > 0.15:      # ~15% days off
                for _ in range(max(0, int(random.gauss(skill, 4)))):
                    tracking_counter += 1
                    tn = f"SA{tracking_counter}"
                    trackings[did].append(tn)
                    rows.append((did, day.isoformat(), tn,
                                 "COD" if random.random() < driver_cod_share[did] else "Prepaid"))
            day += timedelta(days=1)
    deliveries = pd.DataFrame(rows, columns=["driver_id", "date", "tracking_no", "order_type"])

    # File 3: adjustments
    adj = []
    ids = list(by_id)

    def add(driver_id, plate_no, kind, typ, amount, day, reference, note=""):
        adj.append({"driver_id": driver_id, "plate_no": plate_no, "kind": kind, "type": typ,
                    "amount": amount, "date": day, "reference": reference, "note": note})

    tag = f"{month:02d}"
    for i in range(120):   # traffic fines: plate only - PayDesk finds the driver
        did = random.choice(ids)
        plate, f, t = random.choice(driver_plates[did])
        add(None, plate, "Deduction", "Traffic fine", random.choice([100, 150, 300, 500, 1000]),
            random_day(f, t), f"TF-{tag}{81000 + i}", "Speeding" if i % 3 else "Red light")
    for i in range(60):    # lost parcels: tracking number from the driver's own deliveries
        did = random.choice(ids)
        if trackings[did]:
            add(did, None, "Deduction", "Lost parcel", random.choice([50, 80, 120, 150, 250, 400]),
                random_day(*active_range(by_id[did])), random.choice(trackings[did]))
    for i in range(40):
        did = random.choice(ids)
        add(did, None, "Deduction", "Shortage", random.randint(2, 50) * 10,
            random_day(*active_range(by_id[did])), f"SHT-{tag}{2000 + i}", "COD cash short at handover")
    for i in range(100):
        did = random.choice(ids)
        add(did, None, "Deduction", "Advance", random.choice([200, 300, 500]),
            random_day(*active_range(by_id[did])), f"ADV-{tag}{3000 + i}")
    for i in range(20):
        did = random.choice(ids)
        add(did, None, "Deduction", "Other", random.choice([50, 100, 150, 200]),
            random_day(*active_range(by_id[did])), f"OTH-{tag}{4000 + i}", random.choice(OTHER_NOTES))
    for i in range(30):
        did = random.choice(ids)
        add(did, None, "Bonus", "Bonus", random.choice([100, 150, 200, 300]),
            m_end, f"BON-{tag}{5000 + i}", random.choice(["Top performer", "Perfect attendance"]))
    # Big cases: more than 50% of salary -> capped, the rest carried to next month
    for did in big_cases:
        if did in by_id and trackings[did]:
            add(did, None, "Deduction", "Lost parcel", 2500, random_day(*active_range(by_id[did])),
                random.choice(trackings[did]), "High-value electronics parcel")

    adjustments = pd.DataFrame(adj).sort_values(["date", "type"]).reset_index(drop=True)
    return pd.DataFrame(vehicles), deliveries, adjustments


# Drivers who are active in both months (big cases carry over from Sep into Oct)
full_both = [d["driver_id"] for d in drivers if d["joining_date"] < date(YEAR, MONTH - 1, 1) and not d["leaving_date"]]
big_sep, big_oct = random.sample(full_both, 3), random.sample(full_both, 2)

PREV_YEAR, PREV_MONTH = (YEAR, MONTH - 1) if MONTH > 1 else (YEAR - 1, 12)
sep_vehicles, sep_deliveries, sep_adjustments = generate_month(PREV_YEAR, PREV_MONTH, big_sep)
vehicles_df, deliveries_df, adjustments_df = generate_month(YEAR, MONTH, big_oct)

# ---------------------------------------------------------------- errors versions (current month)
errors_df = drivers_df.copy()
errors_df = pd.concat([errors_df, errors_df.iloc[[5]]], ignore_index=True)   # duplicate driver ID
bank_rows = errors_df.index[errors_df["payment_method"] == "Bank"]
errors_df.loc[bank_rows[0], "iban"] = None                                    # bank driver, no IBAN
errors_df.loc[10, "station"] = None                                           # missing station
errors_df.loc[20, "joining_date"] = None                                      # missing joining date
errors_df.loc[30, "payment_method"] = "Cheque"                                # unknown payment method
errors_df.loc[40, "payment_method"] = "Csah"                                  # typo -> PayDesk suggests Cash
errors_df.loc[50, "joining_date"] = "31/02/2026"                              # impossible date

adj_err = adjustments_df.copy()
first_driver_row = adj_err.index[adj_err["driver_id"].notna()][0]
good_id = adj_err.loc[first_driver_row, "driver_id"]
adj_err.loc[first_driver_row, "driver_id"] = good_id[1:]           # "D" missing -> PayDesk suggests it
adj_err.loc[adj_err.index[adj_err["type"] == "Traffic fine"][:3], "type"] = "Trafic fine"  # typo
adj_err.loc[adj_err.index[adj_err["type"] == "Other"][0], "note"] = None                  # Other without note
adj_err.loc[adj_err.index[adj_err["type"] == "Advance"][0], "amount"] = -300               # negative amount

# ---------------------------------------------------------------- save
# Current month (October) in the main folder, previous month (September) in a sub-folder
drivers_df.to_excel(OUT_DIR / "drivers.xlsx", index=False)
deliveries_df.to_csv(OUT_DIR / "deliveries.csv", index=False)
adjustments_df.to_excel(OUT_DIR / "adjustments.xlsx", index=False)
vehicles_df.to_excel(OUT_DIR / "vehicles.xlsx", index=False)
errors_df.to_excel(OUT_DIR / "drivers_with_errors.xlsx", index=False)
adj_err.to_excel(OUT_DIR / "adjustments_with_errors.xlsx", index=False)

PREV_DIR = OUT_DIR / f"{PREV_YEAR}-{PREV_MONTH:02d}"
PREV_DIR.mkdir(exist_ok=True)
drivers_df.to_excel(PREV_DIR / "drivers.xlsx", index=False)
sep_deliveries.to_csv(PREV_DIR / "deliveries.csv", index=False)
sep_adjustments.to_excel(PREV_DIR / "adjustments.xlsx", index=False)
sep_vehicles.to_excel(PREV_DIR / "vehicles.xlsx", index=False)

# ---------------------------------------------------------------- fake fine documents (for AI reading)
def make_fine_documents():
    """6 DEMO traffic fine notices: 4 match a driver, 1 unknown plate, 1 already in the deductions file."""
    from reportlab.lib.pagesizes import A5
    from reportlab.pdfgen import canvas

    fines_dir = OUT_DIR / "fines"
    fines_dir.mkdir(exist_ok=True)
    for old in fines_dir.glob("*"):
        old.unlink()

    picks = vehicles_df.sample(4, random_state=SEED)
    docs = []
    for i, v in enumerate(picks.itertuples(index=False)):
        day = random_day(v.from_date, v.to_date)
        plate = v.plate_no
        if i == 1:   # written differently on the notice: letters first, with a dash
            digits, letters = plate.split(" ")
            plate = f"{letters}-{digits}"
        docs.append((f"TV-{random.randint(40000000, 49999999)}", plate, day,
                     random.choice([150, 300, 500, 900]), random.choice(
                         ["Exceeding speed limit", "Running a red light", "Wrong parking", "Using mobile while driving"])))
    docs.append(("TV-40000001", "9999 ZZZ", date(YEAR, MONTH, 14), 300, "Wrong parking"))   # nobody has this plate
    first_fine = adjustments_df[adjustments_df["type"] == "Traffic fine"].iloc[0]           # already in File 3
    docs.append((first_fine["reference"], first_fine["plate_no"], first_fine["date"],
                 int(first_fine["amount"]), "Exceeding speed limit"))

    for n, (number, plate, day, amount, violation) in enumerate(docs, start=1):
        path = fines_dir / f"fine_{n}.pdf"
        c = canvas.Canvas(str(path), pagesize=A5)
        w, h = A5
        c.setFillColorRGB(0.85, 0.1, 0.1)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(w / 2, h - 30, "DEMO DOCUMENT - NOT A REAL FINE")
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(w / 2, h - 60, "Traffic Violation Notice")
        c.setFont("Helvetica", 9)
        c.drawCentredString(w / 2, h - 75, "PayDesk demo data - fictional traffic authority")
        rows = [("Violation No.", number), ("Vehicle plate", plate),
                ("Date of violation", day.strftime("%d/%m/%Y")), ("Time", f"{random.randint(7, 22):02d}:{random.randint(0, 59):02d}"),
                ("Location", random.choice(["King Fahd Rd", "Olaya St", "Prince Sultan St", "Ring Rd Exit 9"])),
                ("Violation", violation), ("Fine amount", f"SAR {amount:,.2f}")]
        y = h - 120
        for label, value in rows:
            c.setFont("Helvetica", 10)
            c.drawString(40, y, label)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(160, y, str(value))
            y -= 26
        c.setFont("Helvetica", 8)
        c.drawString(40, 40, "Payment due within 30 days. This is sample data for testing only.")
        c.save()

    # Turn the last-but-one notice into a phone-photo style PNG (AI reads images too)
    import pymupdf
    png_source = fines_dir / f"fine_{len(docs) - 2}.pdf"
    with pymupdf.open(png_source) as doc:
        doc[0].get_pixmap(dpi=110).save(str(fines_dir / f"fine_{len(docs) - 2}.png"))
    png_source.unlink()
    return len(docs)


fine_count = make_fine_documents()

print(f"Months:       {calendar.month_name[PREV_MONTH]} {PREV_YEAR} (sub-folder) + "
      f"{calendar.month_name[MONTH]} {YEAR} (main folder)")
print(f"Stations:     {len(stations)}")
print(f"Drivers:      {len(drivers_df)}  (cash {sum(drivers_df.payment_method == 'Cash')}, "
      f"bank {sum(drivers_df.payment_method == 'Bank')})")
print(f"Deliveries:   {len(sep_deliveries):,} (prev) / {len(deliveries_df):,} (current)")
print(f"Adjustments:  {len(sep_adjustments)} (prev) / {len(adjustments_df)} (current)")
print(f"Fine documents: {fine_count} (in the 'fines' folder)")
print(f"Saved to:     {OUT_DIR}")
