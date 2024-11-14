import os.path
from datetime import datetime

from celery import shared_task
import pandas as pd
from django.conf import settings
from django.db import connection
from sqlalchemy import create_engine

from CreditNest.settings import env
from credit.models import Loan, Customer
from credit.utils import calculate_remaining_loan_balance


def load_data(file_path, table_name, engine):
    try:
        data = pd.read_excel(file_path)
        data.columns = [col.lower().replace(' ', '_') for col in data.columns]

        if table_name == 'credit_loan':
            rename_columns = {
                "monthly_payment": "monthly_repayment",
                "date_of_approval": "start_date"
            }
            data.rename(columns=rename_columns, inplace=True)

            # Initializing a set to keep track of unique loan_ids
            unique_loan_ids = set()
            rows_to_drop = []

            # Iterate over the DataFrame
            for index, row in data.iterrows():
                loan_id = row['loan_id']
                # If the loan_id is already in the set, mark this row for deletion
                if loan_id in unique_loan_ids:
                    rows_to_drop.append(index)
                else:
                    # Otherwise, add the loan_id to the set
                    unique_loan_ids.add(loan_id)

            # Drop the rows with duplicate loan_ids
            data.drop(rows_to_drop, inplace=True)

        # Ingest data into the PostgreSQL database
        data.to_sql(table_name, engine, if_exists='append', index=False)

        reset_seq_sql = f"""
                SELECT setval(pg_get_serial_sequence('{table_name}', '{table_name.split("_")[-1]}_id'), 
                COALESCE(MAX({table_name.split("_")[-1]}_id), 0) + 1) FROM {table_name};
                """

        # Execute the SQL command to reset the sequence
        with connection.cursor() as cursor:
            cursor.execute(reset_seq_sql)

        return f"Data from {file_path} successfully loaded into {table_name} table."
    except Exception as e:
        return f"An error occurred: {e}"


def update_customer_debts():
    # Iterate over all customers
    for customer in Customer.objects.all():
        # Fetch loans for the customer that are still active
        active_loans = Loan.objects.filter(customer=customer, end_date__gte=datetime.today().date())

        # Calculate total debt from all active loans
        total_debt = sum(calculate_remaining_loan_balance(loan) for loan in active_loans)

        # Update the current debt field of the customer
        customer.current_debt = total_debt
        customer.save()


@shared_task
def ingest_data():
    db_name = env.str('DB_NAME')
    db_user = env.str('DB_USER')
    db_pass = env.str('DB_PASSWORD')
    db_host = env.str('DB_HOST')
    db_port = env.str('DB_PORT')

    conn_str = f'postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}'
    engine = create_engine(conn_str)

    # File paths for the Excel files
    customer_data_file = os.path.join(settings.STATIC_DIR, 'customer_data.xlsx')
    loan_data_file = os.path.join(settings.STATIC_DIR, 'loan_data.xlsx')

    load_customer_data_result = load_data(customer_data_file, 'credit_customer', engine)
    print(load_customer_data_result)
    load_loan_data_result = load_data(loan_data_file, 'credit_loan', engine)
    print(load_loan_data_result)

    try:
        update_customer_debts()
        print("Updated Debts")
    except Exception as e:
        print(e)
