========================================
  SceneCut Pro — Student Pack
  AI Movie Scene Cutter
========================================

Yeh pack aap PC pe install karke use kar sakte ho.
Phone pe sirf LIVE DEMO chalega (browser link).


A) LIVE DEMO (browser — install ki zaroorat nahi)
------------------------------------------------
Teacher / cloud link open karo, phir:
  1) Load Sample
  2) Auto Cut Scenes
Mobile pe bhi same link chalega.


B) WINDOWS PC PE INSTALL (students ke liye)
------------------------------------------
Zaroori:
  • Python 3.10+   https://www.python.org/downloads/
    Install ke dauran "Add python.exe to PATH" CHECK karo
  • ffmpeg         terminal mein:
                   winget install Gyan.FFmpeg

Phir:
  1) Is zip ko extract karo
  2) INSTALL_WINDOWS.bat par double-click
  3) Desktop pe "SceneCut Pro+" shortcut aa jayegi
  4) Shortcut open karo → Load Sample → Auto Cut


C) BINAA INSTALL (quick test)
-----------------------------
  1) Python + ffmpeg install hon
  2) Folder mein command open karke:
       pip install -r requirements.txt
       python app.py
  3) Browser: http://127.0.0.1:5000


D) FILES
--------
  INSTALL_WINDOWS.bat     ← Windows install (recommended)
  desktop\INSTALL.bat     ← same installer
  desktop\UNINSTALL.bat   ← remove
  start.bat / start.sh    ← quick launch
  sample_*.*              ← demo movie + narration
  STUDENT_README.txt      ← yeh file


E) UNINSTALL
------------
  desktop\UNINSTALL.bat
  ya Start Menu → SceneCut Pro+ → Uninstall


Support tip:
  Video cut ke liye ffmpeg PATH pe hona zaroori hai.
  Agar Auto Cut fail ho: ffmpeg -version check karo.

========================================
