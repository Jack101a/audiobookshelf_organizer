#!/bin/bash
cd "$(dirname "$0")"
streamlit run app.py --server.headless true --server.port 8501 &
sleep 2
google-chrome --app="http://localhost:8501" &

