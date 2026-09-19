#comandos para levantar prueba de respuesta ok .
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload



docker compose up -d
docker compose ps
docker exec a2d_sqlserver /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "A2d_Dev_2026!" -Q "CREATE DATABASE a2d_sm"
