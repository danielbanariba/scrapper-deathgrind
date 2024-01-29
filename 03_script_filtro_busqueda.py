from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re

# Definir las palabras clave
keywords = ["full album", "full ep", "official ep stream", "official album stream", "split", "full split", "demo", "full demo", "full album stream", "compilation"]

# Compilar la expresión regular para las palabras clave
keywords_regex = re.compile("|".join(keywords), re.IGNORECASE)

# Leer el archivo HTML con los enlaces de búsqueda
with open('busqueda.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Analizar el HTML
soup = BeautifulSoup(content, 'html.parser')

# Abrir el archivo de salida
with open('aprobadas.txt', 'w', encoding='utf-8') as out_file:
    # Iterar sobre todos los enlaces de búsqueda
    for search_link in soup.find_all('a'):
        # Iniciar el navegador
        options = Options()
        options.headless = True
        driver = webdriver.Chrome(options=options)  # Use headless browser

        # Navegar a la página de resultados de la búsqueda
        driver.get(search_link.get('href'))

        try:
            # Esperar a que se carguen los enlaces de los videos
            video_links = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.ID, 'video-title'))
            )

            # Variable para controlar si se ha encontrado un video válido
            valid_video_found = False

            # Filtrar los enlaces de los videos
            for video_link in video_links[:3]:  # Limitar la búsqueda a los primeros 3 videos
                title = video_link.get_attribute('title')
                if keywords_regex.search(title):
                    valid_video_found = False
                    break  # Salir del bucle una vez que se encuentra un video inválido
            else:  # Se ejecuta si el bucle terminó normalmente, es decir, no se encontró ninguna palabra clave
                valid_video_found = True
        except TimeoutException:  # Catch TimeoutException instead of TimeoutError
            # Si no se encuentran videos dentro del tiempo valido, marcar como inválido
            valid_video_found = False

        if valid_video_found:
            approved_search = search_link.text
            print(approved_search)
            # Escribir el nombre de la búsqueda aprobada en el archivo de salida
            out_file.write(approved_search + '\n')

        # Cerrar el navegador
        driver.quit()