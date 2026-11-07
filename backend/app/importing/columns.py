"""Smart column matching.

Real files never have the exact column names we expect ("Driver No", "DOJ",
"Mobile Number"...). This finds which column is which, so the accountant can
upload the company's own export without renaming anything.
"""

import difflib
import re

# What each file needs. Deliveries can come in two layouts.
FILE_FIELDS: dict[str, dict[str, list[str]]] = {
    "drivers": {
        "required": ["driver_id", "name", "station_code", "joining_date", "payment_method"],
        "optional": ["station", "city", "iqama_no", "leaving_date", "iban", "phone"],
    },
    "vehicles": {
        "required": ["plate_no", "driver_id", "from_date", "to_date"],
        "optional": [],
    },
    "deliveries_orders": {
        "required": ["driver_id", "date", "order_type"],
        "optional": ["tracking_no"],
    },
    "deliveries_totals": {
        "required": ["driver_id", "prepaid", "cod"],
        "optional": [],
    },
    "adjustments": {
        "required": ["type", "amount"],
        "optional": ["driver_id", "plate_no", "kind", "date", "reference", "note"],
    },
}

# Other names the same column often has in real exports
SYNONYMS: dict[str, list[str]] = {
    "driver_id": ["driver id", "driver no", "driver number", "driver code", "emp id",
                  "employee id", "employee no", "courier id", "rider id", "staff id"],
    "name": ["driver name", "full name", "employee name", "courier name"],
    "station_code": ["station code", "hub code", "branch code", "warehouse code", "station id"],
    "station": ["station name", "hub", "hub name", "warehouse", "branch"],
    "city": ["city name", "region"],
    "iqama_no": ["iqama", "iqama number", "id number", "national id"],
    "joining_date": ["join date", "joined", "date of joining", "doj", "start date", "hire date"],
    "leaving_date": ["leave date", "exit date", "last working day", "end date", "resign date"],
    "payment_method": ["payment", "pay method", "payment type", "salary method", "salary payment"],
    "iban": ["iban no", "iban number", "bank account", "account iban", "bank iban"],
    "phone": ["mobile", "phone number", "mobile number", "mobile no", "contact"],
    "plate_no": ["plate", "plate number", "vehicle", "vehicle no", "vehicle plate", "car plate"],
    "from_date": ["from", "start date", "assigned from", "valid from"],
    "to_date": ["to", "end date", "assigned to", "valid to", "until"],
    "date": ["delivery date", "day", "order date", "delivered date", "delivered at"],
    "tracking_no": ["tracking", "tracking number", "awb", "awb no", "waybill", "shipment no", "order id"],
    "order_type": ["type", "payment type", "cod prepaid", "order payment", "payment mode"],
    "prepaid": ["prepaid count", "prepaid orders", "prepaid deliveries", "total prepaid"],
    "cod": ["cod count", "cod orders", "cod deliveries", "total cod"],
    "kind": ["deduction or bonus", "entry kind"],
    "type": ["deduction type", "category", "adjustment type", "reason"],
    "amount": ["value", "sar", "amount sar", "total"],
    "reference": ["ref", "reference no", "fine number", "fine no", "ref no"],
    "note": ["notes", "remarks", "comment", "comments", "description"],
}


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def match_columns(headers: list[str], layout: str) -> tuple[dict[str, str], list[str]]:
    """Returns ({original header: our field}, [missing required fields])."""
    spec = FILE_FIELDS[layout]
    fields = spec["required"] + spec["optional"]
    normalized = {h: norm(h) for h in headers}
    mapping: dict[str, str] = {}
    used: set[str] = set()

    def names_for(field: str) -> list[str]:
        return [norm(field)] + [norm(s) for s in SYNONYMS.get(field, [])]

    # Pass 1: exact name or known synonym
    for field in fields:
        for header, n in normalized.items():
            if header not in used and n in names_for(field):
                mapping[header] = field
                used.add(header)
                break

    # Pass 2: close spelling ("Joinning Date", "Paymnet Method")
    for field in fields:
        if field in mapping.values():
            continue
        free = {n: h for h, n in normalized.items() if h not in used}
        close = difflib.get_close_matches(norm(field), list(free), n=1, cutoff=0.85)
        if not close:
            for alt in names_for(field)[1:]:
                close = difflib.get_close_matches(alt, list(free), n=1, cutoff=0.88)
                if close:
                    break
        if close:
            header = free[close[0]]
            mapping[header] = field
            used.add(header)

    missing = [f for f in spec["required"] if f not in mapping.values()]
    return mapping, missing
