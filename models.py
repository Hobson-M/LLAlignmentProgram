from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

class DropdownData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False) # sport, country, league, bet_type
    parent_id = db.Column(db.Integer, db.ForeignKey('dropdown_data.id'), nullable=True) # for cascading
    value = db.Column(db.String(100), nullable=False)
    
class Cycle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='in_progress') # in_progress, completed
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=True)

class Accumulator(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cycle_id = db.Column(db.Integer, db.ForeignKey('cycle.id'), nullable=False)
    day_number = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending') # pending, won, lost
    combined_odds = db.Column(db.Float, default=1.0)
    is_finalized = db.Column(db.Boolean, default=False)
    finalized_at = db.Column(db.DateTime, nullable=True)
    
    cycle = db.relationship('Cycle', backref=db.backref('accumulators', lazy=True))

class Bet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    accumulator_id = db.Column(db.Integer, db.ForeignKey('accumulator.id'), nullable=False)
    sport = db.Column(db.String(50), nullable=False)
    country = db.Column(db.String(50), nullable=False)
    league = db.Column(db.String(100), nullable=False)
    match_desc = db.Column(db.String(200), nullable=False)
    bet_type = db.Column(db.String(100), nullable=False)
    odds = db.Column(db.Float, nullable=False)
    threshold = db.Column(db.String(100), nullable=False)
    match_date = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default='pending') # pending, won, lost, void
    notes = db.Column(db.Text, nullable=True)
    
    is_rolled_over = db.Column(db.Boolean, default=False)
    rolled_from_id = db.Column(db.Integer, db.ForeignKey('bet.id'), nullable=True)
    is_excluded = db.Column(db.Boolean, default=False)
    home_team = db.Column(db.String(100), nullable=True)
    away_team = db.Column(db.String(100), nullable=True)
    tracked_entity = db.Column(db.String(20), default='home')
    next_opponent = db.Column(db.String(100), nullable=True)
    
    accumulator = db.relationship('Accumulator', backref=db.backref('bets', lazy=True))
    
class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    min_legs = db.Column(db.Integer, default=13)
    max_legs = db.Column(db.Integer, default=15)
