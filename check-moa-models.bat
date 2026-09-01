@echo off
:: Monitor :free models used by the MoA scheme (no API key needed).
python "%~dp0check-moa-models.py" %*
exit /b %ERRORLEVEL%
