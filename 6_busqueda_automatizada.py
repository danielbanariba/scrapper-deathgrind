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

# Compilar la expresión regular para las palabras clave
keywords_regex = re.compile("|".join(keywords), re.IGNORECASE)

# Leer el archivo HTML con los enlaces de búsqueda
with open('busqueda.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Analizar el HTML
soup = BeautifulSoup(content, 'html.parser')

# Abrir el archivo de salida
with open('bandas-aprobadas.txt', 'w', encoding='utf-8') as out_file: #Cambiar el nombre del archivo de salida
    # Inicializar el contador
    search_counter = 0

    # Iniciar el navegador
    options = Options()
    options.headless = True
    driver = webdriver.Chrome(options=options)  # Use headless browser

    # Iterar sobre todos los enlaces de búsqueda
    for search_link in soup.find_all('a'):
        # Navegar a la página de resultados de la búsqueda
        driver.get(search_link.get('href'))

        try:
            # Esperar a que se carguen los enlaces de los videos
            video_links = WebDriverWait(driver, 120).until(
                EC.presence_of_all_elements_located((By.ID, 'video-title'))
            )

            # Variable para controlar si se ha encontrado un video válido
            valid_video_found = False

            # Filtrar los enlaces de los videos
            analyzed_videos = 0  # Counter for analyzed videos
            for video_link in video_links:
                # Check if the link is a playlist
                if 'ytd-playlist-renderer' in video_link.get_attribute('class'):
                    continue  # Skip this link

                # Limitar la búsqueda a los primeros 3 videos
                if analyzed_videos >= 3:
                    break

                title = video_link.get_attribute('title').lower()  # Get the title of the video
                valid_video_found = True  # Assume the video is valid until proven otherwise

                # Check the title against each keyword
                for keyword in keywords:
                    if keyword in title:
                        valid_video_found = False  # Mark the video as invalid as soon as a keyword is found
                        break  # No need to check the rest of the keywords

                analyzed_videos += 1  # Increment the counter for analyzed videos

                if not valid_video_found:
                    break  # If the video is invalid, no need to check the rest of the videos
        except TimeoutException:  # Catch TimeoutException instead of TimeoutError
            # Si no se encuentran videos dentro del tiempo valido, marcar como inválido
            valid_video_found = False

        if valid_video_found:
            approved_search = search_link.text
            print(approved_search)  # Print the approved search
            # Escribir el nombre de la búsqueda aprobada en el archivo de salida
            out_file.write(approved_search + '\n')

        search_counter += 1  # Incrementar el contador después de cada búsqueda

        if search_counter >= 250:  # Comprobar si el contador ha llegado a 50
            driver.quit()  # Cerrar el navegador
            search_counter = 0  # Reiniciar el contador
            # Aquí deberías volver a abrir el navegador
            options = Options()
            options.headless = True
            driver = webdriver.Chrome(options=options)  # Use headless browser

    # Cerrar el navegador una vez que hayas terminado todas las búsquedas
    driver.quit()