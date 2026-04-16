from pymongo import MongoClient
import os

client = MongoClient("mongodb+srv://raaj73906:Raaj6230097248@cluster0.fsyzvmn.mongodb.net/")
db = client["chat_db"]

messages = db["messages"]
mapping = db["mapping"]