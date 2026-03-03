import sqlite3

connection = sqlite3.connect("my_database.db")

cursor = connection.cursor()

# подзапрос с запросом

try:
    cursor.execute('BEGIN')
    cursor.execute('INSERT INTO Users (username, email) VALUES (?,?)', ('user1', 'user1@example.com'))
    cursor.execute('INSERT INTO Uesrs (username, email) VALUES (?,?)', ('user2', 'user2@example.com'))

    cursor.execute('COMMIT')

except:
    cursor.execute('ROLLBACK')


try:
    with connection:
        cursor.execute('INSERT INTO Users (username, email) VALUES (?,?)', ('user3', 'user3@example.com'))
        cursor.execute('INSERT INTO Users (username, email) VALUES (?,?)', ('user4', 'user4@example.com'))
except:
    pass
connection.close()

