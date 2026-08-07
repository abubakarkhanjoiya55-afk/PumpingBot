# Local MT5 Agent (User PC / Admin PC)

**Default model (v3.33+):** har follower apne **Windows PC** pe yeh agent chalata hai.  
Central VPS optional hai — zaroori nahi.

- **Follower:** `START_FOLLOWER.bat` — master trades copy
- **Master (Admin99):** `START_MASTER.bat` — strategy + fan-out

Poora user guide: **`../USER_PC_SETUP.md`**

## Quick start (follower)

1. App pe MT5 connect + **PC Setup → Get Agent Token**
2. `START_FOLLOWER.bat` edit (SERVER_URL, ACCESS_TOKEN, MT5_*)
3. Bat double-click — window open rakho
4. App → **Start Bot** (daily admin unlock + 25% share clear)

```bat
pip install -r local_agent\requirements.txt
START_FOLLOWER.bat
```

## Daily 25% rule

Raat ko system aaj ke profit ka **25%** bill karta hai.  
Bina **admin approve** ke nayi copy trades **block**.  
Har PKT din ke liye unlock / approve chahiye.

## Manual env

```bat
set SERVER_URL=https://YOUR-APP.up.railway.app
set ACCESS_TOKEN=jwt-from-POST-/me/agent-token
set MT5_LOGIN=12345678
set MT5_PASSWORD=...
set MT5_SERVER=Exness-MT5Real
set MT5_PATH=
set AGENT_ROLE=follower
python local_agent\agent.py
```
