from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
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

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'mysql://root:password@localhost/carbon_tracker')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Legacy carbon fields retained for backward compatibility; not used in finance mode
    total_carbon_footprint = db.Column(db.Float, default=0.0)
    streak_days = db.Column(db.Integer, default=0)
    last_activity_date = db.Column(db.Date)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)

    # Finance preferences
    currency_code = db.Column(db.String(10), default='INR')
    month_start_day = db.Column(db.Integer, default=1)
    
    activities = db.relationship('Activity', backref='user', lazy=True)
    badges = db.relationship('UserBadge', backref='user', lazy=True)
    transactions = db.relationship('Transaction', backref='user', lazy=True)

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    value = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    carbon_emission = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.Text)

class Badge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    icon = db.Column(db.String(100), nullable=False)
    requirement_type = db.Column(db.String(50), nullable=False)
    requirement_value = db.Column(db.Integer, nullable=False)

class UserBadge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey('badge.id'), nullable=False)
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    members = db.relationship('User', backref='group', lazy=True)

class Tip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    impact_score = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ========== Finance Models ==========

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # null => global/default
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'income' or 'expense'
    icon = db.Column(db.String(50))
    color = db.Column(db.String(20))
    is_default = db.Column(db.Boolean, default=False)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'income' | 'expense'
    amount = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    category = db.relationship('Category')

