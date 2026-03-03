import sqlite3

connection = sqlite3.connect("my_database.db")

cursor = connection.cursor()
cursor.execute('INSERT INTO Users (username, email, age) VALUES (?,?,?)', ('newuser','newuser@example.com',28))
connection.commit()    
connection.close()

