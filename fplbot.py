import requests

BOT_TOKEN = "7866601514:AAEsJRyRnfPV_IKgjMIHrUbaKGxcIGLS35g"
CHAT_ID = "7529074378"

message = """
📊 DFGFPL_bot: Daily Intel Drop

🦴 Problem Areas:
- Rashford – 2.3 form, rotation risk 📉
- Gabriel – 1.8 form, benched 📉
- Mitoma – 3.2 form, tough fixtures 📉

🔥 Hot Picks on the Rise:
- Bowen – 8.1 form, fixtures: BOU (H), LUT (A), FUL (H)
- Eze – 7.4 form, fixtures: SHE (H), BRE (A), WOL (H)
- Morris – 6.9 form, fixtures: BUR (A), EVE (H), NFO (A)

🎯 Suggestion Summary:
- Transfer OUT: Rashford, Gabriel
- Transfer IN: Bowen, Eze
- Captain Pick: Haaland (vs Luton, H)
- VC: Bowen
- 💰 Price Watch: Garnacho rise likely tonight

🕖 Deadline in 3d 14h — early moves optional, but monitor news.
"""

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
payload = {
    "chat_id": CHAT_ID,
    "text": message,
    "parse_mode": "HTML"
}

requests.post(url, data=payload)