class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    period = db.Column(db.String(20), nullable=False)  # 'monthly' | 'weekly'
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BudgetItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    budget_id = db.Column(db.Integer, db.ForeignKey('budget.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    limit_amount = db.Column(db.Float, nullable=False)

    budget = db.relationship('Budget', backref='items')
    category = db.relationship('Category')

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

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
        
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 400
        
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already exists'}), 400
        
        password_hash = generate_password_hash(password)
        user = User(username=username, email=email, password_hash=password_hash)
        db.session.add(user)
        db.session.commit()

        # Seed default categories for the user on first registration
        seed_default_categories(user.id)
        
        return jsonify({'message': 'Registration successful'}), 201
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
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

        # Basic validations
        if username and username != current_user.username:
            if User.query.filter_by(username=username).first():
                return jsonify({'error': 'Username already taken'}), 400
            current_user.username = username

        if email and email != current_user.email:
            if User.query.filter_by(email=email).first():
                return jsonify({'error': 'Email already taken'}), 400
            current_user.email = email

        if currency:
            current_user.currency_code = currency.upper()

        try:
            msd = int(month_start_day) if month_start_day is not None else current_user.month_start_day
            if 1 <= msd <= 28:
                current_user.month_start_day = msd
        except Exception:
            pass

        if new_password:
            if new_password != confirm_password:
                return jsonify({'error': 'Passwords do not match'}), 400
            if len(new_password) < 6:
                return jsonify({'error': 'Password must be at least 6 characters'}), 400
            current_user.password_hash = generate_password_hash(new_password)

        db.session.commit()
        return jsonify({'message': 'Settings updated'})

    return render_template('settings.html')

# ========== Finance APIs ==========

def seed_default_categories(user_id: int = None):
    defaults = {
        'income': ['Salary', 'Bonus', 'Interest', 'Other Income'],
        'expense': ['Food', 'Rent', 'Transport', 'Utilities', 'Entertainment', 'Shopping', 'Health', 'Education', 'Bills', 'Other']
    }
    # Create global defaults once
    if not Category.query.filter_by(is_default=True).first():
        for t, names in defaults.items():
            for name in names:
                db.session.add(Category(user_id=None, name=name, type=t, is_default=True))
        db.session.commit()
    # Optionally copy to user-specific (or we can use global defaults by referencing null user_id)
    # For simplicity, we rely on global defaults; users can add their own later.


@app.route('/api/categories', methods=['GET', 'POST'])
@login_required
def categories_api():
    if request.method == 'POST':
        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        ctype = data.get('type')
        if not name or ctype not in ('income', 'expense'):
            return jsonify({'error': 'Invalid category'}), 400
        cat = Category(user_id=current_user.id, name=name, type=ctype, is_default=False)
        db.session.add(cat)
        db.session.commit()
        return jsonify({'id': cat.id, 'name': cat.name, 'type': cat.type}), 201

    # GET
    user_cats = Category.query.filter((Category.user_id == current_user.id) | (Category.user_id.is_(None))).all()
    return jsonify([
        {'id': c.id, 'name': c.name, 'type': c.type, 'is_default': c.is_default}
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
            t_date = datetime.strptime(t_date_str, '%Y-%m-%d').date() if t_date_str else datetime.utcnow().date()
        except Exception:
            return jsonify({'error': 'Invalid date'}), 400

        # category optional; if provided, ensure accessible
        category = None
        if category_id:
            category = db.session.get(Category, int(category_id))
            if not category or (category.user_id not in (None, current_user.id)):
                return jsonify({'error': 'Invalid category'}), 400

        txn = Transaction(
            user_id=current_user.id,
            type=t_type,
            amount=amount,
            category_id=category.id if category else None,
            date=t_date,
            description=description
        )
        db.session.add(txn)
        db.session.commit()

        return jsonify({'message': 'Transaction added', 'id': txn.id}), 201

    # GET list with optional filters
    qs = Transaction.query.filter_by(user_id=current_user.id)
    start = request.args.get('start')
    end = request.args.get('end')
    ctype = request.args.get('type')
    if ctype in ('income', 'expense'):
        qs = qs.filter_by(type=ctype)
    if start:
        try:
            s = datetime.strptime(start, '%Y-%m-%d').date()
            qs = qs.filter(Transaction.date >= s)
        except Exception:
            pass
    if end:
        try:
            e = datetime.strptime(end, '%Y-%m-%d').date()
            qs = qs.filter(Transaction.date <= e)
        except Exception:
            pass

    txns = qs.order_by(Transaction.date.desc(), Transaction.created_at.desc()).limit(100).all()
    def serialize_txn(t):
        return {
            'id': t.id,
            'type': t.type,
            'amount': t.amount,
            'category': t.category.name if t.category else None,
            'category_id': t.category_id,
            'date': t.date.strftime('%Y-%m-%d'),
            'description': t.description
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
        
        activity = Activity(
            user_id=current_user.id,
            activity_type=activity_type,
            category=category,
            value=value,
            unit=unit,
            carbon_emission=carbon_emission,
            date=datetime.now().date(),
            description=description
        )
        
        db.session.add(activity)
        
        current_user.total_carbon_footprint += carbon_emission
        
        today = datetime.now().date()
        if current_user.last_activity_date:
            if today - current_user.last_activity_date == timedelta(days=1):
                current_user.streak_days += 1
            elif today - current_user.last_activity_date > timedelta(days=1):
                current_user.streak_days = 1
        else:
            current_user.streak_days = 1
        
        current_user.last_activity_date = today
        db.session.commit()
        
        check_badges(current_user)
        
        return jsonify({'message': 'Activity logged successfully', 'carbon_emission': carbon_emission}), 201
    
    activities = Activity.query.filter_by(user_id=current_user.id).order_by(Activity.date.desc()).limit(50).all()
    return jsonify([{
        'id': a.id,
        'activity_type': a.activity_type,
        'category': a.category,
        'value': a.value,
        'unit': a.unit,
        'carbon_emission': a.carbon_emission,
        'date': a.date.strftime('%Y-%m-%d'),
        'description': a.description
    } for a in activities])

@app.route('/api/dashboard-data')
@login_required
def dashboard_data():
    # Determine current month period based on user's month_start_day
    today = datetime.utcnow().date()
    start_day = max(1, min(28, current_user.month_start_day or 1))
    if today.day >= start_day:
        month_start = date(today.year, today.month, start_day)
    else:
        # previous month
        prev_month = today.month - 1 or 12
        prev_year = today.year - 1 if prev_month == 12 else today.year
        month_start = date(prev_year, prev_month, start_day)
    # month end is next month start - 1 day
    if month_start.month == 12:
        next_month_start = date(month_start.year + 1, 1, start_day)
    else:
        next_month_start = date(month_start.year, month_start.month + 1, start_day)
    month_end = next_month_start - timedelta(days=1)

    # Fetch transactions for last 180 days for charts
    six_months_ago = today - timedelta(days=180)
    txns = Transaction.query.filter(
        Transaction.user_id == current_user.id,
        Transaction.date >= six_months_ago
    ).all()
    
    # Daily expenses series (positive numbers for expenses)
    daily_data = {}
    for t in txns:
        d = t.date.strftime('%Y-%m-%d')
        daily_data.setdefault(d, 0.0)
        if t.type == 'expense':
            daily_data[d] += abs(t.amount)

    # Category breakdown for current month (expenses only)
    cats_this_month = Transaction.query.filter(
        Transaction.user_id == current_user.id,
        Transaction.date >= month_start,
        Transaction.date <= month_end,
        Transaction.type == 'expense'
    ).all()
    category_data = {}
    for t in cats_this_month:
        key = t.category.name if t.category else 'Uncategorized'
        category_data[key] = category_data.get(key, 0.0) + abs(t.amount)

    # KPIs
    month_income = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0)).filter(
        Transaction.user_id == current_user.id,
        Transaction.date >= month_start,
        Transaction.date <= month_end,
        Transaction.type == 'income'
    ).scalar() or 0.0
    month_expense = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0)).filter(
        Transaction.user_id == current_user.id,
        Transaction.date >= month_start,
        Transaction.date <= month_end,
        Transaction.type == 'expense'
    ).scalar() or 0.0

    # Current balance = total income - total expense overall
    total_income = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0)).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == 'income'
    ).scalar() or 0.0
    total_expense = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0)).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == 'expense'
    ).scalar() or 0.0
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
    today = datetime.utcnow().date()
    start_day = max(1, min(28, current_user.month_start_day or 1))

    # Current month window
    if today.day >= start_day:
        this_start = date(today.year, today.month, start_day)
    else:
        pm = today.month - 1 or 12
        py = today.year - 1 if pm == 12 else today.year
        this_start = date(py, pm, start_day)
    if this_start.month == 12:
        next_start = date(this_start.year + 1, 1, start_day)
    else:
        next_start = date(this_start.year, this_start.month + 1, start_day)
    this_end = next_start - timedelta(days=1)

    # Previous month window
    prev_end = this_start - timedelta(days=1)
    if this_start.month == 1:
        prev_start = date(this_start.year - 1, 12, start_day)
    else:
        prev_start = date(this_start.year, this_start.month - 1, start_day)

    # Aggregate expenses by category for both months
    tx_this = Transaction.query.filter(
        Transaction.user_id == current_user.id,
        Transaction.type == 'expense',
        Transaction.date >= this_start,
        Transaction.date <= this_end
    ).all()
    tx_prev = Transaction.query.filter(
        Transaction.user_id == current_user.id,
        Transaction.type == 'expense',
        Transaction.date >= prev_start,
        Transaction.date <= prev_end
    ).all()

    def by_cat(rows):
        out = {}
        for t in rows:
            key = t.category.name if t.category else 'Uncategorized'
            out[key] = out.get(key, 0.0) + abs(t.amount)
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
    income_this = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0)).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == 'income',
        Transaction.date >= this_start,
        Transaction.date <= this_end,
    ).scalar() or 0.0
    expense_this = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0)).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == 'expense',
        Transaction.date >= this_start,
        Transaction.date <= this_end,
    ).scalar() or 0.0

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
    qs = Transaction.query.filter_by(user_id=current_user.id)
    if start:
        try:
            s = datetime.strptime(start, '%Y-%m-%d').date()
            qs = qs.filter(Transaction.date >= s)
        except Exception:
            pass
    if end:
        try:
            e = datetime.strptime(end, '%Y-%m-%d').date()
            qs = qs.filter(Transaction.date <= e)
        except Exception:
            pass

    rows = qs.order_by(Transaction.date.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'date', 'type', 'amount', 'currency', 'category', 'description'])
    for t in rows:
        writer.writerow([
            t.id,
            t.date.strftime('%Y-%m-%d'),
            t.type,
            f"{t.amount:.2f}",
            current_user.currency_code or 'USD',
            t.category.name if t.category else '',
            (t.description or '').replace('\n', ' ').strip()
        ])

    resp = app.response_class(output.getvalue(), mimetype='text/csv')
    resp.headers['Content-Disposition'] = 'attachment; filename=transactions.csv'
    return resp

