# Guía de Despliegue en la Nube - Egasis Studio

Esta guía te explica cómo subir **Egasis Studio** a la nube para que funcione 24/7 sin depender de que tu computadora local esté encendida.

Dado que la aplicación incluye navegadores autónomos (Playwright) para el scraping de Google Maps, el despliegue mediante **Docker** es el método más estable y recomendado. El archivo `Dockerfile` ya está preconfigurado con la imagen oficial de Playwright.

---

## Opción 1: Despliegue en Render (Recomendado)

Render es una plataforma muy sencilla para alojar aplicaciones web con soporte para Docker.

### 1. Preparar el repositorio
Asegúrate de tener el código del proyecto en un repositorio privado de GitHub o GitLab.

### 2. Crear un "Web Service" en Render
1. Ve a tu panel de [Render](https://dashboard.render.com/) y haz clic en **New +** -> **Web Service**.
2. Conecta tu repositorio de GitHub y selecciona la rama correspondiente.
3. Configura los siguientes campos:
   - **Runtime**: `Docker`
   - **Instance Type**: Selecciona el plan que prefieras (se recomienda al menos 1 GB o 2 GB de RAM para que la ejecución de Playwright sea fluida).

### 3. Configurar Almacenamiento Persistente (¡CRÍTICO!)
SQLite guarda la base de datos localmente en un archivo llamado `outreach.db`. Si no usas un disco persistente, tus datos (leads, respuestas, configuraciones) se borrarán cada vez que el servidor se reinicie.
1. En la configuración del Web Service en Render, ve a la pestaña **Disks**.
2. Haz clic en **Add Disk**.
3. Configura:
   - **Name**: `outreach-db-volume`
   - **Mount Path**: `/app/data`
   - **Size**: `1 GiB` (es más que suficiente para SQLite).
4. Guarda los cambios.
5. Ve a la pestaña **Environment** y añade esta variable de entorno para indicarle a la app que guarde la base de datos en el disco persistente:
   - `DB_PATH=/app/data/outreach.db`

### 4. Configurar Variables de Entorno
En la pestaña **Environment**, añade todas las variables definidas en tu archivo `.env`:
- `GEMINI_API_KEY`: Tu clave de Google Gemini (¡Crítica!).
- `SMTP_EMAIL`: Tu correo de Gmail para el envío.
- `SMTP_PASSWORD`: Tu contraseña de aplicación de Gmail (16 caracteres).
- `SMTP_SERVER`: `smtp.gmail.com`
- `SMTP_PORT`: `587`
- `IMAP_SERVER`: `imap.gmail.com`
- `IMAP_PORT`: `993`
- `DAILY_LIMIT`: `80`
- `WORK_HOUR_START`: `8`
- `WORK_HOUR_END`: `18`
- `SIMULATION_MODE`: `False` (para enviar correos reales)

---

## Opción 2: Despliegue en Railway

Railway es otra excelente alternativa con soporte nativo para Docker.

1. Crea un nuevo proyecto en [Railway](https://railway.app/).
2. Selecciona **Deploy from GitHub repo** y conecta tu repositorio.
3. En la configuración del servicio:
   - Railway detectará automáticamente el `Dockerfile` y compilará la imagen.
4. **Agregar volumen persistente (Disk)**:
   - Ve a **Settings** -> **Volumes** y añade un volumen persistente.
   - Móntalo en `/app/data`.
   - Agrega la variable de entorno `DB_PATH=/app/data/outreach.db`.
5. Agrega las variables de entorno restantes (las mismas de la sección de Render).

---

## Opción 3: Despliegue en un VPS Propio (Ubuntu/Debian)

Si prefieres usar un servidor propio (DigitalOcean, AWS, Linode, etc.) con Docker Compose:

1. **Instalar Docker y Docker Compose** en el servidor:
   ```bash
   sudo apt update
   sudo apt install docker.io docker-compose -y
   ```
2. **Subir los archivos del proyecto** al servidor (puedes clonarlo usando git).
3. **Crear o editar el archivo `.env`** en la carpeta del proyecto en el VPS con tus credenciales reales.
4. **Iniciar el contenedor**:
   ```bash
   docker-compose up -d --build
   ```
5. Esto compilará e iniciará el contenedor automáticamente en segundo plano en el puerto `8000`.

---

## Consejos de Producción y Mantenimiento

* **Contraseña de Aplicación**: Recuerda que en Gmail debes activar la *Verificación en 2 pasos* y crear una *Contraseña de Aplicación* específica para Egasis Studio. Nunca uses tu contraseña personal directamente.
* **Logs del Contenedor**: Puedes revisar qué está haciendo el robot o el scraper en tiempo real mediante los logs de Render/Railway o ejecutando `docker logs -f egasis_studio` en tu VPS.
* **Copia de seguridad**: Se recomienda descargar periódicamente el archivo `outreach.db` desde el volumen persistente como backup de seguridad de tus leads e historial.
