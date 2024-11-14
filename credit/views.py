from django.shortcuts import render
import datetime
from decimal import Decimal
import numpy_financial as npf
from dateutil.relativedelta import relativedelta
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from . import utils
from .serializers import *
from .models import Customer, Loan
import math, random
from .tasks import ingest_data
from .utils import calculate_remaining_loan_balance
from django.http import HttpResponse

# Create your views here.

class Home(APIView):
    def get(self, request):
        return HttpResponse("Welcome to the Credit Nest")

class FillDataView(APIView):
    def get(self, request):
        ingest_data.delay()
        return Response({
            "Data Filled": True
        })


class RegisterView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            approved_limit = math.ceil(data['monthly_income'] * 36 / 100000) * 100000
            customer_id = random.randint(10000, 99999)
            customer = Customer.objects.create(
                customer_id=customer_id,
                first_name=data['first_name'],
                last_name=data['last_name'],
                phone_number=data['phone_number'],
                age=data['age'],
                monthly_salary=data['monthly_income'],
                approved_limit=approved_limit,
            )
            return Response({
                'customer_id': customer.customer_id,
                'name': f"{customer.first_name} {customer.last_name}",
                'age': data['age'],
                'monthly_income': data['monthly_income'],
                'approved_limit': approved_limit,
                'phone_number': data['phone_number']
            })
        return Response(serializer.errors, status=400)


class CheckEligibilityView(APIView):
    def post(self, request):
        serializer = CheckEligibilityRequestSerializer(data=request.data)
        if serializer.is_valid():
            # Retrieve customer and loan data
            customer_id = serializer.validated_data['customer_id']
            customer = Customer.objects.get(customer_id=customer_id)
            loans = Loan.objects.filter(customer_id=customer_id)
            credit_score = utils.calculate_credit_score(loans=loans, customer=customer)

            loan_amount = serializer.validated_data['loan_amount']
            interest_rate = serializer.validated_data['interest_rate']
            tenure = serializer.validated_data['tenure']
            # Determine loan approval and interest rates
            approval, corrected_interest_rate = utils.check_eligibility(credit_score=credit_score,
                                                                        interest_rate=interest_rate, customer=customer,
                                                                        loans=loans)

            # Calculate monthly installment if approved
            if approval:
                monthly_installment = npf.pmt(rate=interest_rate / 12, nper=tenure, pv=-loan_amount)
            else:
                monthly_installment = 0

            response_data = {
                'customer_id': customer_id,
                'approval': approval,
                'interest_rate': interest_rate,
                'corrected_interest_rate': corrected_interest_rate,
                'tenure': tenure,
                'monthly_installment': monthly_installment
            }
            response_serializer = CheckEligibilityResponseSerializer(data=response_data)
            if response_serializer.is_valid():
                return Response(response_serializer.data)
            return Response(response_serializer.errors, status=400)
        return Response(serializer.errors, status=400)


class CreateLoanView(APIView):
    def post(self, request):
        serializer = CreateLoanRequestSerializer(data=request.data)
        if serializer.is_valid():
            customer_id = serializer.validated_data['customer_id']
            loan_amount = serializer.validated_data['loan_amount']
            interest_rate = serializer.validated_data['interest_rate']
            tenure = serializer.validated_data['tenure']

            customer = Customer.objects.get(customer_id=customer_id)
            loans = Loan.objects.filter(customer_id=customer_id)

            credit_score = utils.calculate_credit_score(loans=loans, customer=customer)

            loan_approved, corrected_interest_rate = utils.check_eligibility(credit_score=credit_score,
                                                                             interest_rate=interest_rate,
                                                                             customer=customer,
                                                                             loans=loans)
            message = 'Loan approved' if loan_approved else 'Loan not approved'
            monthly_installment = npf.pmt(rate=interest_rate / 12, nper=tenure, pv=-loan_amount)

            start_date = datetime.datetime.today().date()

            end_date = start_date + relativedelta(months=+tenure)

            if loan_approved:
                with transaction.atomic():
                    loan = Loan.objects.create(
                        customer=customer,
                        loan_amount=loan_amount,
                        interest_rate=corrected_interest_rate,
                        tenure=tenure,
                        start_date=start_date,
                        end_date=end_date,
                        emis_paid_on_time=0,
                        monthly_repayment=monthly_installment
                    )
                    loan_id = loan.loan_id
                    customer.customer_id += calculate_remaining_loan_balance(loan)
                    customer.save()

                response_data = {
                    'loan_id': loan_id,
                    'customer_id': customer_id,
                    'loan_approved': loan_approved,
                    'message': message,
                    'monthly_installment': monthly_installment,
                }

            else:
                response_data = {
                    'loan_id': None,
                    'customer_id': customer_id,
                    'loan_approved': loan_approved,
                    'message': message,
                    'monthly_installment': None,
                }
            response_serializer = CreateLoanResponseSerializer(data=response_data)
            if response_serializer.is_valid():
                return Response(response_serializer.data)
            return Response(response_serializer.errors, status=400)
        return Response(serializer.errors, status=400)


class ViewLoanView(APIView):
    def get(self, request, loan_id):
        # Retrieve the loan by ID or return 404 if not found
        loan = Loan.objects.filter(loan_id=loan_id).first()
        loan.customer_info = Customer.objects.get(customer_id=loan.customer_id)
        # Serialize the loan data
        serializer = SingleLoanDetailSerializer(instance=loan)

        return Response(serializer.data)


class ViewLoansView(APIView):
    def get(self, request, customer_id):
        # Ensure the customer exists
        try:
            customer = Customer.objects.get(customer_id=customer_id)
            loans = Loan.objects.filter(customer_id=customer_id, end_date__gte=datetime.date.today())
            serializer = LoanDetailSerializer(loans, many=True)
            return Response(serializer.data)
        except ObjectDoesNotExist as e:
            return Response({
                'error': 'Customer not found.'
            }, status=404)
