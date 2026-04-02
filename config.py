import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

SECRET_KEY = os.environ.get("SECRET_KEY", "b3a58e47c12f4d8e90a6152b1134a4c7")
DATABASE = os.path.join(BASE_DIR, "betting_tracker_v2.db")
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "81e8fc57800c725b70ac6fea14c16b9b")
