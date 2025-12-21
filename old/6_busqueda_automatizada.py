from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re

# Definir las palabras clave
#keywords_EP = ["full ep", "official ep stream", "full ep stream", "full length ep", "ep stream", "full e.p", "full-length ep", "full lenght ep"]

keywords = [
    "full album", "official album stream", "full album stream",
    "full length", "full length album", "album stream", "full a.l.b.u.m",
    "full-album", "album full", "full lenght", "full lenght album",
    "full-length album", "full-length album", "full death metal album", "offical album premiere",
    "full-length", "full", "album", "premiere", "full album premiere"
]

# Leer el archivo HTML con los enlaces de búsqueda
with open('busqueda.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Analizar el HTML
soup = BeautifulSoup(content, 'html.parser')

# Abrir el archivo de salida
with open('bandas-aprobadas.txt', 'w', encoding='utf-8') as out_file:
    # Inicializar el contador
    search_counter = 0

    # Iniciar el navegador
    options = Options()
    options.headless = True
    driver = webdriver.Chrome(options=options)

    for search_link in soup.find_all('a'):
        driver.get(search_link.get('href'))
        valid_search = True  # Asumir que la búsqueda es válida

        try:
            # Esperar a que los títulos de los videos estén presentes
            WebDriverWait(driver, 120).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a#video-title yt-formatted-string"))
            )
            video_titles = driver.find_elements(By.CSS_SELECTOR, "a#video-title yt-formatted-string")

            analyzed_videos = 0
            for video_title in video_titles:
                if analyzed_videos >= 3:
                    break

                # Obtener el texto visible del título (no el atributo "title")
                title = video_title.text.strip().lower()
                print(f"Analizando título: {title}")  # Depuración

                # Verificar si alguna palabra clave está presente
                if any(keyword in title for keyword in keywords):
                    valid_search = False
                    print(f"Palabra clave encontrada: {title}")  # Depuración
                    break  # Descartar la búsqueda inmediatamente

                analyzed_videos += 1

        except TimeoutException:
            valid_search = False
            print("Timeout al cargar los videos.")

        # Escribir solo si no se encontraron palabras clave
        if valid_search:
            approved_search = search_link.text
            print(f"Aprobado: {approved_search}")
            out_file.write(approved_search + '\n')

        search_counter += 1

        if search_counter >= 250:
            driver.quit()
            search_counter = 0
            driver = webdriver.Chrome(options=options)

    driver.quit()