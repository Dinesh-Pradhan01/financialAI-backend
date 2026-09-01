from fastapi import APIRouter, Depends, Body
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from app.utils.response import success_response, error_response
from app.services.chatbot_service import (
    get_highest_salary_employees,
    get_employees_above_salary,
    get_employee_salary_hike,
    get_recent_joinees,
    get_largest_department,
    get_inactive_employees,
    get_department_counts,
    get_contract_employees,
    
    get_highest_value_vendors,
    get_recurring_vendors,
    get_industry_counts,
    get_largest_industry,
    get_active_vendors
)

router = APIRouter()

class EmployeeChatRequest(BaseModel):
    questionId: str
    rows: List[Dict[str, Any]]
    employeeId: Optional[str] = None

class VendorChatRequest(BaseModel):
    question_id: str
    rows: List[Dict[str, Any]]

@router.post("/employee")
async def process_employee_chatbot(request: EmployeeChatRequest):
    question_id = request.questionId
    rows = request.rows
    
    if question_id == "highest_salary":
        employees = get_highest_salary_employees(rows)
        return success_response(
            message="Top Highest Paid Employees",
            data={
                "kind": "employees",
                "title": "Top Highest Paid Employees",
                "summary": "Showing the top 5 employees by current salary." if employees else "No salary data was found.",
                "employees": employees
            }
        )
    elif question_id == "above_salary":
        employees = get_employees_above_salary(rows)
        return success_response(
            message="Employees Earning Above INR 100,000",
            data={
                "kind": "employees",
                "title": "Employees Earning Above INR 100,000",
                "summary": f"{len(employees)} employees match this salary threshold." if employees else "No employees matched.",
                "employees": employees
            }
        )
    elif question_id == "salary_hike":
        if not request.employeeId:
            return success_response(
                message="Select an Employee",
                data={
                    "kind": "employeeSelection",
                    "title": "Select an Employee",
                    "summary": "Choose an employee to calculate current salary, previous salary, increase, and hike percentage."
                }
            )
        result = get_employee_salary_hike(rows, request.employeeId)
        return success_response(
            message="Salary Hike",
            data={
                "kind": "salaryHike",
                "title": f"{result['employee'].get('employee_name', 'Employee')} Salary Hike" if result else "Salary Hike",
                "summary": "Salary movement calculated from uploaded employee data." if result else "Employee not found.",
                "result": result
            }
        )
    elif question_id == "recent_joiners":
        employees = get_recent_joinees(rows)
        return success_response(
            message="Joined in the Last 6 Months",
            data={
                "kind": "employees",
                "title": "Joined in the Last 6 Months",
                "summary": f"{len(employees)} recent joiners found." if employees else "No recent joiners found.",
                "employees": employees
            }
        )
    elif question_id == "largest_department":
        department = get_largest_department(rows)
        return success_response(
            message="Largest Department",
            data={
                "kind": "largestDepartment",
                "title": "Largest Department",
                "summary": f"{department['department']} has the most employees." if department else "No department data was found.",
                "department": department
            }
        )
    elif question_id == "inactive_employees":
        employees = get_inactive_employees(rows)
        return success_response(
            message="Inactive Employees",
            data={
                "kind": "employees",
                "title": "Inactive Employees",
                "summary": f"{len(employees)} inactive employees found." if employees else "No inactive employees found.",
                "employees": employees
            }
        )
    elif question_id == "department_distribution":
        departments = get_department_counts(rows)
        return success_response(
            message="Department Distribution",
            data={
                "kind": "departments",
                "title": "Department Distribution",
                "summary": "Employees grouped by department." if departments else "No department data was found.",
                "departments": departments
            }
        )
    elif question_id == "contract_employees":
        employees = get_contract_employees(rows)
        return success_response(
            message="Contract Employees",
            data={
                "kind": "employees",
                "title": "Contract Employees",
                "summary": f"{len(employees)} contract employees found." if employees else "No contract employees found.",
                "employees": employees
            }
        )
        
    return error_response("Unknown question ID", status_code=400)


@router.post("/vendor")
async def process_vendor_chatbot(request: VendorChatRequest):
    question_id = request.question_id
    rows = request.rows
    
    if question_id == "highest_value":
        vendors = get_highest_value_vendors(rows)
        return success_response(
            message="Top High-Value Vendors",
            data={
                "kind": "vendors",
                "title": "Top High-Value Vendors",
                "summary": "Showing the top 5 vendors by contract value." if vendors else "No contract value data was found.",
                "vendors": vendors
            }
        )
    elif question_id == "recurring":
        vendors = get_recurring_vendors(rows)
        return success_response(
            message="Recurring Vendors",
            data={
                "kind": "vendors",
                "title": "Recurring Vendors",
                "summary": f"{len(vendors)} recurring contracts found." if vendors else "No recurring contracts found.",
                "vendors": vendors
            }
        )
    elif question_id == "industries":
        industries = get_industry_counts(rows)
        return success_response(
            message="Vendors by Industry",
            data={
                "kind": "industries",
                "title": "Vendors by Industry",
                "summary": "Vendors grouped by industry." if industries else "No industry data was found.",
                "industries": industries
            }
        )
    elif question_id == "largest_industry":
        industry = get_largest_industry(rows)
        return success_response(
            message="Largest Vendor Industry",
            data={
                "kind": "largest_industry",
                "title": "Largest Vendor Industry",
                "summary": f"{industry['industry']} has the most vendors." if industry else "No industry data was found.",
                "industry": industry
            }
        )
    elif question_id == "active_vendors":
        vendors = get_active_vendors(rows)
        return success_response(
            message="Active Vendors",
            data={
                "kind": "vendors",
                "title": "Active Vendors",
                "summary": f"{len(vendors)} active vendors found." if vendors else "No active vendors found.",
                "vendors": vendors
            }
        )
        
    return error_response("Unknown question ID", status_code=400)
