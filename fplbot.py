import requests
from collections import defaultdict

BOT_TOKEN = "7866601514:AAEsJRyRnfPV_IKgjMIHrUbaKGxcIGLS35g"
CHAT_ID = "7529074378"

# Set your FPL team ID here when ready (e.g., TEAM_ID = 1234567)
TEAM_ID = None  # <-- Set to your FPL team ID after GW1 to use your real team

FPL_API_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"

# FPL position codes
POSITION_MAP = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
POSITION_LIMITS = {'GK': 2, 'DEF': 5, 'MID': 5, 'FWD': 3}
STARTING_LIMITS = {'GK': 1, 'DEF': 3, 'MID': 2, 'FWD': 1}  # minimums for starting 11
MAX_FROM_CLUB = 3
TOTAL_BUDGET = 1000  # FPL API uses tenths of millions

# Fetch FPL data
data = requests.get(FPL_API_URL).json()
players = data['elements']
teams = data['teams']

# Fetch fixtures data
fixtures = requests.get(FPL_FIXTURES_URL).json()

# Helper: get club name by team id
def get_team_name(team_id):
    return teams[team_id-1]['name']

# Helper: get next 3 fixture difficulties for a team
team_fixtures = defaultdict(list)
for f in fixtures:
    if not f['finished']:
        # Home team
        team_fixtures[f['team_h']].append(f['team_h_difficulty'])
        # Away team
        team_fixtures[f['team_a']].append(f['team_a_difficulty'])

def get_next3_avg_difficulty(team_id):
    next3 = team_fixtures[team_id][:3]
    if not next3:
        return 3  # Neutral if no fixtures
    return sum(next3) / len(next3)

# Score players for attacking potential and value, adjusted for next 3 fixtures, injury risk, and recent form/minutes

def adjusted_score(base_score, avg_difficulty, chance_playing, flagged, form, minutes):
    # Lower difficulty = better (1 easiest, 5 hardest)
    fixture_factor = (6 - avg_difficulty) / 5
    # Injury/suspension risk: penalize if flagged or low chance of playing
    risk_factor = 1.0
    if flagged:
        risk_factor *= 0.5  # halve score if flagged
    if chance_playing is not None:
        risk_factor *= (chance_playing / 100)
    # Recent form: boost if form is high (form is a float, usually 0-10)
    form_factor = 1.0 + (float(form) - 5) / 10  # +10% for form 6, -10% for form 4
    # Minutes: boost if played most of last season (3000+), penalize if low (<1000)
    minutes_factor = 1.0
    if minutes >= 3000:
        minutes_factor = 1.1
    elif minutes < 1000:
        minutes_factor = 0.7
    # Combine all factors
    return base_score * fixture_factor * risk_factor * form_factor * minutes_factor

player_scores = []
for p in players:
    if p['element_type'] not in POSITION_MAP:
        continue  # Skip unknown types
    pos = POSITION_MAP[p['element_type']]
    # Attacking score: goals + assists + bonus (+ xG/xA if available)
    base_score = (
        float(p.get('expected_goals', 0)) +
        float(p.get('expected_assists', 0)) +
        p['goals_scored'] +
        p['assists'] +
        p['bonus']
    )
    # For GK, use clean sheets and bonus
    if pos == 'GK':
        base_score = p['clean_sheets'] * 2 + p['bonus']
    avg_diff = get_next3_avg_difficulty(p['team'])
    chance_playing = p.get('chance_of_playing_next_round')
    flagged = p.get('status') not in ("a", None, "")  # 'a' = available
    form = p.get('form', 5)  # default to 5 if missing
    minutes = p.get('minutes', 0)
    score = adjusted_score(base_score, avg_diff, chance_playing, flagged, form, minutes)
    price_m = p['now_cost'] / 10
    value = score / price_m if price_m else 0
    player_scores.append({
        'id': p['id'],
        'name': f"{p['first_name']} {p['second_name']}",
        'pos': pos,
        'team': get_team_name(p['team']),
        'price': p['now_cost'],
        'score': score,
        'value': value,
        'club_id': p['team'],
        'raw': p,
        'base_score': base_score,
        'avg_diff': avg_diff,
        'chance_playing': chance_playing,
        'flagged': flagged,
        'form': form,
        'minutes': minutes
    })

