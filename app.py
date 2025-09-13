from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from pymongo import MongoClient
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
import csv
import io
import json
import os
from dotenv import load_dotenv
import bcrypt
import jwt
import requests
import openai
from bson import ObjectId

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
mongo_url = os.getenv('MONGODB_URL')
mongo_client = MongoClient(mongo_url)
db = mongo_client.get_database() 

# MongoDB collections
users_collection = db.users
activities_collection = db.activities
categories_collection = db.categories
transactions_collection = db.transactions
badges_collection = db.badges
user_badges_collection = db.user_badges
tips_collection = db.tips

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.username = user_data['username']
        self.email = user_data['email']
        self.password_hash = user_data['password_hash']
        self.created_at = user_data.get('created_at', datetime.utcnow())
        self.total_carbon_footprint = user_data.get('total_carbon_footprint', 0.0)
        self.streak_days = user_data.get('streak_days', 0)
        self.last_activity_date = user_data.get('last_activity_date')
        self.currency_code = user_data.get('currency_code', 'INR')
        self.month_start_day = user_data.get('month_start_day', 1)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    user_data = users_collection.find_one({'_id': ObjectId(user_id)})
    if user_data:
        return User(user_data)
    return None

# User functions:
def get_user_by_username(username):
    return users_collection.find_one({'username': username})

def create_user(username, email, password_hash):
    user = {
        'username': username,
        'email': email,
        'password_hash': password_hash,
        'created_at': datetime.utcnow(),
        'total_carbon_footprint': 0.0,
        'streak_days': 0,
        'last_activity_date': None,
        'currency_code': 'INR',
        'month_start_day': 1,
    }
    result = users_collection.insert_one(user)
    user['_id'] = result.inserted_id
    return user

CARBON_FACTORS = {
    'transport': {   # kg CO2 per km
        'car': 0.2,  
        'bus': 0.05, 
        'train': 0.04, 
        'plane': 0.25,  
        'bike': 0.0,  
        'walk': 0.0, 
    },
    'electricity': {
        'kwh': 0.5, 
    },
    'food': {
        'beef': 13.3,  
        'chicken': 2.9, 
        'fish': 3.0, 
        'vegetables': 0.2,
        'fruits': 0.3,
    },
    'waste': {
        'kg': 0.5,
    }
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')

        if users_collection.find_one({'username': username}):
            return jsonify({'error': 'Username already exists'}), 400

        if users_collection.find_one({'email': email}):
            return jsonify({'error': 'Email already exists'}), 400

        password_hash = generate_password_hash(password)
        user = create_user(username, email, password_hash)
        # Seed default categories for the user on first registration
        seed_default_categories(user['_id'])

        return jsonify({'message': 'Registration successful'}), 201

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        user_data = users_collection.find_one({'username': username})
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data)
            login_user(user)
            return jsonify({'message': 'Login successful'}), 200
        
        return jsonify({'error': 'Invalid credentials'}), 401
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/profile', methods=['GET'])
@login_required
def profile():
    return render_template('profile.html')

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        data = request.get_json() or {}
        username = (data.get('username') or '').strip()
        email = (data.get('email') or '').strip()
        currency = (data.get('currency_code') or '').strip() or 'INR'
        month_start_day = data.get('month_start_day')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')

        update_data = {}

        # Basic validations
        if username and username != current_user.username:
            if users_collection.find_one({'username': username}):
                return jsonify({'error': 'Username already taken'}), 400
            update_data['username'] = username

        if email and email != current_user.email:
            if users_collection.find_one({'email': email}):
                return jsonify({'error': 'Email already taken'}), 400
            update_data['email'] = email

        if currency:
            update_data['currency_code'] = currency.upper()

        try:
            msd = int(month_start_day) if month_start_day is not None else current_user.month_start_day
            if 1 <= msd <= 28:
                update_data['month_start_day'] = msd
        except Exception:
            pass

        if new_password:
            if new_password != confirm_password:
                return jsonify({'error': 'Passwords do not match'}), 400
            if len(new_password) < 6:
                return jsonify({'error': 'Password must be at least 6 characters'}), 400
            update_data['password_hash'] = generate_password_hash(new_password)

        if update_data:
            users_collection.update_one(
                {'_id': ObjectId(current_user.id)},
                {'$set': update_data}
            )

        return jsonify({'message': 'Settings updated'})

    return render_template('settings.html')

