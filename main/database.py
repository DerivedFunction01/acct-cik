# %%
## Initialization
import sqlite3
import pandas as pd

db_path = "./web_data.db"


def execute_sql(sql: str, head: int = 0) -> pd.DataFrame | int:
    """
    Execute a SQL statement on a SQLite database.

    Parameters
    ----------
    sql : str
        SQL statement to execute.
    head : int, default 0
        If the query is a SELECT statement and head > 0, return the first `head` rows.
        Otherwise, returns the full DataFrame.

    Returns
    -------
    pd.DataFrame or int
        - For SELECT queries, a pandas DataFrame containing the results.
        - For other queries (INSERT, UPDATE, DELETE, etc.), an integer representing the number of affected rows.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Automatically determine if the query is a SELECT statement
    is_select = sql.strip().upper().startswith("SELECT")

    try:
        cursor.execute(sql)
        if is_select:
            # Fetch all results for SELECT
            columns = [col[0] for col in cursor.description]
            data = cursor.fetchall()
            df = pd.DataFrame(data, columns=columns)
            if head > 0:
                return df.head(head)  # Return the top `head` rows
            return df
        else:
            # Commit changes for INSERT, UPDATE, DELETE, etc.
            conn.commit()
            return cursor.rowcount
    finally:
        conn.close()


# %%
## Execute SELECT Statements
#ff = execute_sql("SELECT * FROM report_data WHERE NOT url=''")
#ff.to_csv("./report_data.csv", index=False)
#len(ff)


# %%
# ff = execute_sql("SELECT * FROM names", fetch=True)
# # ff[["name"]].to_excel("./names.xlsx", index=False)
# ff.head()

# %%
## Execute SELECT Statements on webpage result
# ff = execute_sql("SELECT * FROM webpage_result")
# ff.head()

# %%
## Execute SELECT Statements on server result
#ff = execute_sql("SELECT * FROM server_result")
#ff.head()

# %%
## Execute INSERT/DELETE/UPDATE Statements
# ff = execute_sql("DELETE FROM server_result")
# print(ff)

#%%
if __name__ == "__main__":
    last_df = None  # "Global" variable to hold the last queried DataFrame
    # Create a menu for common operations
    print("Database Operations Menu:")
    print("1. SELECT * FROM webpage_result")
    print("2. SELECT * FROM server_result")
    print("3. Custom SQL Query")
    print("4. Inspect last DataFrame")
    print("5. Exit")
    print("-" * 30)

    while True:
        choice = input("Enter your choice (1/2/3/4/5): ").strip()
        if choice == "1":
            df = execute_sql("SELECT * FROM webpage_result")
            last_df = df
            print(df.head(20))
        elif choice == "2":
            df = execute_sql("SELECT * FROM server_result")
            last_df = df
            print(df.head(20))
        elif choice == "3":
            custom_sql = input("Enter your SQL query: ").strip()
            if custom_sql:
                result = execute_sql(custom_sql)
                if isinstance(result, pd.DataFrame):
                    last_df = result
                    print(result)
                else:
                    print(f"Query executed successfully, {result} rows affected.")
            else:
                print("No SQL query entered.")
        elif choice == "4":
            if last_df is not None:
                print("Last DataFrame is available as 'last_df'.")
                print("You can perform operations like 'last_df.iloc[0]' or 'last_df.info()'.")
                print("Type 'exit' or press Ctrl+Z (Windows) / Ctrl+D (Unix) to return to the menu.")
                import code
                code.interact(local=locals())
            else:
                print("No DataFrame has been loaded yet. Please run a query first.")
        elif choice == "5":
            print("Exiting the program.")
            break
        else:
            print("Invalid choice. Please try again.")