# Sort by value (score per million), then by score, for outfield players; GKs sorted by score
player_scores.sort(key=lambda x: (x['pos'] == 'GK', -x['value'] if x['pos'] != 'GK' else 0, -x['score']))

# --- SQUAD SELECTION: Use real FPL team if TEAM_ID is set, else use virtual XV ---
if TEAM_ID:
    # Fetch your real FPL team for the current GW
    # Get current GW (event) from bootstrap-static
    current_gw = data['events'][0]['id']
    for event in data['events']:
        if event.get('is_current'):
            current_gw = event['id']
            break
    picks_url = f"https://fantasy.premierleague.com/api/entry/{TEAM_ID}/event/{current_gw}/picks/"
    entry_url = f"https://fantasy.premierleague.com/api/entry/{TEAM_ID}/"
    picks = requests.get(picks_url).json()
    entry = requests.get(entry_url).json()
    # Map element IDs to player info
    id_to_player = {p['id']: p for p in player_scores}
    squad = [id_to_player[pick['element']] for pick in picks['picks'] if pick['element'] in id_to_player]
    # Starting 11: is_captain/is_vice_captain flags
    starting_11 = [id_to_player[pick['element']] for pick in picks['picks'] if pick['position'] <= 11 and pick['element'] in id_to_player]
    bench = [id_to_player[pick['element']] for pick in picks['picks'] if pick['position'] > 11 and pick['element'] in id_to_player]
    # Captain/vice
    captain = next((id_to_player[pick['element']] for pick in picks['picks'] if pick.get('is_captain')), None)
    vice = next((id_to_player[pick['element']] for pick in picks['picks'] if pick.get('is_vice_captain')), None)
else:
    # Virtual XV logic (guarantee 15 players: 2 GK, 5 DEF, 5 MID, 3 FWD)
    squad = []
    club_counts = defaultdict(int)
    pos_counts = defaultdict(int)
    budget = TOTAL_BUDGET
    # Fill up to the full allowed for each position (not just minimums)
    for pos in ['GK', 'DEF', 'MID', 'FWD']:
        for p in filter(lambda x: x['pos'] == pos, player_scores):
            if (pos_counts[pos] < POSITION_LIMITS[pos] and
                club_counts[p['club_id']] < MAX_FROM_CLUB and
                budget - p['price'] >= 0 and
                p not in squad):
                squad.append(p)
                pos_counts[pos] += 1
                club_counts[p['club_id']] += 1
                budget -= p['price']
            if len(squad) == 15:
                break
        if len(squad) == 15:
            break
    # If not yet 15, fill remaining spots with best value players regardless of position (shouldn't happen, but just in case)
    if len(squad) < 15:
        for p in player_scores:
            if p not in squad and club_counts[p['club_id']] < MAX_FROM_CLUB and budget - p['price'] >= 0:
                squad.append(p)
                pos_counts[p['pos']] += 1
                club_counts[p['club_id']] += 1
                budget -= p['price']
            if len(squad) == 15:
                break
    # Starting 11: 1 GK, 3 DEF, 4 MID, 3 FWD (most attacking possible)
    starting_11 = []
    counts = {'GK': 0, 'DEF': 0, 'MID': 0, 'FWD': 0}
    limits = {'GK': 1, 'DEF': 3, 'MID': 4, 'FWD': 3}
    for pos in ['FWD', 'MID', 'DEF', 'GK']:
        for p in filter(lambda x: x['pos'] == pos, squad):
            if counts[pos] < limits[pos]:
                starting_11.append(p)
                counts[pos] += 1
            if len(starting_11) == 11:
                break
        if len(starting_11) == 11:
            break
    bench = [p for p in squad if p not in starting_11]
    captain = max(starting_11, key=lambda x: x['value'])
    vice = sorted(starting_11, key=lambda x: x['value'], reverse=True)[1]

# Find the highest value per million in the squad for percentage calculation
max_value = max(p['value'] for p in squad) if squad else 1

