# 1. Imagen oficial de Azure Functions para Python 3.11
FROM mcr.microsoft.com/azure-functions/python:4-python3.11

# 2. Configuración para que los logs salgan directos a la terminal
ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PYTHONUNBUFFERED=1

# 3. Instalamos las dependencias
COPY requirements.txt /
RUN pip install --no-cache-dir -r /requirements.txt

# 4. Copiamos el código a la carpeta que espera Azure
COPY . /home/site/wwwroot