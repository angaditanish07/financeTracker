#!/usr/bin/env python3
"""
Simple database setup for EcoTracker
Creates SQLite database and initializes with default data
"""

import sqlite3
import os
from pathlib import Path

def setup_database():
    """Set up the SQLite database with all tables and initial data"""
    print("🗄️  Setting up SQLite database...")
    
    db_path = Path('carbon_tracker.db')
    
    if db_path.exists():
        print("✅ Database already exists")
        return True
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_carbon_footprint REAL DEFAULT 0.0,
                streak_days INTEGER DEFAULT 0,
                last_activity_date DATE,
                group_id INTEGER
            );
            
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                activity_type TEXT NOT NULL,
                category TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT NOT NULL,
                carbon_emission REAL NOT NULL,
                date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT,
                FOREIGN KEY (user_id) REFERENCES user (id)
            );
            
            CREATE TABLE IF NOT EXISTS badge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                icon TEXT NOT NULL,
                requirement_type TEXT NOT NULL,
                requirement_value INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS user_badge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                badge_id INTEGER NOT NULL,
                earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user (id),
                FOREIGN KEY (badge_id) REFERENCES badge (id),
                UNIQUE(user_id, badge_id)
            );
            
            CREATE TABLE IF NOT EXISTS "group" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS tip (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT NOT NULL,
                impact_score REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Insert default badges
        cursor.executemany("""
            INSERT OR IGNORE INTO badge (name, description, icon, requirement_type, requirement_value)
            VALUES (?, ?, ?, ?, ?)
        """, [
            ('First Steps', 'Log your first activity', '🌱', 'total_activities', 1),
            ('Week Warrior', 'Maintain a 7-day streak', '🔥', 'streak_days', 7),
            ('Month Master', 'Maintain a 30-day streak', '👑', 'streak_days', 30),
            ('Eco Champion', 'Keep total footprint under 1000kg CO2', '🌍', 'low_footprint', 1000),
        ])
        
        # Insert default tips
        cursor.executemany("""
            INSERT OR IGNORE INTO tip (title, content, category, impact_score)
            VALUES (?, ?, ?, ?)
        """, [
            ('Switch to LED Bulbs', 'Replace incandescent bulbs with LED bulbs to reduce electricity usage by up to 80%.', 'electricity', 0.7),
            ('Use Public Transport', 'Take public transport instead of driving to reduce your carbon footprint significantly.', 'transport', 0.8),
            ('Eat Less Meat', 'Reduce meat consumption, especially beef, to lower your food-related carbon emissions.', 'food', 0.9),
            ('Unplug Electronics', 'Unplug electronics when not in use to prevent phantom energy consumption.', 'electricity', 0.5),
        ])
        
        conn.commit()
        conn.close()
        print("✅ Database setup completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error setting up database: {e}")
        return False

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

# Database Configuration (SQLite for development)
DATABASE_URL=sqlite:///carbon_tracker.db

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
    
    2. Run the application:
       python app.py
    
    3. Open your browser and go to: http://localhost:5000
    
    4. Register a new account and start tracking your carbon footprint!
    
    📝 Notes:
    - The application is configured to use SQLite for development
    - Add your OpenAI API key to .env for AI recommendations
    - Add your Google Maps API key to .env for travel distance features
    
    🌱 Happy carbon tracking!
        """)
    else:
        print("❌ Setup failed. Please check the errors above.")

if __name__ == "__main__":
    main()
