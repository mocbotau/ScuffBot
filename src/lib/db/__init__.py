import logging
import mysql.connector.pooling
from dotenv import find_dotenv, load_dotenv
import os

env_file = find_dotenv(".env.local")
load_dotenv(env_file)


class DB:
    with open(os.getenv("DB_PASSWORD_FILE"), "r", encoding="utf-8") as f:
        password = f.read().strip()
    pool = mysql.connector.pooling.MySQLConnectionPool(host=os.getenv("DB_HOST"), user=os.getenv(
        "DB_USER"), password=password, database=os.getenv("DB_DATABASE"), autocommit=True)

    def get_cursor():
        cnx = DB.pool.get_connection()
        cursor = cnx.cursor(dictionary=True)
        return (cnx, cursor)

    def close(connection, cursor):
        cursor.close()
        connection.close()

    def execute(command, *values):
        connection, cursor = DB.get_cursor()
        cursor.execute(command, tuple(values))
        DB.close(connection, cursor)

    def field(command, *values):
        connection, cursor = DB.get_cursor()
        cursor.execute(command, tuple(values))
        result = None if not (data := cursor.fetchone()
                              ) else list(data.values())[0]
        DB.close(connection, cursor)
        return result

    def row(command, *values):
        connection, cursor = DB.get_cursor()
        cursor.execute(command, tuple(values))
        result = cursor.fetchone()
        DB.close(connection, cursor)
        return result

    def rows(command, *values):
        connection, cursor = DB.get_cursor()
        cursor.execute(command, tuple(values))
        result = cursor.fetchall()
        DB.close(connection, cursor)
        return result

    def column(command, *values):
        connection, cursor = DB.get_cursor()
        cursor.execute(command, tuple(values))
        result = [list(row.values())[0] for row in cursor.fetchall()]
        DB.close(connection, cursor)
        return result
