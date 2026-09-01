@echo off
:: Rotate a dead model out of the MoA scheme.
:: Usage: rotate-moa-model.bat <dead-model> <replacement-model>
if "%~1"=="" ( echo Usage: %~nx0 ^<dead-model^> ^<replacement-model^> & exit /b 2 )
if "%~2"=="" ( echo Usage: %~nx0 ^<dead-model^> ^<replacement-model^> & exit /b 2 )
python "%~dp0rotate-moa-model.py" "%~1" "%~2"
exit /b %ERRORLEVEL%
