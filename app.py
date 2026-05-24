import streamlit as st
import requests
import pandas as pd
from datetime import date, timedelta

# Set page configuration
st.set_page_config(page_title="Wettenstrat", page_icon="⚾", layout="wide")

st.title("⚾ Wettenstrat")
st.write("Retrieve live and historical inning-by-inning box scores using the MLB Stats API.")

# Define Tabs
tab1, tab2 = st.tabs(["Daily Scores", "High 0-Run Chance Inning"])

# ==========================================
# HELPER FUNCTIONS 
# ==========================================
@st.cache_data(ttl=60)
def fetch_mlb_scores(game_date):
    date_str = game_date.strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&hydrate=linescore"
    response = requests.get(url)
    if response.status_code != 200: return []
    data = response.json()
    if not data.get('dates'): return []
    
    games = data['dates'][0]['games']
    game_data = []
    
    for game in games:
        status = game['status']['detailedState']
        away_team = game['teams']['away']['team']['name']
        home_team = game['teams']['home']['team']['name']
        
        linescore = game.get('linescore', {})
        innings = linescore.get('innings', [])
        
        away_runs = {'Team': away_team, 'R': game['teams']['away'].get('score', 0)}
        home_runs = {'Team': home_team, 'R': game['teams']['home'].get('score', 0)}
        
        for inning in innings:
            num = str(inning['num'])
            away_runs[num] = inning['away'].get('runs', '')
            home_runs[num] = inning['home'].get('runs', '')
            
        game_data.append((status, away_runs, home_runs))
    return game_data

@st.cache_data(ttl=86400)
def get_mlb_teams():
    url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    response = requests.get(url).json()
    teams = {t['name']: t['id'] for t in sorted(response['teams'], key=lambda x: x['name']) if t['sport']['id'] == 1}
    return teams

@st.cache_data(ttl=3600)
def get_upcoming_matches():
    """Fetches upcoming matches for the next 3 days for quick selection."""
    start_d = date.today()
    end_d = start_d + timedelta(days=2)
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={start_d.strftime('%Y-%m-%d')}&endDate={end_d.strftime('%Y-%m-%d')}"
    
    res = requests.get(url).json()
    matches = []
    
    if res.get('dates'):
        for date_obj in res['dates']:
            game_date = date_obj['date']
            for game in date_obj['games']:
                away = game['teams']['away']['team']['name']
                home = game['teams']['home']['team']['name']
                matches.append({
                    'label': f"{game_date} : {away} @ {home}",
                    'away': away,
                    'home': home
                })
    return matches

@st.cache_data(ttl=3600)
def fetch_0_run_innings(team_id, start_year, end_year):
    stats = {str(i): {'played': 0, 'zero_runs': 0} for i in range(1, 10)}
    
    for year in range(start_year, end_year + 1):
        url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId={team_id}&startDate={year}-01-01&endDate={year}-12-31&hydrate=linescore&gameType=R,P"
        res = requests.get(url)
        if res.status_code != 200: continue
        
        data = res.json()
        if not data.get('dates'): continue
        
        for date_obj in data['dates']:
            for game in date_obj['games']:
                if 'linescore' not in game: continue
                
                is_away = game['teams']['away']['team']['id'] == team_id
                team_side = 'away' if is_away else 'home'
                
                for inning in game['linescore'].get('innings', []):
                    num = str(inning['num'])
                    if num not in stats: continue
                    
                    inning_data = inning.get(team_side, {})
                    if 'runs' in inning_data:
                        stats[num]['played'] += 1
                        if inning_data['runs'] == 0:
                            stats[num]['zero_runs'] += 1
    return stats

def get_last_h2h_match(team_a_id, team_b_id):
    today = date.today().strftime('%Y-%m-%d')
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId={team_a_id}&opponentId={team_b_id}&startDate=2000-01-01&endDate={today}"
    res = requests.get(url).json()
    
    if not res.get('dates'): return None
    
    past_dates = [d for d in res['dates'] if d['games'][0]['status']['abstractGameState'] == 'Final']
    if not past_dates: return None
    
    last_game = past_dates[-1]['games'][-1]
    away = last_game['teams']['away']
    home = last_game['teams']['home']
    game_date = past_dates[-1]['date']
    
    return f"{game_date}: {away['team']['name']} ({away.get('score', 0)}) @ {home['team']['name']} ({home.get('score', 0)})"

# ==========================================
# TAB 1: DAILY SCORES
# ==========================================
with tab1:
    st.header("Daily Scoreboard")
    selected_date = st.date_input("Select Game Date", date.today())
    games = fetch_mlb_scores(selected_date)

    if not games:
        st.info(f"No games found for {selected_date}.")
    else:
        for status, away, home in games:
            st.subheader(f"{away['Team']} @ {home['Team']}")
            st.caption(f"Status: {status}")
            
            df = pd.DataFrame([away, home])
            inning_cols = [str(i) for i in range(1, 20) if str(i) in df.columns]
            ordered_cols = ['Team'] + inning_cols + ['R']
            
            st.dataframe(df[ordered_cols], hide_index=True, use_container_width=True)
            st.divider()

