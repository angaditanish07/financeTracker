#!/usr/bin/env python3
"""
Create user and add historical data to EcoTracker (MongoDB Version)
Creates a demo user with 6 months of realistic activity data
"""

from pymongo import MongoClient
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
import random
import os

# Connect to MongoDB
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://<username>:<password>@cluster0.mongodb.net/myDatabase")
client = MongoClient(MONGO_URI)
db = client["EcoTracker"]

users_col = db["users"]
activities_col = db["activities"]
badges_col = db["badges"]
user_badges_col = db["user_badges"]


def create_demo_user():
    print("👤 Creating demo user account...")

    existing_user = users_col.find_one({"username": "demo_user"})
    if existing_user:
        print("✅ Demo user already exists")
        return existing_user["_id"]

    user_doc = {
        "username": "demo_user",
        "email": "demo@ecotracker.com",
        "password_hash": generate_password_hash("demo123"),
        "created_at": datetime.now() - timedelta(days=180),
        "total_carbon_footprint": 0.0,
        "streak_days": 0,
        "last_activity_date": None
    }

    result = users_col.insert_one(user_doc)
    user_id = result.inserted_id

    print(f"✅ Created demo user: demo_user (ID: {user_id})")
    print("📧 Email: demo@ecotracker.com")
    print("🔑 Password: demo123")
    return user_id


def add_historical_data(user_id):
    print("📊 Adding 6 months of historical data...")

    activities = [
        {"category": "transport", "activity_type": "car", "unit": "km", "min_value": 5, "max_value": 50, "frequency": 0.4},
        {"category": "transport", "activity_type": "bus", "unit": "km", "min_value": 2, "max_value": 30, "frequency": 0.3},
        {"category": "transport", "activity_type": "train", "unit": "km", "min_value": 10, "max_value": 100, "frequency": 0.1},
        {"category": "transport", "activity_type": "bike", "unit": "km", "min_value": 1, "max_value": 15, "frequency": 0.15},
        {"category": "transport", "activity_type": "walk", "unit": "km", "min_value": 0.5, "max_value": 8, "frequency": 0.05},
        {"category": "electricity", "activity_type": "kwh", "unit": "kWh", "min_value": 2, "max_value": 20, "frequency": 0.6},
        {"category": "food", "activity_type": "beef", "unit": "kg", "min_value": 0.1, "max_value": 0.5, "frequency": 0.2},
        {"category": "food", "activity_type": "chicken", "unit": "kg", "min_value": 0.2, "max_value": 1.0, "frequency": 0.4},
        {"category": "food", "activity_type": "fish", "unit": "kg", "min_value": 0.1, "max_value": 0.8, "frequency": 0.2},
        {"category": "food", "activity_type": "vegetables", "unit": "kg", "min_value": 0.5, "max_value": 2.0, "frequency": 0.8},
        {"category": "food", "activity_type": "fruits", "unit": "kg", "min_value": 0.3, "max_value": 1.5, "frequency": 0.7},
        {"category": "food", "activity_type": "dairy", "unit": "kg", "min_value": 0.1, "max_value": 0.8, "frequency": 0.5},
        {"category": "waste", "activity_type": "kg", "unit": "kg", "min_value": 0.5, "max_value": 3.0, "frequency": 0.3}
    ]

    carbon_factors = {
        "transport": {"car": 0.2, "bus": 0.05, "train": 0.04, "bike": 0.0, "walk": 0.0},
        "electricity": {"kwh": 0.5},
        "food": {"beef": 13.3, "chicken": 2.9, "fish": 3.0, "vegetables": 0.2, "fruits": 0.3, "dairy": 1.4},
        "waste": {"kg": 0.5}
    }

    start_date = datetime.now() - timedelta(days=180)
    total_carbon_footprint = 0.0
    streak_days = 0
    last_activity_date = None

    for day in range(180):
        current_date = start_date + timedelta(days=day)
        is_weekend = current_date.weekday() >= 5
        num_activities = random.randint(1, 4) if is_weekend else random.randint(2, 8)

        if random.random() < 0.1:
            num_activities = 0
        elif random.random() < 0.05:
            num_activities = random.randint(8, 15)

        day_carbon = 0.0
        for _ in range(num_activities):
            activity = random.choices(activities, weights=[a["frequency"] for a in activities])[0]
            value = round(random.uniform(activity["min_value"], activity["max_value"]), 2)

            category = activity["category"]
            activity_type = activity["activity_type"]
            carbon_emission = value * carbon_factors[category][activity_type]

            description = f"Auto-generated {activity_type} activity"

            activities_col.insert_one({
                "user_id": user_id,
                "activity_type": activity_type,
                "category": category,
                "value": value,
                "unit": activity["unit"],
                "carbon_emission": carbon_emission,
                "date": current_date,
                "description": description
            })

            day_carbon += carbon_emission

        if num_activities > 0:
            if last_activity_date is None:
                streak_days = 1
            elif (current_date.date() - last_activity_date).days == 1:
                streak_days += 1
            elif (current_date.date() - last_activity_date).days > 1:
                streak_days = 1
            last_activity_date = current_date.date()

        total_carbon_footprint += day_carbon

    users_col.update_one(
        {"_id": user_id},
        {"$set": {
            "total_carbon_footprint": total_carbon_footprint,
            "streak_days": streak_days,
            "last_activity_date": last_activity_date
        }}
    )

    print(f"✅ Added 6 months of data. Total footprint: {total_carbon_footprint:.2f} kg CO₂, Streak: {streak_days} days")
    return True


def main():
    user_id = create_demo_user()
    if user_id:
        add_historical_data(user_id)
        print("🎉 Demo setup completed successfully!")


if __name__ == "__main__":
    main()
