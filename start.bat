@echo off
REM Set this to your local Kafka installation directory!
set KAFKA_DIR=C:\kafka

echo Starting Kafka in KRaft mode...
start cmd /k "cd /d %KAFKA_DIR% && .\bin\windows\kafka-server-start.bat .\config\server.properties"

echo Waiting for Kafka to initialize...
timeout /t 5 /nobreak >nul

echo Starting Vector Engine Backend...
start cmd /k ".\venv\Scripts\uvicorn.exe main:app --reload"

echo Starting Kafka Vectorization Worker...
start cmd /k ".\venv\Scripts\python.exe -m engine.worker"

echo Starting Vector Engine Frontend...
start cmd /k "cd frontend && npm run dev"

echo All services are starting up! You can close this window if you want, but keep the new command windows open to keep the servers running.
