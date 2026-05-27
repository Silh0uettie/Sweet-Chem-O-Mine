@echo off
setlocal

"%PYTHON%" -m pip install "%SRC_DIR%" --no-deps --no-build-isolation -vv
if errorlevel 1 exit /b 1

if not exist "%PREFIX%\Menu" mkdir "%PREFIX%\Menu"
copy /Y "%RECIPE_DIR%\sweet-chem-o-mine.json" "%PREFIX%\Menu\sweet-chem-o-mine.json"
if errorlevel 1 exit /b 1
copy /Y "%SRC_DIR%\packaging\windows\app_icon.ico" "%PREFIX%\Menu\sweet-chem-o-mine.ico"
if errorlevel 1 exit /b 1

exit /b 0