# ========== Finance APIs ==========

def seed_default_categories(user_id=None):
    defaults = {
        'income': ['Salary', 'Bonus', 'Interest', 'Other Income'],
        'expense': ['Food', 'Rent', 'Transport', 'Utilities', 'Entertainment', 'Shopping', 'Health', 'Education', 'Bills', 'Other']
    }
    # Create global defaults once
    if not categories_collection.find_one({'is_default': True}):
        for t, names in defaults.items():
            for name in names:
                categories_collection.insert_one({
                    'user_id': None,
                    'name': name,
                    'type': t,
                    'is_default': True,
                    'created_at': datetime.utcnow()
                })


@app.route('/api/categories', methods=['GET', 'POST'])
@login_required
def categories_api():
    if request.method == 'POST':
        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        ctype = data.get('type')
        if not name or ctype not in ('income', 'expense'):
            return jsonify({'error': 'Invalid category'}), 400
        
        category_doc = {
            'user_id': ObjectId(current_user.id),
            'name': name,
            'type': ctype,
            'is_default': False,
            'created_at': datetime.utcnow()
        }
        result = categories_collection.insert_one(category_doc)
        return jsonify({'id': str(result.inserted_id), 'name': name, 'type': ctype}), 201

    # GET
    user_cats = categories_collection.find({
        '$or': [
            {'user_id': ObjectId(current_user.id)},
            {'user_id': None}
        ]
    })
    return jsonify([
        {'id': str(c['_id']), 'name': c['name'], 'type': c['type'], 'is_default': c.get('is_default', False)}
        for c in user_cats
    ])


@app.route('/api/transactions', methods=['GET', 'POST'])
@login_required
def transactions_api():
    if request.method == 'POST':
        data = request.get_json() or {}
        t_type = data.get('type')
        amount = data.get('amount')
        category_id = data.get('category_id')
        t_date_str = data.get('date')
        description = data.get('description', '')

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid amount'}), 400

        if t_type not in ('income', 'expense'):
            return jsonify({'error': 'Invalid type'}), 400

        try:
            t_date = datetime.strptime(t_date_str, '%Y-%m-%d') if t_date_str else datetime.utcnow()
        except Exception:
            return jsonify({'error': 'Invalid date'}), 400

        # category optional; if provided, ensure accessible
        category = None
        if category_id:
            category = categories_collection.find_one({'_id': ObjectId(category_id)})
            if not category or (category.get('user_id') not in (None, ObjectId(current_user.id))):
                return jsonify({'error': 'Invalid category'}), 400

        transaction_doc = {
            'user_id': ObjectId(current_user.id),
            'type': t_type,
            'amount': amount,
            'category_id': ObjectId(category_id) if category_id else None,
            'date': t_date,
            'description': description,
            'created_at': datetime.utcnow()
        }
        result = transactions_collection.insert_one(transaction_doc)

        return jsonify({'message': 'Transaction added', 'id': str(result.inserted_id)}), 201

    # GET list with optional filters
    query = {'user_id': ObjectId(current_user.id)}
    start = request.args.get('start')
    end = request.args.get('end')
    ctype = request.args.get('type')
    
    if ctype in ('income', 'expense'):
        query['type'] = ctype
    if start:
        try:
            s = datetime.strptime(start, '%Y-%m-%d')
            query['date'] = {'$gte': s}
        except Exception:
            pass
    if end:
        try:
            e = datetime.strptime(end, '%Y-%m-%d')
            if 'date' in query:
                query['date']['$lte'] = e
            else:
                query['date'] = {'$lte': e}
        except Exception:
            pass

    txns = list(transactions_collection.find(query).sort([('date', -1), ('created_at', -1)]).limit(100))
    
    def serialize_txn(t):
        category_name = None
        if t.get('category_id'):
            category = categories_collection.find_one({'_id': t['category_id']})
            if category:
                category_name = category['name']
        
        return {
            'id': str(t['_id']),
            'type': t['type'],
            'amount': t['amount'],
            'category': category_name,
            'category_id': str(t['category_id']) if t.get('category_id') else None,
            'date': t['date'].strftime('%Y-%m-%d'),
            'description': t.get('description', '')
        }
    return jsonify([serialize_txn(t) for t in txns])

