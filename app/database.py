# database.py
from pymongo import MongoClient
from app.config import MONGODB_URL

client = MongoClient(MONGODB_URL)

database = client.Call_Assistant_Dashboard

collection_user = database["users"]
