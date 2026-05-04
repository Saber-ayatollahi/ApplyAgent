# Start Saber's Job Search Dashboard
Set-Location $PSScriptRoot

# Open browser after a short delay (Streamlit takes ~3s to boot)
Start-Process powershell -ArgumentList "-Command", "Start-Sleep 4; Start-Process 'http://localhost:8501'" -WindowStyle Hidden

# Start Streamlit
streamlit run ui/app.py --server.headless true
