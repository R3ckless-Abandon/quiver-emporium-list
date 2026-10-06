@echo off
rem Daily local sync (run by Windows Task Scheduler): rebuild the list and push it if anything changed.
rem The site blocks GitHub's servers, so this runs from Dan's PC instead of the GitHub Action.
cd /d "%~dp0.."
>>sync.log 2>&1 call :main
exit /b

:main
echo ==== %date% %time%
git pull --ff-only || exit /b 1
python scripts\build_list.py || exit /b 1
git add lists
git diff --cached --quiet -- lists && (echo No changes.& exit /b 0)
git commit -m "Update Gaming Emporium list" || exit /b 1
git push || exit /b 1
echo Pushed.