# Format message for Starting XI
message_xi = "<b>📊 DFGFPL_bot: Pre-Season Attacking XV Draft (Next 3 GWs, risk, minutes weighted)</b>\n\n"
message_xi += f"<b>Budget used:</b> £{(TOTAL_BUDGET-budget)/10:.1f}m / £{TOTAL_BUDGET/10:.1f}m\n\n"
message_xi += "<b>Starting XI:</b>\n"
for p in starting_11:
    percent = (p['value'] / max_value) * 100 if max_value else 0
    stat = (
        f"<b>Adj. Score:</b> {p['score']:.2f} (weighted for fixtures, risk, minutes)\n"
        f"<b>Value per £1m:</b> {p['value']:.2f} ({percent:.0f}% of squad best)\n"
        f"<b>Base Score:</b> {p['base_score']:.2f} (raw attacking/defensive output)\n"
        f"<b>Avg. Fixture Difficulty (next 3):</b> {p['avg_diff']:.2f} (1 easiest, 5 hardest)\n"
        f"<b>Minutes Last Season:</b> {p['minutes']}\n"
        f"<b>Injury/Suspension Risk:</b> {'Yes' if p['flagged'] else 'No'}\n"
        f"<b>Chance of Playing Next GW:</b> {p['chance_playing'] if p['chance_playing'] is not None else 'N/A'}%"
    )
    message_xi += f"<b>{p['pos']}</b> - {p['name']} ({p['team']}) - £{p['price']/10:.1f}m\n{stat}\n\n"

bench = [p for p in squad if p not in starting_11]
# Format message for Bench
message_bench = "<b>Bench:</b>\n"
for p in bench:
    percent = (p['value'] / max_value) * 100 if max_value else 0
    stat = (
        f"<b>Adj. Score:</b> {p['score']:.2f} (weighted for fixtures, risk, minutes)\n"
        f"<b>Value per £1m:</b> {p['value']:.2f} ({percent:.0f}% of squad best)\n"
        f"<b>Base Score:</b> {p['base_score']:.2f} (raw attacking/defensive output)\n"
        f"<b>Avg. Fixture Difficulty (next 3):</b> {p['avg_diff']:.2f} (1 easiest, 5 hardest)\n"
        f"<b>Minutes Last Season:</b> {p['minutes']}\n"
        f"<b>Injury/Suspension Risk:</b> {'Yes' if p['flagged'] else 'No'}\n"
        f"<b>Chance of Playing Next GW:</b> {p['chance_playing'] if p['chance_playing'] is not None else 'N/A'}%"
    )
    message_bench += f"<b>{p['pos']}</b> - {p['name']} ({p['team']}) - £{p['price']/10:.1f}m\n{stat}\n\n"

message_bench += "<i>Note: Squad and scores are weighted for next 3 GWs fixture difficulty, injury/suspension risk, and minutes played. Adj. Score = score x all factors. Value per £1m = Adj. Score divided by price in millions.</i>"

# Send both messages
url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
payload_xi = {
    "chat_id": CHAT_ID,
    "text": message_xi,
    "parse_mode": "HTML"
}
payload_bench = {
    "chat_id": CHAT_ID,
    "text": message_bench,
    "parse_mode": "HTML"
}
response_xi = requests.post(url, data=payload_xi)
response_bench = requests.post(url, data=payload_bench)

# --- Weekly FPL Bot Message (for in-season, but always send for testing) ---

# 1. List current XV and GW performance
latest_gw = max([e.get('event_points', 0) for e in players])
top_gw_points = max([p.get('event_points', 0) for p in players]) or 1

def get_player_gw_points(p):
    return p.get('event_points', 0)

def get_player_price_change(p):
    # FPL API: 'cost_change_event' is price change this GW in tenths of a million
    return p.get('cost_change_event', 0) / 10

def get_player_team_name(p):
    return teams[p['team']-1]['name']

message_weekly = "📝 <b>Current XV - GW Performance</b>\n"
for p in squad:
    pts = get_player_gw_points(p['raw'])
    percent = int(100 * pts / top_gw_points)
    message_weekly += f"{p['pos']} - {p['name']}: {pts} pts ({percent}%)\n"

# 2. Problem Areas (simulate: flagged, low minutes, hard fixtures, low points)
message_weekly += "\n⚠️ <b>Problem Areas</b>\n"
problems = []
for p in squad:
    reasons = []
    if p['flagged']:
        reasons.append("Injury/Suspension")
    if p['avg_diff'] > 3.5:
        reasons.append("Hard fixtures")
    if p['minutes'] < 500:
        reasons.append("Limited minutes")
    if get_player_gw_points(p['raw']) < 2:
        reasons.append("Poor GW score")
    if reasons:
        problems.append(f"- {p['name']}: {', '.join(reasons)}")
