from typing import List, Optional
from collections import defaultdict

def get_highest_salary_employees(rows: List[dict]):
    def get_salary(row):
        val = row.get("salary") or ""
        clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
        try:
            return float(clean) if clean else 0.0
        except ValueError:
            return 0.0

    sorted_rows = sorted(rows, key=get_salary, reverse=True)
    return sorted_rows[:5]

def get_employees_above_salary(rows: List[dict], threshold: float = 100000.0):
    def get_salary(row):
        val = row.get("salary") or ""
        clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
        try:
            return float(clean) if clean else 0.0
        except ValueError:
            return 0.0

    return [row for row in rows if get_salary(row) > threshold]

def get_employee_salary_hike(rows: List[dict], employee_id: str):
    employee = next((row for row in rows if row.get("employee_id") == employee_id), None)
    if not employee:
        return None

    def get_val(val):
        clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
        try:
            return float(clean) if clean else 0.0
        except ValueError:
            return 0.0

    current = get_val(employee.get("salary"))
    previous = get_val(employee.get("previous_salary")) or current

    increase = current - previous
    percentage = (increase / previous * 100) if previous > 0 else 0

    return {
        "employee": employee,
        "currentSalary": current,
        "previousSalary": previous,
        "increase": increase,
        "percentage": percentage
    }

def get_recent_joinees(rows: List[dict]):
    # Note: simplistic implementation without date parsing, assuming frontend logic for now
    # Since we lack complex date parsing here, we return a mock subset or use basic string matching
    # Better implementation would parse date_of_joining
    import datetime
    
    recent = []
    six_months_ago = datetime.datetime.now() - datetime.timedelta(days=180)
    
    for row in rows:
        doj = row.get("date_of_joining")
        if not doj:
            continue
        try:
            # try parsing basic dates
            dt = datetime.datetime.strptime(doj, "%Y-%m-%d")
            if dt > six_months_ago:
                recent.append(row)
        except Exception:
            # fallback
            pass
    return recent

def get_largest_department(rows: List[dict]):
    counts = defaultdict(int)
    for row in rows:
        dept = row.get("department")
        if dept:
            counts[dept] += 1
            
    if not counts:
        return None
        
    largest = max(counts.items(), key=lambda x: x[1])
    return {"department": largest[0], "count": largest[1]}

def get_inactive_employees(rows: List[dict]):
    return [row for row in rows if str(row.get("status", "")).lower() in ["inactive", "terminated", "resigned"]]

def get_department_counts(rows: List[dict]):
    counts = defaultdict(int)
    for row in rows:
        dept = row.get("department")
        if dept:
            counts[dept] += 1
    return [{"department": k, "count": v} for k, v in counts.items()]

def get_contract_employees(rows: List[dict]):
    return [row for row in rows if str(row.get("employment_type", "")).lower() == "contract"]

# Vendor Logic

def get_highest_value_vendors(rows: List[dict]):
    def get_val(val):
        clean = "".join(c for c in str(val) if c.isdigit() or c == '.')
        try:
            return float(clean) if clean else 0.0
        except ValueError:
            return 0.0

    sorted_rows = sorted(rows, key=lambda r: get_val(r.get("contract_value")), reverse=True)
    return sorted_rows[:5]

def get_recurring_vendors(rows: List[dict]):
    filtered = [row for row in rows if (str(row.get("recurring", "")).lower() in ["yes", "true"])]
    return filtered

def get_industry_counts(rows: List[dict]):
    counts = defaultdict(int)
    for row in rows:
        ind = row.get("industry")
        if ind:
            counts[ind] += 1
    return [{"industry": k, "count": v} for k, v in counts.items()]

def get_largest_industry(rows: List[dict]):
    counts = defaultdict(int)
    for row in rows:
        ind = row.get("industry")
        if ind:
            counts[ind] += 1
            
    if not counts:
        return None
        
    largest = max(counts.items(), key=lambda x: x[1])
    return {"industry": largest[0], "count": largest[1]}

def get_active_vendors(rows: List[dict]):
    filtered = [row for row in rows if (str(row.get("status", "")).lower() == "active")]
    return filtered
