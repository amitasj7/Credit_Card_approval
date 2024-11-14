import pandas as pd
from sqlalchemy import create_engine

# Assuming 'alemeno' is the database name, username, and password
db_name = 'alemeno'
db_user = 'alemeno'
db_pass = 'alemeno'
db_host = 'localhost'
db_port = '5432'

# Connection string for PostgreSQL
# Format: 'postgresql://username:password@host:port/database'
conn_str = f'postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}'
print(conn_str)
# Create SQLAlchemy engine
engine = create_engine(conn_str)


# Function to load data from an Excel file into a DataFrame and then into the database
def load_data(file_path, table_name):
    try:
        # Read data from Excel file
        data = pd.read_excel(file_path)
        data.columns = [col.lower().replace(' ', '_') for col in data.columns]
        new_headers = []
        for i in range(len(data.columns)):
            if data.columns[i] == "monthly_payment":
                new_headers.append("monthly_repayment")
            elif data.columns[i] == "date_of_approval":
                new_headers.append("start_date")
            else:
                new_headers.append(data.columns[i])
        data.columns = new_headers
        # Ingest data into the PostgreSQL database
        data.to_sql(table_name, engine, if_exists='append', index=False)
        return f"Data from {file_path} successfully loaded into {table_name} table."
    except Exception as e:
        return f"An error occurred: {e}"