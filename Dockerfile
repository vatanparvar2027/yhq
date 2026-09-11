FROM python:3.12-slim

# Tizim to'plamlari va ffmpeg o'rnatish
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Ishchi papka
WORKDIR /app

# Kutubxonalarni o'rnatish (cache uchun avval)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Loyiha fayllarini ko'chirish
COPY . .

# downloads papkasini yaratish
RUN mkdir -p downloads

# Botni ishga tushirish
CMD ["python", "main.py"]
