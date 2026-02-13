.PHONY: run tunnel dev install

run:
	.venv/bin/python server.py

tunnel:
	ngrok http 8000 --url=ldraney.ngrok-free.app

dev:
	tmux new-session -d -s mcp 'make run' \; split-window -h 'make tunnel' \; attach

install:
	python -m venv .venv
	.venv/bin/pip install -r requirements.txt
