import urllib.request
import json

api_key = "81e8fc57800c725b70ac6fea14c16b9b"
url = f"https://api.the-odds-api.com/v4/sports/soccer_epl/odds/?apiKey={api_key}&regions=eu,us,uk&markets=h2h"

req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        for game in data:
            print(f"{game['home_team']} vs {game['away_team']}")
except Exception as e:
    print(e)