@app.route('/api/activities', methods=['GET', 'POST'])
@login_required
def activities():
    if request.method == 'POST':
        data = request.get_json()
        activity_type = data.get('activity_type')
        category = data.get('category')
        value = float(data.get('value'))
        unit = data.get('unit')
        description = data.get('description', '')
        
        if category in CARBON_FACTORS and activity_type in CARBON_FACTORS[category]:
            carbon_emission = value * CARBON_FACTORS[category][activity_type]
        else:
            carbon_emission = 0.0
        
        activity_doc = {
            'user_id': ObjectId(current_user.id),
            'activity_type': activity_type,
            'category': category,
            'value': value,
            'unit': unit,
            'carbon_emission': carbon_emission,
            'date': datetime.now(),
            'description': description,
            'created_at': datetime.utcnow()
        }
        
        activities_collection.insert_one(activity_doc)
        
        # Update user's total carbon footprint and streak
        users_collection.update_one(
            {'_id': ObjectId(current_user.id)},
            {'$inc': {'total_carbon_footprint': carbon_emission}}
        )
        
        today = datetime.now()
        user_data = users_collection.find_one({'_id': ObjectId(current_user.id)})
        last_activity_date = user_data.get('last_activity_date')
        current_streak = user_data.get('streak_days', 0)
        
        if last_activity_date:
            if (today.date() - last_activity_date.date()) == timedelta(days=1):
                new_streak = current_streak + 1
            elif (today.date() - last_activity_date.date()) > timedelta(days=1):
                new_streak = 1
            else:
                new_streak = current_streak
        else:
            new_streak = 1
        
        users_collection.update_one(
            {'_id': ObjectId(current_user.id)},
            {'$set': {
                'streak_days': new_streak,
                'last_activity_date': today
            }}
        )
        
        check_badges(current_user)
        
        return jsonify({'message': 'Activity logged successfully', 'carbon_emission': carbon_emission}), 201
    
    activities = list(activities_collection.find({'user_id': ObjectId(current_user.id)}).sort('date', -1).limit(50))
    return jsonify([{
        'id': str(a['_id']),
        'activity_type': a['activity_type'],
        'category': a['category'],
        'value': a['value'],
        'unit': a['unit'],
        'carbon_emission': a['carbon_emission'],
        'date': a['date'].strftime('%Y-%m-%d'),
        'description': a.get('description', '')
    } for a in activities])

