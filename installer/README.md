# PumpingBot Windows Installer

User ko yeh pack do (ya app se **Download Installer ZIP**):

- `PumpingBotSetup.bat` ← double-click
- `PumpingBotSetup.ps1`
- `PumpingBotFollower.mq5`
- `README.txt`

Installer automatically:
1. Finds MetaTrader / Exness data folders  
2. Copies EA → `MQL5\Experts\`  
3. Writes `MQL5\Files\pumpingbot_config.txt` (SERVER + TOKEN)  
4. Adds WebRequest URL in `config\common.ini`  
5. Tries to launch MT5  

User still does once: AutoTrading ON + drag EA on chart.
