
from db import get_connection

try:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT current_database(), NOW()")
            database, server_time = cursor.fetchone()

            print("Connected successfully!")
            print("Database:", database)
            print("Server time:", server_time)

            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)

            tables = cursor.fetchall()

            print("\nTables found:")
            for table in tables:
                print("-", table[0])

except Exception as e:
    print("Database connection failed!")
    print(e)