@app.route('/api/dashboard-data')
@login_required
def dashboard_data():
    # Determine current month period based on user's month_start_day
    today = datetime.utcnow()
    start_day = max(1, min(28, current_user.month_start_day or 1))
    if today.day >= start_day:
        month_start = datetime(today.year, today.month, start_day)
    else:
        # previous month
        prev_month = today.month - 1 or 12
        prev_year = today.year - 1 if prev_month == 12 else today.year
        month_start = datetime(prev_year, prev_month, start_day)
    # month end is next month start - 1 day
    if month_start.month == 12:
        next_month_start = datetime(month_start.year + 1, 1, start_day)
    else:
        next_month_start = datetime(month_start.year, month_start.month + 1, start_day)
    month_end = next_month_start - timedelta(days=1)

    # Fetch transactions for last 180 days for charts
    six_months_ago = today - timedelta(days=180)
    txns = list(transactions_collection.find({
        'user_id': ObjectId(current_user.id),
        'date': {'$gte': six_months_ago}
    }))
    
    # Daily expenses series (positive numbers for expenses)
    daily_data = {}
    for t in txns:
        d = t['date'].strftime('%Y-%m-%d')
        daily_data.setdefault(d, 0.0)
        if t['type'] == 'expense':
            daily_data[d] += abs(t['amount'])

    # Category breakdown for current month (expenses only)
    cats_this_month = list(transactions_collection.find({
        'user_id': ObjectId(current_user.id),
        'date': {'$gte': month_start, '$lte': month_end},
        'type': 'expense'
    }))
    category_data = {}
    for t in cats_this_month:
        if t.get('category_id'):
            category = categories_collection.find_one({'_id': t['category_id']})
            key = category['name'] if category else 'Uncategorized'
        else:
            key = 'Uncategorized'
        category_data[key] = category_data.get(key, 0.0) + abs(t['amount'])

    # KPIs using MongoDB aggregation
    month_income_pipeline = [
        {'$match': {
            'user_id': ObjectId(current_user.id),
            'date': {'$gte': month_start, '$lte': month_end},
            'type': 'income'
        }},
        {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
    ]
    month_income_result = list(transactions_collection.aggregate(month_income_pipeline))
    month_income = month_income_result[0]['total'] if month_income_result else 0.0
    
    month_expense_pipeline = [
        {'$match': {
            'user_id': ObjectId(current_user.id),
            'date': {'$gte': month_start, '$lte': month_end},
            'type': 'expense'
        }},
        {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
    ]
    month_expense_result = list(transactions_collection.aggregate(month_expense_pipeline))
    month_expense = month_expense_result[0]['total'] if month_expense_result else 0.0

    # Current balance = total income - total expense overall
    total_income_pipeline = [
        {'$match': {
            'user_id': ObjectId(current_user.id),
            'type': 'income'
        }},
        {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
    ]
    total_income_result = list(transactions_collection.aggregate(total_income_pipeline))
    total_income = total_income_result[0]['total'] if total_income_result else 0.0
    
    total_expense_pipeline = [
        {'$match': {
            'user_id': ObjectId(current_user.id),
            'type': 'expense'
        }},
        {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
    ]
    total_expense_result = list(transactions_collection.aggregate(total_expense_pipeline))
    total_expense = total_expense_result[0]['total'] if total_expense_result else 0.0
    
    current_balance = float(total_income) - float(total_expense)

    income_this_month = float(month_income)
    expense_this_month = float(month_expense)
    savings_this_month = income_this_month - expense_this_month
    savings_rate = (savings_this_month / income_this_month) * 100.0 if income_this_month > 0 else 0.0
    
    return jsonify({
        'daily_data': daily_data,
        'category_data': category_data,
        'kpis': {
            'current_balance': round(current_balance, 2),
            'month_income': round(income_this_month, 2),
            'month_expense': round(expense_this_month, 2),
            'savings_rate': round(savings_rate, 2),
            'currency': current_user.currency_code or 'INR'
        }
    })

@app.route('/api/recommendations')
@login_required
def get_recommendations():
    """Finance insights: month-over-month category changes and savings tips."""
    today = datetime.utcnow()
    start_day = max(1, min(28, current_user.month_start_day or 1))

    # Current month window
    if today.day >= start_day:
        this_start = datetime(today.year, today.month, start_day)
    else:
        pm = today.month - 1 or 12
        py = today.year - 1 if pm == 12 else today.year
        this_start = datetime(py, pm, start_day)
    if this_start.month == 12:
        next_start = datetime(this_start.year + 1, 1, start_day)
    else:
        next_start = datetime(this_start.year, this_start.month + 1, start_day)
    this_end = next_start - timedelta(days=1)

    # Previous month window
    prev_end = this_start - timedelta(days=1)
    if this_start.month == 1:
        prev_start = datetime(this_start.year - 1, 12, start_day)
    else:
        prev_start = datetime(this_start.year, this_start.month - 1, start_day)

    # Aggregate expenses by category for both months
    tx_this = list(transactions_collection.find({
        'user_id': ObjectId(current_user.id),
        'type': 'expense',
        'date': {'$gte': this_start, '$lte': this_end}
    }))
    tx_prev = list(transactions_collection.find({
        'user_id': ObjectId(current_user.id),
        'type': 'expense',
        'date': {'$gte': prev_start, '$lte': prev_end}
    }))

    def by_cat(rows):
        out = {}
        for t in rows:
            if t.get('category_id'):
                category = categories_collection.find_one({'_id': t['category_id']})
                key = category['name'] if category else 'Uncategorized'
            else:
                key = 'Uncategorized'
            out[key] = out.get(key, 0.0) + abs(t['amount'])
        return out

    cur_by_cat = by_cat(tx_this)
    prev_by_cat = by_cat(tx_prev)

    # Compute category deltas
    deltas = []
    for cat, cur_val in cur_by_cat.items():
        prev_val = prev_by_cat.get(cat, 0.0)
        if prev_val == 0 and cur_val == 0:
            continue
        change_pct = ((cur_val - prev_val) / prev_val * 100.0) if prev_val > 0 else 100.0
        deltas.append((cat, cur_val, prev_val, change_pct))
    deltas.sort(key=lambda x: x[3], reverse=True)

    # KPIs for savings
    income_this_pipeline = [
        {'$match': {
            'user_id': ObjectId(current_user.id),
            'type': 'income',
            'date': {'$gte': this_start, '$lte': this_end}
        }},
        {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
    ]
    income_this_result = list(transactions_collection.aggregate(income_this_pipeline))
    income_this = income_this_result[0]['total'] if income_this_result else 0.0
    
    expense_this_pipeline = [
        {'$match': {
            'user_id': ObjectId(current_user.id),
            'type': 'expense',
            'date': {'$gte': this_start, '$lte': this_end}
        }},
        {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
    ]
    expense_this_result = list(transactions_collection.aggregate(expense_this_pipeline))
    expense_this = expense_this_result[0]['total'] if expense_this_result else 0.0

    currency = current_user.currency_code or 'USD'
    fmt = lambda v: f"{currency} {round(float(v), 2):,.2f}"

    insights = []
    if deltas:
        top_cat, cur_val, prev_val, change_pct = deltas[0]
        insights.append({
            'title': f'{top_cat} up {round(change_pct, 1)}% vs last month',
            'content': f'You spent {fmt(cur_val)} on {top_cat} this month vs {fmt(prev_val)} last month. Consider setting a budget or looking for savings.',
        })

    # Highest spend category this month
    if cur_by_cat:
        high_cat = max(cur_by_cat.items(), key=lambda kv: kv[1])
        insights.append({
            'title': f'Highest spend: {high_cat[0]}',
            'content': f'Category {high_cat[0]} totals {fmt(high_cat[1])} this month. Review transactions to find quick wins.',
        })

    # Savings rate
    income_val = float(income_this)
    expense_val = float(expense_this)
    if income_val > 0:
        savings = income_val - expense_val
        rate = max(0.0, (savings / income_val) * 100.0)
        insights.append({
            'title': f'Savings rate {round(rate, 1)}% this month',
            'content': f'Income {fmt(income_val)} minus expenses {fmt(expense_val)} equals {fmt(savings)} saved.',
        })

    if not insights:
        insights.append({
            'title': 'Add transactions to see insights',
            'content': 'Once you add income and expenses, we will show trends and tips.',
        })

    return jsonify(insights[:3])

@app.route('/api/export.csv')
@login_required
def export_csv():
    """Export transactions to CSV in the selected date range."""
    start = request.args.get('start')
    end = request.args.get('end')
    query = {'user_id': ObjectId(current_user.id)}
    
    if start:
        try:
            s = datetime.strptime(start, '%Y-%m-%d')
            query['date'] = {'$gte': s}
        except Exception:
            pass
    if end:
        try:
            e = datetime.strptime(end, '%Y-%m-%d')
            if 'date' in query:
                query['date']['$lte'] = e
            else:
                query['date'] = {'$lte': e}
        except Exception:
            pass

    rows = list(transactions_collection.find(query).sort('date', 1))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'date', 'type', 'amount', 'currency', 'category', 'description'])
    for t in rows:
        category_name = ''
        if t.get('category_id'):
            category = categories_collection.find_one({'_id': t['category_id']})
            if category:
                category_name = category['name']
        
        writer.writerow([
            str(t['_id']),
            t['date'].strftime('%Y-%m-%d'),
            t['type'],
            f"{t['amount']:.2f}",
            current_user.currency_code or 'USD',
            category_name,
            (t.get('description') or '').replace('\n', ' ').strip()
        ])

    resp = app.response_class(output.getvalue(), mimetype='text/csv')
    resp.headers['Content-Disposition'] = 'attachment; filename=transactions.csv'
    return resp

@app.route('/api/leaderboard')
@login_required
def leaderboard():
    users = list(users_collection.find().sort('total_carbon_footprint', 1).limit(10))
    
    return jsonify([{
        'username': user['username'],
        'total_footprint': user['total_carbon_footprint'],
        'streak_days': user['streak_days']
    } for user in users])

@app.route('/api/offset-calculator')
@login_required
def offset_calculator():
    trees_needed = current_user.total_carbon_footprint / 22
    carbon_credits = current_user.total_carbon_footprint / 1000
    
    return jsonify({
        'trees_needed': round(trees_needed, 2),
        'carbon_credits': round(carbon_credits, 2),
        'total_footprint': current_user.total_carbon_footprint
    })

def check_badges(user):
    """Check and award badges based on user achievements"""
    badges = list(badges_collection.find())
    
    for badge in badges:
        if user_badges_collection.find_one({'user_id': ObjectId(user.id), 'badge_id': badge['_id']}):
            continue
        
        if badge['requirement_type'] == 'streak_days' and user.streak_days >= badge['requirement_value']:
            award_badge(user, badge)
        elif badge['requirement_type'] == 'total_activities':
            activity_count = activities_collection.count_documents({'user_id': ObjectId(user.id)})
            if activity_count >= badge['requirement_value']:
                award_badge(user, badge)
        elif badge['requirement_type'] == 'low_footprint':
            if user.total_carbon_footprint <= badge['requirement_value']:
                award_badge(user, badge)

def award_badge(user, badge):
    """Award a badge to a user"""
    user_badge = {
        'user_id': ObjectId(user.id),
        'badge_id': badge['_id'],
        'earned_at': datetime.utcnow()
    }
    user_badges_collection.insert_one(user_badge)

@app.route('/api/badges')
@login_required
def get_badges():
    user_badges = list(user_badges_collection.find({'user_id': ObjectId(current_user.id)}))
    badges = []
    
    for user_badge in user_badges:
        badge = badges_collection.find_one({'_id': user_badge['badge_id']})
        if badge:
            badges.append({
                'name': badge['name'],
                'description': badge['description'],
                'icon': badge['icon'],
                'earned_at': user_badge['earned_at'].strftime('%Y-%m-%d')
            })
    
    return jsonify(badges)

def initialize_default_data():
    """Initialize default badges and tips in MongoDB"""
    # Initialize default badges
    if not badges_collection.find_one():
        default_badges = [
            {'name': 'First Steps', 'description': 'Log your first activity', 'icon': '🌱', 'requirement_type': 'total_activities', 'requirement_value': 1, 'created_at': datetime.utcnow()},
            {'name': 'Week Warrior', 'description': 'Maintain a 7-day streak', 'icon': '🔥', 'requirement_type': 'streak_days', 'requirement_value': 7, 'created_at': datetime.utcnow()},
            {'name': 'Month Master', 'description': 'Maintain a 30-day streak', 'icon': '👑', 'requirement_type': 'streak_days', 'requirement_value': 30, 'created_at': datetime.utcnow()},
            {'name': 'Eco Champion', 'description': 'Keep total footprint under 1000kg CO2', 'icon': '🌍', 'requirement_type': 'low_footprint', 'requirement_value': 1000, 'created_at': datetime.utcnow()},
        ]
        badges_collection.insert_many(default_badges)
    
    # Initialize default tips
    if not tips_collection.find_one():
        default_tips = [
            {'title': 'Switch to LED Bulbs', 'content': 'Replace incandescent bulbs with LED bulbs to reduce electricity usage by up to 80%.', 'category': 'electricity', 'impact_score': 0.7, 'created_at': datetime.utcnow()},
            {'title': 'Use Public Transport', 'content': 'Take public transport instead of driving to reduce your carbon footprint significantly.', 'category': 'transport', 'impact_score': 0.8, 'created_at': datetime.utcnow()},
            {'title': 'Eat Less Meat', 'content': 'Reduce meat consumption, especially beef, to lower your food-related carbon emissions.', 'category': 'food', 'impact_score': 0.9, 'created_at': datetime.utcnow()},
            {'title': 'Unplug Electronics', 'content': 'Unplug electronics when not in use to prevent phantom energy consumption.', 'category': 'electricity', 'impact_score': 0.5, 'created_at': datetime.utcnow()},
        ]
        tips_collection.insert_many(default_tips)

if __name__ == '__main__':
    initialize_default_data()
    app.run(debug=True)
