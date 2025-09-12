#!/usr/bin/env python3
"""
Create user and add historical data to EcoTracker
Creates a demo user with 6 months of realistic activity data
"""

import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path
from werkzeug.security import generate_password_hash

def create_demo_user():
    """Create a demo user account"""
    print("👤 Creating demo user account...")
    
    db_path = Path('carbon_tracker.db')
    if not db_path.exists():
        print("❌ Database not found. Run setup_database.py first.")
        return None
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if demo user already exists
        cursor.execute("SELECT id FROM user WHERE username = 'demo_user'")
        existing_user = cursor.fetchone()
        
        if existing_user:
            print("✅ Demo user already exists")
            return existing_user[0]
        
        # Create demo user
        username = "demo_user"
        email = "demo@ecotracker.com"
        password_hash = generate_password_hash("demo123")
        
        cursor.execute("""
            INSERT INTO user (username, email, password_hash, created_at, total_carbon_footprint, streak_days)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, email, password_hash, datetime.now() - timedelta(days=180), 0.0, 0))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        print(f"✅ Created demo user: {username} (ID: {user_id})")
        print("📧 Email: demo@ecotracker.com")
        print("🔑 Password: demo123")
        
        return user_id
        
    except Exception as e:
        print(f"❌ Error creating demo user: {e}")
        return None

def add_historical_data(user_id):
    """Add 6 months of realistic activity data"""
    print("📊 Adding 6 months of historical data...")
    
    db_path = Path('carbon_tracker.db')
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Define realistic activity patterns
        activities = [
            # Transport activities (most common)
            {'category': 'transport', 'activity_type': 'car', 'unit': 'km', 'min_value': 5, 'max_value': 50, 'frequency': 0.4},
            {'category': 'transport', 'activity_type': 'bus', 'unit': 'km', 'min_value': 2, 'max_value': 30, 'frequency': 0.3},
            {'category': 'transport', 'activity_type': 'train', 'unit': 'km', 'min_value': 10, 'max_value': 100, 'frequency': 0.1},
            {'category': 'transport', 'activity_type': 'bike', 'unit': 'km', 'min_value': 1, 'max_value': 15, 'frequency': 0.15},
            {'category': 'transport', 'activity_type': 'walk', 'unit': 'km', 'min_value': 0.5, 'max_value': 8, 'frequency': 0.05},
            
            # Electricity activities
            {'category': 'electricity', 'activity_type': 'kwh', 'unit': 'kWh', 'min_value': 2, 'max_value': 20, 'frequency': 0.6},
            
            # Food activities
            {'category': 'food', 'activity_type': 'beef', 'unit': 'kg', 'min_value': 0.1, 'max_value': 0.5, 'frequency': 0.2},
            {'category': 'food', 'activity_type': 'chicken', 'unit': 'kg', 'min_value': 0.2, 'max_value': 1.0, 'frequency': 0.4},
            {'category': 'food', 'activity_type': 'fish', 'unit': 'kg', 'min_value': 0.1, 'max_value': 0.8, 'frequency': 0.2},
            {'category': 'food', 'activity_type': 'vegetables', 'unit': 'kg', 'min_value': 0.5, 'max_value': 2.0, 'frequency': 0.8},
            {'category': 'food', 'activity_type': 'fruits', 'unit': 'kg', 'min_value': 0.3, 'max_value': 1.5, 'frequency': 0.7},
            {'category': 'food', 'activity_type': 'dairy', 'unit': 'kg', 'min_value': 0.1, 'max_value': 0.8, 'frequency': 0.5},
            
            # Waste activities
            {'category': 'waste', 'activity_type': 'kg', 'unit': 'kg', 'min_value': 0.5, 'max_value': 3.0, 'frequency': 0.3},
        ]
        
        # Carbon emission factors
        carbon_factors = {
            'transport': {
                'car': 0.2, 'bus': 0.05, 'train': 0.04, 'plane': 0.25, 'bike': 0.0, 'walk': 0.0
            },
            'electricity': {'kwh': 0.5},
            'food': {
                'beef': 13.3, 'chicken': 2.9, 'fish': 3.0, 'vegetables': 0.2, 'fruits': 0.3, 'dairy': 1.4
            },
            'waste': {'kg': 0.5}
        }
        
        # Generate 6 months of data (180 days)
        start_date = datetime.now() - timedelta(days=180)
        total_carbon_footprint = 0.0
        streak_days = 0
        last_activity_date = None
        
        # Create realistic patterns (more activities on weekdays, fewer on weekends)
        for day in range(180):
            current_date = start_date + timedelta(days=day)
            is_weekend = current_date.weekday() >= 5
            
            # Determine number of activities for this day
            if is_weekend:
                num_activities = random.randint(1, 4)  # Fewer activities on weekends
            else:
                num_activities = random.randint(2, 8)  # More activities on weekdays
            
            # Add some variation (some days with no activities, some with many)
            if random.random() < 0.1:  # 10% chance of no activities
                num_activities = 0
            elif random.random() < 0.05:  # 5% chance of many activities
                num_activities = random.randint(8, 15)
            
            day_carbon = 0.0
            
            for _ in range(num_activities):
                # Select activity based on frequency
                activity = random.choices(activities, weights=[a['frequency'] for a in activities])[0]
                
                # Generate realistic value
                value = round(random.uniform(activity['min_value'], activity['max_value']), 2)
                
                # Calculate carbon emission
                category = activity['category']
                activity_type = activity['activity_type']
                carbon_emission = value * carbon_factors[category][activity_type]
                
                # Generate realistic descriptions
                descriptions = {
                    'transport': {
                        'car': ['Commute to work', 'Grocery shopping', 'Visit to friend', 'Doctor appointment'],
                        'bus': ['Public transport to work', 'Shopping trip', 'City center visit'],
                        'train': ['Business trip', 'Weekend getaway', 'Family visit'],
                        'bike': ['Morning exercise', 'Quick errand', 'Leisure ride'],
                        'walk': ['Morning walk', 'Dog walking', 'Short errand']
                    },
                    'electricity': {
                        'kwh': ['Daily household usage', 'Cooking and appliances', 'Lighting and electronics']
                    },
                    'food': {
                        'beef': ['Steak dinner', 'Burger lunch', 'Beef stew'],
                        'chicken': ['Chicken breast', 'Roast chicken', 'Chicken curry'],
                        'fish': ['Salmon dinner', 'Fish and chips', 'Tuna sandwich'],
                        'vegetables': ['Daily vegetables', 'Salad ingredients', 'Cooking vegetables'],
                        'fruits': ['Daily fruits', 'Smoothie ingredients', 'Snack fruits'],
                        'dairy': ['Milk consumption', 'Cheese usage', 'Yogurt']
                    },
                    'waste': {
                        'kg': ['Daily household waste', 'Kitchen waste', 'General waste']
                    }
                }
                
                description = random.choice(descriptions[category][activity_type])
                
                # Insert activity
                cursor.execute("""
                    INSERT INTO activity (user_id, activity_type, category, value, unit, carbon_emission, date, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, activity_type, category, value, activity['unit'], carbon_emission, current_date.date(), description))
                
                day_carbon += carbon_emission
            
            # Update streak logic
            if num_activities > 0:
                if last_activity_date is None:
                    streak_days = 1
                elif (current_date.date() - last_activity_date).days == 1:
                    streak_days += 1
                elif (current_date.date() - last_activity_date).days > 1:
                    streak_days = 1
                last_activity_date = current_date.date()
            
            total_carbon_footprint += day_carbon
        
        # Update user's total carbon footprint and streak
        cursor.execute("""
            UPDATE user 
            SET total_carbon_footprint = ?, streak_days = ?, last_activity_date = ?
            WHERE id = ?
        """, (total_carbon_footprint, streak_days, last_activity_date, user_id))
        
        # Add some badge achievements based on the historical data
        cursor.execute("SELECT COUNT(*) FROM activity WHERE user_id = ?", (user_id,))
        total_activities = cursor.fetchone()[0]
        
        # Award badges based on achievements
        badges_to_award = []
        
        if total_activities >= 1:
            badges_to_award.append(('First Steps', 1))
        
        if streak_days >= 7:
            badges_to_award.append(('Week Warrior', 2))
        
        if streak_days >= 30:
            badges_to_award.append(('Month Master', 3))
        
        if total_carbon_footprint <= 1000:
            badges_to_award.append(('Eco Champion', 4))
        
        # Award badges
        for badge_name, badge_id in badges_to_award:
            cursor.execute("""
                INSERT OR IGNORE INTO user_badge (user_id, badge_id, earned_at)
                VALUES (?, ?, ?)
            """, (user_id, badge_id, start_date + timedelta(days=random.randint(30, 150))))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Successfully added 6 months of historical data!")
        print(f"📊 Total activities: {total_activities}")
        print(f"🌱 Total carbon footprint: {total_carbon_footprint:.2f} kg CO₂")
        print(f"🔥 Current streak: {streak_days} days")
        print(f"🏆 Badges earned: {len(badges_to_award)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error adding historical data: {e}")
        return False

def main():
    """Main function"""
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                🚀 Demo Setup Generator                       ║
    ║         Create user and add 6 months of data                ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Create demo user
    user_id = create_demo_user()
    if not user_id:
        print("❌ Failed to create demo user")
        return
    
    # Add historical data
    success = add_historical_data(user_id)
    
    if success:
        print("""
    🎉 Demo setup completed successfully!
    
    📋 Login Credentials:
    - Username: demo_user
    - Email: demo@ecotracker.com
    - Password: demo123
    
    🌱 Your dashboard now shows:
    - 6 months of realistic activity data
    - Varied carbon footprint patterns
    - Achievements and badges
    - Realistic streaks and trends
    
    🔗 Access your dashboard at: http://localhost:5000
        """)
    else:
        print("❌ Failed to add historical data. Please check the errors above.")

if __name__ == "__main__":
    main()