# ==========================================
# TAB 2: HIGH 0-RUN CHANCE INNING
# ==========================================
with tab2:
    st.header("High 0-Run Chance Inning Analyzer")
    st.write("Compare how often teams fail to score (0 runs) in specific innings (1st - 9th).")
    
    teams_dict = get_mlb_teams()
    team_names = list(teams_dict.keys())
    
    # 1. Upcoming Matches Quick Select
    upcoming_matches = get_upcoming_matches()
    match_labels = ["-- Manual Selection --"] + [m['label'] for m in upcoming_matches]
    
    st.markdown("### Matchup Selection")
    match_selection = st.selectbox("Quick Select: Upcoming Match", match_labels)
    
    if match_selection == "-- Manual Selection --":
        col1, col2 = st.columns(2)
        with col1:
            team_a_name = st.selectbox("Select Team", team_names, index=0)
        with col2:
            team_b_name = st.selectbox("Select Team to Compare To", team_names, index=1)
    else:
        # Extract selected match details
        selected_match_data = next(m for m in upcoming_matches if m['label'] == match_selection)
        team_a_name = selected_match_data['away']
        team_b_name = selected_match_data['home']
        
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**Away Team:** {team_a_name}")
        with col2:
            st.info(f"**Home Team:** {team_b_name}")
            
    team_a_id = teams_dict.get(team_a_name)
    team_b_id = teams_dict.get(team_b_name)
    
    st.markdown("### Filters")
    f_col1, f_col2, f_col3 = st.columns(3)
    
    current_year = date.today().year
    with f_col1:
        season_filter = st.selectbox(
            "Timeframe", 
            ["Current Season", "Include Last Season", "5 Seasons", "10 Seasons", "All Time"]
        )
    with f_col2:
        format_filter = st.radio("Display Format", ["Count", "Percentage"], horizontal=True)
    with f_col3:
        show_last_match = st.checkbox("Show Last Head-to-Head Result", value=True)
        
    if season_filter == "Current Season":
        s_year, e_year = current_year, current_year
    elif season_filter == "Include Last Season":
        s_year, e_year = current_year - 1, current_year
    elif season_filter == "5 Seasons":
        s_year, e_year = current_year - 4, current_year
    elif season_filter == "10 Seasons":
        s_year, e_year = current_year - 9, current_year
    elif season_filter == "All Time":
        s_year, e_year = 1998, current_year
        st.warning("⚠️ 'All Time' is capped back to 1998 (Modern Expansion Era) to ensure stable loading times.")

    if show_last_match and team_a_id and team_b_id:
        last_match = get_last_h2h_match(team_a_id, team_b_id)
        if last_match:
            st.success(f"**Last Head-to-Head Match:** {last_match}")
        else:
            st.info("**Last Head-to-Head Match:** No recent matches found.")

    if st.button("Generate Inning Data", type="primary"):
        if not team_a_id or not team_b_id:
            st.error("Error identifying teams. Please ensure MLB team names are matching correctly.")
        else:
            with st.spinner(f"Fetching play data from {s_year} to {e_year}..."):
                team_a_stats = fetch_0_run_innings(team_a_id, s_year, e_year)
                team_b_stats = fetch_0_run_innings(team_b_id, s_year, e_year)
                
                a_row = {"Team": team_a_name}
                b_row = {"Team": team_b_name}
                
                for i in range(1, 10):
                    inning = str(i)
                    
                    a_played = team_a_stats[inning]['played']
                    a_zeros = team_a_stats[inning]['zero_runs']
                    if a_played == 0:
                        a_row[inning] = "0" if format_filter == "Count" else "0%"
                    elif format_filter == "Count":
                        a_row[inning] = f"{a_zeros} / {a_played}"
                    else:
                        a_row[inning] = f"{round((a_zeros / a_played) * 100, 1)}%"

                    b_played = team_b_stats[inning]['played']
                    b_zeros = team_b_stats[inning]['zero_runs']
                    if b_played == 0:
                        b_row[inning] = "0" if format_filter == "Count" else "0%"
                    elif format_filter == "Count":
                        b_row[inning] = f"{b_zeros} / {b_played}"
                    else:
                        b_row[inning] = f"{round((b_zeros / b_played) * 100, 1)}%"
                        
                df_zeros = pd.DataFrame([a_row, b_row])
                ordered_inning_cols = ['Team', '1', '2', '3', '4', '5', '6', '7', '8', '9']
                
                st.markdown(f"#### 0-Run Inning Frequency ({format_filter})")
                if format_filter == "Count":
                    st.caption("Displayed as: **[Zero-Run Innings] / [Total Innings Played]**")
                    
                st.dataframe(df_zeros[ordered_inning_cols], hide_index=True, use_container_width=True)