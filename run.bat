@echo off
cd /d "%~dp0"
pip install -r requirements.txt --quiet
streamlit run app.py