@app.route('/api/leaderboard')
@login_required
def leaderboard():
    users = User.query.order_by(User.total_carbon_footprint.asc()).limit(10).all()
    
    return jsonify([{
        'username': user.username,
        'total_footprint': user.total_carbon_footprint,
        'streak_days': user.streak_days
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
    badges = Badge.query.all()
    
    for badge in badges:
        if UserBadge.query.filter_by(user_id=user.id, badge_id=badge.id).first():
            continue
        
        if badge.requirement_type == 'streak_days' and user.streak_days >= badge.requirement_value:
            award_badge(user, badge)
        elif badge.requirement_type == 'total_activities':
            activity_count = Activity.query.filter_by(user_id=user.id).count()
            if activity_count >= badge.requirement_value:
                award_badge(user, badge)
        elif badge.requirement_type == 'low_footprint':
            if user.total_carbon_footprint <= badge.requirement_value:
                award_badge(user, badge)

def award_badge(user, badge):
    """Award a badge to a user"""
    user_badge = UserBadge(user_id=user.id, badge_id=badge.id)
    db.session.add(user_badge)
    db.session.commit()

@app.route('/api/badges')
@login_required
def get_badges():
    user_badges = UserBadge.query.filter_by(user_id=current_user.id).all()
    badges = []
    
    for user_badge in user_badges:
        badge = db.session.get(Badge, user_badge.badge_id)
        badges.append({
            'name': badge.name,
            'description': badge.description,
            'icon': badge.icon,
            'earned_at': user_badge.earned_at.strftime('%Y-%m-%d')
        })
    
    return jsonify(badges)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        if not Badge.query.first():
            default_badges = [
                Badge(name='First Steps', description='Log your first activity', icon='🌱', requirement_type='total_activities', requirement_value=1),
                Badge(name='Week Warrior', description='Maintain a 7-day streak', icon='🔥', requirement_type='streak_days', requirement_value=7),
                Badge(name='Month Master', description='Maintain a 30-day streak', icon='👑', requirement_type='streak_days', requirement_value=30),
                Badge(name='Eco Champion', description='Keep total footprint under 1000kg CO2', icon='🌍', requirement_type='low_footprint', requirement_value=1000),
            ]
            
            for badge in default_badges:
                db.session.add(badge)
            
            default_tips = [
                Tip(title='Switch to LED Bulbs', content='Replace incandescent bulbs with LED bulbs to reduce electricity usage by up to 80%.', category='electricity', impact_score=0.7),
                Tip(title='Use Public Transport', content='Take public transport instead of driving to reduce your carbon footprint significantly.', category='transport', impact_score=0.8),
                Tip(title='Eat Less Meat', content='Reduce meat consumption, especially beef, to lower your food-related carbon emissions.', category='food', impact_score=0.9),
                Tip(title='Unplug Electronics', content='Unplug electronics when not in use to prevent phantom energy consumption.', category='electricity', impact_score=0.5),
            ]
            
            for tip in default_tips:
                db.session.add(tip)
            
            db.session.commit()
    
    app.run(debug=True)