if problems:
    message_weekly += "\n".join(problems)
else:
    message_weekly += "None!"

# 3. Hot Picks (Players to Watch: top 4 in league by GW points, value, fixture ease)
message_weekly += "\n\n🔥 <b>Hot Picks (Players to Watch)</b>\n"
# Sort all players by GW points, then value, then easy fixtures
hot_candidates = sorted(players, key=lambda p: (get_player_gw_points(p), float(p.get('form', 0)), -p.get('now_cost', 0), -p.get('minutes', 0)), reverse=True)
hot_picks = []
added_names = set()
for p in hot_candidates:
    if len(hot_picks) >= 4:
        break
    name = f"{p['first_name']} {p['second_name']}"
    if name in added_names:
        continue
    team = get_player_team_name(p)
    pts = get_player_gw_points(p)
    value = (float(p.get('form', 0)) / (p['now_cost']/10)) if p['now_cost'] else 0
    avg_diff = 3  # Could be improved by mapping team_id to avg_diff, but keep simple for now
    hot_picks.append(f"- {name} ({team}): {pts} pts, Value: {value:.2f}")
    added_names.add(name)
if hot_picks:
    message_weekly += "\n".join(hot_picks)
else:
    message_weekly += "None this week."

# 4. Price Drop & Price Rise Alerts (whole league)
# Price Drop
message_weekly += "\n\n📉 <b>Price Drop Alert</b>\n"
drops = sorted(players, key=lambda p: get_player_price_change(p))[:2]
for p in drops:
    if get_player_price_change(p) < 0:
        name = f"{p['first_name']} {p['second_name']}"
        team = get_player_team_name(p)
        message_weekly += f"- {name} ({team}): £{get_player_price_change(p):.1f}m\n"
if not any(get_player_price_change(p) < 0 for p in drops):
    message_weekly += "No significant drops.\n"
# Price Rise
message_weekly += "\n📈 <b>Price Rise Alert</b>\n"
rises = sorted(players, key=lambda p: get_player_price_change(p), reverse=True)[:2]
for p in rises:
    if get_player_price_change(p) > 0:
        name = f"{p['first_name']} {p['second_name']}"
        team = get_player_team_name(p)
        message_weekly += f"- {name} ({team}): +£{get_player_price_change(p):.1f}m\n"
if not any(get_player_price_change(p) > 0 for p in rises):
    message_weekly += "No significant rises.\n"

# 5. Suggestions (simulate: sub in/out, chip, unchanged)
message_weekly += "\n💡 <b>Suggestions</b>\n"
suggestions = []
for p in squad:
    if p['flagged']:
        suggestions.append(f"Sub OUT: {p['name']} (injury/suspension)")
    elif get_player_gw_points(p['raw']) < 2 and p['avg_diff'] > 3.5:
        suggestions.append(f"Sub OUT: {p['name']} (bad form, hard fixtures)")
for p in player_scores:
    if p['value'] > 3.0 and not any(p['name'] == s['name'] for s in squad):
        suggestions.append(f"Sub IN: {p['name']} (great value)")
        break
if not suggestions:
    suggestions.append("Leave team unchanged")
message_weekly += "\n".join(suggestions)

# 6. Suggested Starting XI & Captain
message_weekly += "\n\n🏆 <b>Suggested Starting XI</b>\n"
for p in starting_11:
    message_weekly += f"{p['pos']} - {p['name']}\n"
captain = max(starting_11, key=lambda x: x['value'])
message_weekly += f"\n👑 <b>Captain:</b> {captain['name']}"
vice = sorted(starting_11, key=lambda x: x['value'], reverse=True)[1]
message_weekly += f"\n🥈 <b>Vice:</b> {vice['name']}"

# 7. Gameweek Deadline (simulate: show placeholder)
message_weekly += "\n\n⏰ <b>Next GW Deadline:</b> See FPL site for details."

# Send weekly message
payload_weekly = {
    "chat_id": CHAT_ID,
    "text": message_weekly,
    "parse_mode": "HTML"
}
requests.post(url, data=payload_weekly)
