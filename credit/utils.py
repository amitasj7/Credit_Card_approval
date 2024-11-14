import datetime

from django.db.models import QuerySet
import numpy_financial as npf

from credit.models import Customer, Loan


def calculate_credit_score(loans: Loan, customer: Customer) -> int:
    current_year = datetime.datetime.now().year
    number_of_past_loans = loans.count()
    loan_activity_current_year = 0
    loan_approved_volume = 0
    total_emis_paid_on_time = 0
    total_emis_tenure = 0
    current_loans_sum = sum(loan.loan_amount for loan in loans if loan.start_date.year == current_year)

    if number_of_past_loans > 0:
        max_loan_amount = max(loan.loan_amount for loan in loans)
    else:
        max_loan_amount = 1  # Avoid division by zero by setting a default value

    for loan in loans:
        total_emis_paid_on_time += loan.emis_paid_on_time
        total_emis_tenure += loan.tenure
        if loan.start_date.year == current_year:
            loan_activity_current_year += 1
        loan_approved_volume = 1.8

    past_loans_paid_on_time_ratio = (total_emis_paid_on_time / total_emis_tenure) if total_emis_tenure else 0

    # Initial credit score calculation
    credit_score = (past_loans_paid_on_time_ratio * 25 + 
                    number_of_past_loans * 25 + 
                    loan_activity_current_year * 25 + 
                    loan_approved_volume * 25)

    return min(credit_score, 100)  # Ensure credit score does not exceed 100


def check_eligibility(credit_score: float, interest_rate: float, customer: Customer, loans: QuerySet):
    monthly_salary = customer.monthly_salary
    total_emi = sum(loan.monthly_repayment for loan in loans if loan.end_date > datetime.date.today())
    
    if total_emi > monthly_salary * 0.5:
        return False, interest_rate  # No loan approval if EMIs exceed 50% of monthly salary

    approval = False
    corrected_interest_rate = interest_rate
    
    if credit_score > 50:
        approval = True
    elif 50 >= credit_score > 30:
        approval = True
        corrected_interest_rate = max(interest_rate, 12)
    elif 30 >= credit_score > 10:
        approval = True
        corrected_interest_rate = max(interest_rate, 16)
    elif credit_score <= 10:
        approval = False  # Do not approve any loans

    # Correct the interest rate in the response based on the credit score
    if corrected_interest_rate != interest_rate:
        interest_rate = corrected_interest_rate
    
    return approval, interest_rate


def calculate_remaining_loan_balance(loan):
    monthly_interest_rate = loan.interest_rate / 12 / 100

    # Calculate the number of payments already made
    payments_made = loan.emis_paid_on_time

    # The remaining balance is the future value of the remaining payments
    remaining_balance = npf.fv(rate=monthly_interest_rate, nper=loan.tenure - payments_made,
                               pmt=-loan.monthly_repayment,
                               pv=loan.loan_amount, when='end')

    return abs(remaining_balance)