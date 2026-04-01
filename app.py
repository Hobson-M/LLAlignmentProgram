from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from config import SECRET_KEY, DATABASE, ODDS_API_KEY
from models import db, User, Settings, Cycle, Accumulator, Bet, DropdownData
from forms import LoginForm, ChangePasswordForm
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
import os
from datetime import datetime
import re
import csv
import io
from flask import Response
import urllib.request
import urllib.parse
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{DATABASE}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['ODDS_API_KEY'] = ODDS_API_KEY

db.init_app(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()
    # Create default settings if not exists
    if not Settings.query.first():
        db.session.add(Settings())
        db.session.commit()
    # Create default user if not exists
    if not User.query.filter_by(username='admin').first():
        hashed_password = bcrypt.generate_password_hash('password').decode('utf-8')
        default_user = User(username='admin', password_hash=hashed_password)
        db.session.add(default_user)
        db.session.commit()
    
    # Default dropdowns
    if DropdownData.query.count() == 0:
        sports = ['Football', 'Basketball', 'Tennis', 'Ice Hockey', 'Table Tennis']
        for sport in sports:
            s = DropdownData(category='sport', value=sport)
            db.session.add(s)
            db.session.commit()
            
            if sport == 'Football':
                c = DropdownData(category='country', parent_id=s.id, value='England')
                db.session.add(c)
                db.session.commit()
                db.session.add(DropdownData(category='league', parent_id=c.id, value='Premier League'))
                
                for bt in ['Over 2.5', 'Under 2.5', 'BTS', 'Over 8.5 Corners', 'Over 3.5 Cards', 'Over 23.5 Fouls']:
                    db.session.add(DropdownData(category='bet_type', parent_id=s.id, value=bt))
            elif sport == 'Basketball':
                c = DropdownData(category='country', parent_id=s.id, value='USA')
                db.session.add(c)
                db.session.commit()
                db.session.add(DropdownData(category='league', parent_id=c.id, value='NBA'))
                db.session.add(DropdownData(category='bet_type', parent_id=s.id, value='Totals'))
            elif sport == 'Tennis':
                c = DropdownData(category='country', parent_id=s.id, value='International')
                db.session.add(c)
                db.session.commit()
                db.session.add(DropdownData(category='league', parent_id=c.id, value='ATP'))
                db.session.add(DropdownData(category='bet_type', parent_id=s.id, value='Totals'))
            elif sport == 'Ice Hockey':
                c = DropdownData(category='country', parent_id=s.id, value='USA')
                db.session.add(c)
                db.session.commit()
                db.session.add(DropdownData(category='league', parent_id=c.id, value='NHL'))
                db.session.add(DropdownData(category='bet_type', parent_id=s.id, value='Over 3.5 Totals'))
                db.session.add(DropdownData(category='bet_type', parent_id=s.id, value='Over 4.5 Totals'))
            elif sport == 'Table Tennis':
                c = DropdownData(category='country', parent_id=s.id, value='International')
                db.session.add(c)
                db.session.commit()
                db.session.add(DropdownData(category='league', parent_id=c.id, value='ITTF'))
                db.session.add(DropdownData(category='bet_type', parent_id=s.id, value='Totals'))
        db.session.commit()

def get_active_cycle_and_accumulator():
    cycle = Cycle.query.filter_by(status='in_progress').first()
    if not cycle:
        last_cycle = Cycle.query.order_by(Cycle.number.desc()).first()
        number = last_cycle.number + 1 if last_cycle else 1
        cycle = Cycle(number=number)
        db.session.add(cycle)
        db.session.commit()
        
    accumulator = Accumulator.query.filter(Accumulator.cycle_id == cycle.id, Accumulator.status.in_(['pending', 'in_play'])).first()
    if not accumulator:
        day_number = (datetime.utcnow().date() - cycle.start_date.date()).days + 1
        day_number = max(1, day_number)
        
        # Ensure it never regresses if multiple accumulators happen on same day
        last_acc = Accumulator.query.filter_by(cycle_id=cycle.id).order_by(Accumulator.day_number.desc()).first()
        if last_acc and day_number <= last_acc.day_number:
            day_number = last_acc.day_number + 1
            
        accumulator = Accumulator(cycle_id=cycle.id, day_number=day_number)
        db.session.add(accumulator)
        db.session.commit()
        
    return cycle, accumulator

@app.route("/")
@login_required
def dashboard():
    cycle, accumulator = get_active_cycle_and_accumulator()
    
    active_bets = Bet.query.filter_by(accumulator_id=accumulator.id, is_excluded=False).all()
    
    # Floating Stash logic: Pull all pending stashed bets globally
    global_pending_excluded = Bet.query.filter_by(status='pending', is_excluded=True).all()
    # Pull finished excluded bets for THIS accumulator only (history)
    local_finished_excluded = Bet.query.filter(Bet.accumulator_id == accumulator.id, Bet.is_excluded == True, Bet.status != 'pending').all()
    
    excluded_bets = global_pending_excluded + local_finished_excluded
    
    # Game Day Alert Logic (Option B)
    current_date_str = datetime.utcnow().strftime('%Y-%m-%d')
    
    for bet in excluded_bets:
        bet.is_playing_today = False
        if bet.status == 'pending' and bet.match_date and bet.match_date.startswith(current_date_str):
            bet.is_playing_today = True

    # Sort so playing today floats to the top
    excluded_bets.sort(key=lambda b: b.is_playing_today, reverse=True)
    
    combined_odds = 1.0
    for b in active_bets:
        combined_odds *= b.odds

    # Progress calculations (Option C: win % + time %)
    total_active = len(active_bets)
    won_active = sum(1 for b in active_bets if b.status == 'won')
    win_percent = (won_active / total_active * 100) if total_active else 0
    # Time percent based on days elapsed in the current cycle (capped at 100)
    days_elapsed = (datetime.utcnow().date() - cycle.start_date.date()).days + 1
    # Assume a typical cycle length of 7 days for scaling; adjust if needed
    time_percent = min(days_elapsed / 7 * 100, 100)
    # Combined progress: equal weighting of win % and time %
    progress = (win_percent * 0.5) + (time_percent * 0.5)

    stats = {
        'total_cycles': Cycle.query.count(),
        'cycles_won': Cycle.query.filter_by(status='completed').count(),
        'total_legs': Bet.query.count(),
        'won_legs': Bet.query.filter_by(status='won').count()
    }
    win_rate = (stats['won_legs'] / stats['total_legs'] * 100) if stats['total_legs'] > 0 else 0

    return render_template('dashboard.html', cycle=cycle, accumulator=accumulator, bets=active_bets, excluded_bets=excluded_bets, combined_odds=combined_odds, stats=stats, win_rate=win_rate, progress=progress)

@app.route("/finalize_accumulator/<int:acc_id>", methods=["POST"])
@login_required
def finalize_accumulator(acc_id):
    acc = Accumulator.query.get_or_404(acc_id)
    if acc.is_finalized:
        flash("Accumulator already locked.", "info")
        return redirect(url_for('dashboard'))
    acc.is_finalized = True
    acc.finalized_at = datetime.utcnow()
    db.session.commit()
    flash("Ticket locked. You can now update results via the modal.", "success")
    return redirect(url_for('dashboard'))

@app.route("/unlock_accumulator/<int:acc_id>", methods=["POST"])
@login_required
def unlock_accumulator(acc_id):
    acc = Accumulator.query.get_or_404(acc_id)
    acc.is_finalized = False
    acc.finalized_at = None
    db.session.commit()
    flash("Ticket unlocked. You can now add or edit bets.", "info")
    return redirect(url_for('dashboard'))

# Quick update via modal (status selection)
@app.route("/quick_update/<int:bet_id>", methods=["POST"])
@login_required
def quick_update(bet_id):
    bet = Bet.query.get_or_404(bet_id)
    acc = bet.accumulator
    if not acc.is_finalized:
        flash("Accumulator not locked – quick update unavailable.", "warning")
        return redirect(url_for('dashboard'))
    new_status = request.form.get('status')
    if new_status not in ['pending', 'won', 'lost']:
        flash("Invalid status.", "danger")
        return redirect(url_for('dashboard'))
    bet.status = new_status
    db.session.commit()
    flash(f"Bet status set to {new_status}.", "success")
    return redirect(url_for('dashboard'))

# Guard add_bet when accumulator is finalized
def _guard_finalized(acc):
    if acc.is_finalized:
        flash("Cannot modify a locked ticket.", "danger")
        return True
    return False

# Modify add_bet route to include guard
@app.route("/add_bet", methods=["GET", "POST"])
@login_required
def add_bet():
    # Get current accumulator
    _, accumulator = get_active_cycle_and_accumulator()
    # Guard against modifications when ticket is locked
    if _guard_finalized(accumulator):
        return redirect(url_for('dashboard'))

    if request.method == "POST":
        sport = request.form.get('sport')
        country = request.form.get('country')
        league = request.form.get('league')
        home_team = request.form.get('home_team', '')
        away_team = request.form.get('away_team', '')
        match_desc = f"{home_team} vs {away_team}"
        if not home_team and not away_team:
            match_desc = request.form.get('match_desc', '')
        tracked_entity = request.form.get('tracked_entity', 'none')
        bet_type = request.form.get('bet_type')
        odds = float(request.form.get('odds', 1.0))
        threshold = request.form.get('threshold')
        match_date = request.form.get('match_date')
        notes = request.form.get('notes')

        # Auto-save potentially new dropdown data iteratively
        def get_or_create_dropdown(cat, val, parent_id=None):
            if not val:
                return None
            existing = DropdownData.query.filter(db.func.lower(DropdownData.value) == val.lower(), DropdownData.category == cat, DropdownData.parent_id == parent_id).first()
            if not existing:
                existing = DropdownData(category=cat, parent_id=parent_id, value=val)
                db.session.add(existing)
                db.session.commit()
            return existing.id

        sport_id = get_or_create_dropdown('sport', sport)
        country_id = get_or_create_dropdown('country', country, sport_id)
        get_or_create_dropdown('league', league, country_id)
        get_or_create_dropdown('bet_type', bet_type, sport_id)

        new_bet = Bet(
            accumulator_id=accumulator.id,
            sport=sport,
            country=country,
            league=league,
            home_team=home_team,
            away_team=away_team,
            tracked_entity=tracked_entity,
            match_desc=match_desc,
            bet_type=bet_type,
            odds=odds,
            threshold=threshold,
            match_date=match_date,
            status='pending',
            notes=notes,
            is_rolled_over=False,
        )
        db.session.add(new_bet)
        db.session.commit()
        flash('Bet added successfully!', 'success')
        return redirect(url_for('dashboard'))

    # GET request – render form
    all_dropdowns = DropdownData.query.all()
    data = [
        {'id': d.id, 'category': d.category, 'parent_id': d.parent_id, 'value': d.value}
        for d in all_dropdowns
    ]
    return render_template('add_bet.html', dropdown_data=data)

@app.route("/delete_bet/<int:bet_id>", methods=['POST'])
@login_required
def delete_bet(bet_id):
    bet = Bet.query.get_or_404(bet_id)
    if bet.status == 'pending' or bet.is_excluded:
        db.session.delete(bet)
        db.session.commit()
        flash('Bet deleted successfully.', 'success')
    else:
        flash('Cannot delete a bet that is not pending or excluded.', 'danger')
    return redirect(url_for('dashboard'))

@app.route("/exclude_bet/<int:bet_id>", methods=['POST'])
@login_required
def exclude_bet(bet_id):
    bet = Bet.query.get_or_404(bet_id)
    if bet.is_rolled_over and bet.status == 'pending':
        bet.is_excluded = True
        db.session.commit()
        flash('Bet securely benched to the stash.', 'success')
    else:
        flash('Cannot exclude this bet.', 'danger')
    return redirect(url_for('dashboard'))

@app.route("/include_bet/<int:bet_id>", methods=['POST'])
@login_required
def include_bet(bet_id):
    cycle, accumulator = get_active_cycle_and_accumulator()
    bet = Bet.query.get_or_404(bet_id)
    if bet.is_excluded and bet.status == 'pending':
        bet.is_excluded = False
        bet.accumulator_id = accumulator.id
        db.session.commit()
        flash('Bet successfully pulled into the active accumulator.', 'success')
    else:
        flash('Cannot include this bet.', 'danger')
    return redirect(url_for('dashboard'))

@app.route("/mark_results", methods=['GET', 'POST'])
@login_required
def mark_results():
    cycle, accumulator = get_active_cycle_and_accumulator()
    all_bets = Bet.query.filter_by(accumulator_id=accumulator.id).all()
    
    if request.method == 'POST':
        all_won = True
        has_lost = False
        lost_bets = []
        
        for bet in all_bets:
            result = request.form.get(f'result_{bet.id}')
            if result:
                bet.status = result
                if not bet.is_excluded:
                    if result == 'lost':
                        has_lost = True
                        all_won = False
                        lost_bets.append(bet)
                    elif result == 'pending':
                        all_won = False
                else:
                    if result == 'lost':
                        lost_bets.append(bet)
        
        db.session.commit()
        
        active_bets = [b for b in all_bets if not b.is_excluded]
        
        if all_won and len(active_bets) > 0 and not has_lost:
            accumulator.status = 'won'
            cycle.status = 'completed'
            cycle.end_date = datetime.utcnow()
            db.session.commit()
            
            # Since the accumulator won, what happens to excluded bets that were pending?
            # They stay pending. Excluded lost bets roll over!
            if lost_bets:
                new_acc = Accumulator(cycle_id=cycle.id, day_number=accumulator.day_number + 1)
                db.session.add(new_acc)
                db.session.commit()
                for bet in lost_bets:
                    new_threshold = bet.threshold
                    match = re.search(r'\d+', new_threshold)
                    if match:
                        num = int(match.group())
                        new_threshold = new_threshold[:match.start()] + str(num + 1) + new_threshold[match.end():]
                    
                    entities_to_track = ['home', 'away'] if bet.tracked_entity == 'both' else [bet.tracked_entity]
                    for entity in entities_to_track:
                        new_match_desc = bet.match_desc
                        if entity == 'home' and bet.home_team:
                            new_match_desc = f"Awaiting {bet.home_team}'s Next Match"
                        elif entity == 'away' and bet.away_team:
                            new_match_desc = f"Awaiting {bet.away_team}'s Next Match"
                            
                        new_bet = Bet(
                            accumulator_id=new_acc.id, sport=bet.sport, country=bet.country, league=bet.league,
                            home_team=bet.home_team, away_team=bet.away_team, tracked_entity=entity,
                            match_desc=new_match_desc, bet_type=bet.bet_type, odds=1.0, threshold=new_threshold, match_date='',
                            status='pending', notes=bet.notes, is_rolled_over=True, rolled_from_id=bet.id, is_excluded=True
                        )
                        db.session.add(new_bet)
                db.session.commit()
                
            flash(f'ACCUMULATOR WON! Cycle #{cycle.number} complete.', 'success')
            return redirect(url_for('dashboard'))
            
        elif has_lost:
            accumulator.status = 'lost'
            db.session.commit()
            
            # Auto-rollover to new day
            new_acc = Accumulator(cycle_id=cycle.id, day_number=accumulator.day_number + 1)
            db.session.add(new_acc)
            db.session.commit()
            
            for bet in lost_bets:
                new_threshold = bet.threshold
                match = re.search(r'\d+', new_threshold)
                if match:
                    num = int(match.group())
                    new_threshold = new_threshold[:match.start()] + str(num + 1) + new_threshold[match.end():]
                
                entities_to_track = ['home', 'away'] if bet.tracked_entity == 'both' else [bet.tracked_entity]
                for entity in entities_to_track:
                    new_match_desc = bet.match_desc
                    if entity == 'home' and bet.home_team:
                        new_match_desc = f"Awaiting {bet.home_team}'s Next Match"
                    elif entity == 'away' and bet.away_team:
                        new_match_desc = f"Awaiting {bet.away_team}'s Next Match"
                        
                    new_bet = Bet(
                        accumulator_id=new_acc.id, sport=bet.sport, country=bet.country, league=bet.league,
                        home_team=bet.home_team, away_team=bet.away_team, tracked_entity=entity,
                        match_desc=new_match_desc, bet_type=bet.bet_type, odds=1.0, threshold=new_threshold, match_date='',
                        status='pending', notes=bet.notes, is_rolled_over=True, rolled_from_id=bet.id, is_excluded=True
                    )
                    db.session.add(new_bet)
            db.session.commit()
            
            flash(f"{len(lost_bets)} legs lost. Rolling over to tomorrow's accumulator.", 'warning')
            return redirect(url_for('dashboard'))
            
        flash('Results updated.', 'info')
        return redirect(url_for('dashboard'))
        
    return render_template('mark_results.html', cycle=cycle, accumulator=accumulator, all_bets=all_bets)

@app.route("/quick_result/<int:bet_id>/<string:result>", methods=['POST'])
@login_required
def quick_result(bet_id, result):
    bet = Bet.query.get_or_404(bet_id)
    if bet.is_excluded and result in ['won', 'lost', 'pending']:
        bet.status = result
        db.session.commit()
        flash(f'Stashed bet updated to {result}.', 'success')
    return redirect(url_for('dashboard'))

@app.route("/update_odds/<int:bet_id>", methods=['POST'])
@login_required
def update_odds(bet_id):
    bet = Bet.query.get_or_404(bet_id)
    if bet.status == 'pending':
        try:
            new_odds = float(request.form.get('new_odds', 1.0))
            bet.odds = new_odds
            db.session.commit()
            flash('Odds updated successfully.', 'success')
        except ValueError:
            flash('Invalid odds provided.', 'danger')
    return redirect(url_for('dashboard'))

@app.route("/sync_fixture/<int:bet_id>", methods=['POST'])
@login_required
def sync_fixture(bet_id):
    bet = Bet.query.get_or_404(bet_id)
    api_key = app.config.get('ODDS_API_KEY')
    
    if not api_key:
        flash("ODDS_API_KEY is not set in config. Please add your key to config.py to sync.", "danger")
        return redirect(url_for('dashboard'))
        
    team_to_track = ""
    if bet.tracked_entity == 'home' and bet.home_team:
        team_to_track = bet.home_team
    elif bet.tracked_entity == 'away' and bet.away_team:
        team_to_track = bet.away_team
        
    if not team_to_track:
        flash("Could not determine team to track.", "danger")
        return redirect(url_for('dashboard'))

    # Map common user leagues to specific Odds API keys to bypass the 'upcoming' 8-game limit
    league_map = {
        "premier league": "soccer_epl",
        "fa cup": "soccer_fa_cup",
        "la liga": "soccer_spain_la_liga",
        "serie a": "soccer_italy_serie_a",
        "bundesliga": "soccer_germany_bundesliga",
        "ligue 1": "soccer_france_ligue_one",
        "champions league": "soccer_uefa_champs_league",
        "europa league": "soccer_uefa_europa_league",
        "mls": "soccer_usa_mls",
        "nba": "basketball_nba",
        "nfl": "americanfootball_nfl",
        "nhl": "icehockey_nhl",
        "mlb": "baseball_mlb"
    }
    
    sport_key = "upcoming"
    if bet.league:
        for key, val in league_map.items():
            if key in bet.league.lower():
                sport_key = val
                break

    # Query specific sport or default to upcoming.
    # Cost optimization: We only query 1 region ('uk') and 1 market ('h2h') to keep the API cost exactly at 1 credit per sync.
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?apiKey={api_key}&regions=uk&markets=h2h"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            
            found_game = None
            for game in data:
                home = game.get('home_team', '')
                away = game.get('away_team', '')
                if team_to_track.lower() in home.lower() or team_to_track.lower() in away.lower():
                    found_game = game
                    break
                    
            if found_game:
                bet.match_desc = f"{found_game.get('home_team')} vs {found_game.get('away_team')}"
                ct = found_game.get('commence_time')
                if ct:
                    try:
                        parsed_time = datetime.strptime(ct, "%Y-%m-%dT%H:%M:%SZ")
                        bet.match_date = parsed_time.strftime("%Y-%m-%dT%H:%M")
                    except:
                        pass
                
                db.session.commit()
                flash(f"Sync Successful: Found next match for {team_to_track}!", "success")
            else:
                flash(f"Could not find upcoming (next 8) fixtures for {team_to_track} on The Odds API.", "warning")
                
    except Exception as e:
        flash(f"API Sync Failed (Check your key or limits): {str(e)}", "danger")

    return redirect(url_for('dashboard'))

@app.route("/edit_fixture/<int:bet_id>", methods=['POST'])
@login_required
def edit_fixture(bet_id):
    bet = Bet.query.get_or_404(bet_id)
    new_match = request.form.get('new_match')
    new_date = request.form.get('new_date')
    if new_match:
        bet.match_desc = new_match
        if new_date:
            bet.match_date = new_date
        db.session.commit()
        flash('Fixture manually updated.', 'success')
    return redirect(url_for('dashboard'))

@app.route("/history")
@login_required
def history():
    cycles = Cycle.query.order_by(Cycle.number.desc()).all()
    return render_template('history.html', cycles=cycles)

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            flash('Login successful!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html', form=form)

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route("/settings", methods=['GET', 'POST'])
@login_required
def settings():
    form = ChangePasswordForm()
    
    # Check if this is a form submission for password
    if 'submit' in request.form and form.validate_on_submit():
        if bcrypt.check_password_hash(current_user.password_hash, form.old_password.data):
            hashed_password = bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')
            current_user.password_hash = hashed_password
            db.session.commit()
            flash('Your password has been updated!', 'success')
            return redirect(url_for('settings'))
        else:
            flash('Current password is incorrect.', 'danger')

    settings_obj = Settings.query.first()
    
    if request.method == 'POST' and 'action' in request.form:
        action = request.form.get('action')
        
        if action == 'update_size':
            settings_obj.min_legs = int(request.form.get('min_legs', 13))
            settings_obj.max_legs = int(request.form.get('max_legs', 15))
            db.session.commit()
            flash('Accumulator size updated.', 'success')
            return redirect(url_for('settings'))
            
        elif action == 'add_dropdown_chain':
            sport = request.form.get('sport')
            country = request.form.get('country')
            league = request.form.get('league')
            bet_type = request.form.get('bet_type')
            
            def get_or_create_dropdown(cat, val, parent_id=None):
                if not val:
                    return None
                existing = DropdownData.query.filter(db.func.lower(DropdownData.value) == val.lower(), DropdownData.category == cat, DropdownData.parent_id == parent_id).first()
                if not existing:
                    existing = DropdownData(category=cat, parent_id=parent_id, value=val)
                    db.session.add(existing)
                    db.session.commit()
                return existing.id

            sport_id = get_or_create_dropdown('sport', sport)
            country_id = get_or_create_dropdown('country', country, sport_id)
            get_or_create_dropdown('league', league, country_id)
            get_or_create_dropdown('bet_type', bet_type, sport_id)
            
            flash('Synchronization success: Mapped custom chain successfully.', 'success')
            return redirect(url_for('settings'))
            
    dropdowns = DropdownData.query.all()
    return render_template('settings.html', form=form, settings=settings_obj, dropdowns=dropdowns)

@app.route("/export_csv")
@login_required
def export_csv():
    bets = Bet.query.all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Cycle_ID', 'Day_Number', 'Sport', 'Country', 'League', 'Match', 'Bet_Type', 'Odds', 'Threshold', 'Date', 'Status', 'Rolled_Over'])
    for bet in bets:
        writer.writerow([
            bet.id,
            bet.accumulator.cycle.number,
            bet.accumulator.day_number,
            bet.sport,
            bet.country,
            bet.league,
            bet.match_desc,
            bet.bet_type,
            bet.odds,
            bet.threshold,
            bet.match_date,
            bet.status,
            'Yes' if bet.is_rolled_over else 'No'
        ])
    output.seek(0)
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=bets_history.csv"}
    )

@app.route("/stats")
@login_required
def stats():
    bets = Bet.query.all()
    sport_stats = {}
    bet_type_stats = {}
    for bet in bets:
        if bet.status in ['won', 'lost']:
            if bet.sport not in sport_stats:
                sport_stats[bet.sport] = {'w': 0, 'l': 0}
            if bet.bet_type not in bet_type_stats:
                bet_type_stats[bet.bet_type] = {'w': 0, 'l': 0}
            if bet.status == 'won':
                sport_stats[bet.sport]['w'] += 1
                bet_type_stats[bet.bet_type]['w'] += 1
            else:
                sport_stats[bet.sport]['l'] += 1
                bet_type_stats[bet.bet_type]['l'] += 1
    
    chart_labels = list(sport_stats.keys())
    chart_wins = [sport_stats[s]['w'] for s in chart_labels] if chart_labels else []
    chart_losses = [sport_stats[s]['l'] for s in chart_labels] if chart_labels else []
    
    return render_template('stats.html', 
                           sport_stats=sport_stats, 
                           bet_type_stats=bet_type_stats,
                           chart_labels=chart_labels,
                           chart_wins=chart_wins,
                           chart_losses=chart_losses)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
