@echo off
chcp 65001 >nul
rem "סדר מהמודל" v6.4 - מתקין סידור אוטומטי שפועל ברקע ומתחיל עם המחשב
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0..\מערכת"
if not exist "bin-win\MoodleSorter.exe" goto python
rem the program itself - no Python needed
bin-win\MoodleSorter.exe --install
echo.
pause
exit /b

:python
set PY=
where py >nul 2>nul && py -3 -c "import sys" >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && python -c "import sys" >nul 2>nul && set PY=python
if not defined PY goto nopython
%PY% sort_downloads.py --install
echo.
pause
exit /b

:nopython
powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; $r=[System.Windows.MessageBox]::Show(('Python לא מותקן במחשב, והכלי צריך אותו.', '', 'להתקין אותו עכשיו? (לוקח כמה דקות, בלי הרשאות מנהל)', '', 'אפשר גם להתקין לבד מ-python.org - ובהתקנה לסמן Add python.exe to PATH.') -join [char]10, 'סדר מהמודל', 'YesNo', 'Question', 'Yes', 'RtlReading'); if ($r -eq 'Yes') { exit 1 } else { exit 0 }"
if errorlevel 1 goto winget
exit /b

:winget
echo Installing Python (winget)...
winget install -e --id Python.Python.3.12 --scope user
powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; $r=[System.Windows.MessageBox]::Show(('אם ההתקנה הצליחה: לחצו שוב לחיצה כפולה על אותו קובץ.', '', 'אם לא: התקינו מ-python.org ולחצו שוב.') -join [char]10, 'סדר מהמודל', 'OK', 'Information', 'Yes', 'RtlReading'); if ($r -eq 'Yes') { exit 1 } else { exit 0 }"
