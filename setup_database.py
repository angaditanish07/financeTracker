#!/usr/bin/env python3
"""
MongoDB database setup for EcoTracker
Creates MongoDB collections and initializes with default data
"""

from pymongo import MongoClient
import os
from pathlib import Path
from datetime import datetime

def setup_database():
    """Set up the MongoDB database with all collections and initial data"""
    print("🗄️  Setting up MongoDB database...")
    
    # Connect to MongoDB
    mongo_url = 'mongodb+srv://tanishangadi27_db_user:tanish%401234@tanish27.qqt4ite.mongodb.net/finance_tracker?retryWrites=true&w=majority'
    client = MongoClient(mongo_url)
    db = client.get_database()
    
    # Create collections (MongoDB creates collections automatically when first document is inserted)
    collections = [
        'users',
        'activities', 
        'categories',
        'transactions',
        'badges',
        'user_badges',
        'tips'
    ]
    
    for collection_name in collections:
        if collection_name not in db.list_collection_names():
            db.create_collection(collection_name)
            print(f"✅ Created collection: {collection_name}")
        else:
            print(f"✅ Collection already exists: {collection_name}")
    
    # Initialize default badges
    badges_collection = db.badges
    if not badges_collection.find_one():
        default_badges = [
            {
                'name': 'First Steps',
                'description': 'Log your first activity',
                'icon': '🌱',
                'requirement_type': 'total_activities',
                'requirement_value': 1,
                'created_at': datetime.utcnow()
            },
            {
                'name': 'Week Warrior',
                'description': 'Maintain a 7-day streak',
                'icon': '🔥',
                'requirement_type': 'streak_days',
                'requirement_value': 7,
                'created_at': datetime.utcnow()
            },
            {
                'name': 'Month Master',
                'description': 'Maintain a 30-day streak',
                'icon': '👑',
                'requirement_type': 'streak_days',
                'requirement_value': 30,
                'created_at': datetime.utcnow()
            },
            {
                'name': 'Eco Champion',
                'description': 'Keep total footprint under 1000kg CO2',
                'icon': '🌍',
                'requirement_type': 'low_footprint',
                'requirement_value': 1000,
                'created_at': datetime.utcnow()
            }
        ]
        badges_collection.insert_many(default_badges)
        print("✅ Inserted default badges")
    else:
        print("✅ Default badges already exist")
    
    # Initialize default tips
    tips_collection = db.tips
    if not tips_collection.find_one():
        default_tips = [
            {
                'title': 'Switch to LED Bulbs',
                'content': 'Replace incandescent bulbs with LED bulbs to reduce electricity usage by up to 80%.',
                'category': 'electricity',
                'impact_score': 0.7,
                'created_at': datetime.utcnow()
            },
            {
                'title': 'Use Public Transport',
                'content': 'Take public transport instead of driving to reduce your carbon footprint significantly.',
                'category': 'transport',
                'impact_score': 0.8,
                'created_at': datetime.utcnow()
            },
            {
                'title': 'Eat Less Meat',
                'content': 'Reduce meat consumption, especially beef, to lower your food-related carbon emissions.',
                'category': 'food',
                'impact_score': 0.9,
                'created_at': datetime.utcnow()
            },
            {
                'title': 'Unplug Electronics',
                'content': 'Unplug electronics when not in use to prevent phantom energy consumption.',
                'category': 'electricity',
                'impact_score': 0.5,
                'created_at': datetime.utcnow()
            }
        ]
        tips_collection.insert_many(default_tips)
        print("✅ Inserted default tips")
    else:
        print("✅ Default tips already exist")
    
    # Initialize default categories
    categories_collection = db.categories
    if not categories_collection.find_one({'is_default': True}):
        defaults = {
            'income': ['Salary', 'Bonus', 'Interest', 'Other Income'],
            'expense': ['Food', 'Rent', 'Transport', 'Utilities', 'Entertainment', 'Shopping', 'Health', 'Education', 'Bills', 'Other']
        }
        
        for t, names in defaults.items():
            for name in names:
                categories_collection.insert_one({
                    'user_id': None,
                    'name': name,
                    'type': t,
                    'is_default': True,
                    'created_at': datetime.utcnow()
                })
        print("✅ Inserted default categories")
    else:
        print("✅ Default categories already exist")
    
    client.close()
    print("✅ MongoDB database setup completed successfully")
    return True

def create_env_file():
    """Create .env file with default configuration"""
    env_file = Path('.env')
    
    if env_file.exists():
        print("✅ .env file already exists")
        return True
    
    env_content = """# Flask Configuration
SECRET_KEY=your-super-secret-key-change-this-in-production
FLASK_ENV=development
FLASK_DEBUG=True

# MongoDB Configuration
MONGODB_URL=mongodb://localhost:27017/finance_tracker

# OpenAI API Key (for AI recommendations) - Optional
OPENAI_API_KEY=your-openai-api-key-here

# Optional: Google Maps API Key (for travel distance calculation)
GOOGLE_MAPS_API_KEY=your-google-maps-api-key-here
"""
    
    try:
        with open(env_file, 'w') as f:
            f.write(env_content)
        print("✅ .env file created")
        print("⚠️  Please update the .env file with your actual API keys")
        return True
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")
        return False

def main():
    """Main setup function"""
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                    🌱 EcoTracker Setup                      ║
    ║              Carbon Footprint Tracker                       ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    success = True
    success &= setup_database()
    success &= create_env_file()
    
    if success:
        print("""
    🎉 Setup completed successfully!
    
    Next steps:
    1. Make sure your virtual environment is activated:
       venv\\Scripts\\activate
    
    2. Install dependencies:
       pip install -r requirements_simple.txt
    
    3. Make sure MongoDB is running on your system
    
    4. Run the application:
       python app.py
    
    5. Open your browser and go to: http://localhost:5000
    
    6. Register a new account and start tracking your carbon footprint!
    
    📝 Notes:
    - The application is now configured to use MongoDB
    - Add your OpenAI API key to .env for AI recommendations
    - Add your Google Maps API key to .env for travel distance features
    
    🌱 Happy carbon tracking!
        """)
    else:
        print("❌ Setup failed. Please check the errors above.")

if __name__ == "__main__":
    main()
