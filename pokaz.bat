@echo off
rem Pokaz na zajeciach: publiczny adres https (Tailscale Funnel) prowadzi do serwera aplikacji na porcie 8000.
rem Serwer slucha tylko na tym komputerze (127.0.0.1) - z zewnatrz wchodzi sie wylacznie przez adres Funnel.
set TS="C:\Program Files\Tailscale\tailscale.exe"
%TS% funnel --bg 8000
%TS% funnel status
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
