from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# Definir las palabras clave
keywords = ["Full Album", "Full EP", "OFFICIAL EP STREAM", "OFFICIAL ALBUM STREAM", "split", "SPLIT", "FULL ALBUM", "FULL EP", "official ep stream", "official album stream", "split CD", "Demo", "DEMO", "Full DEMO"]

# Iniciar el navegador
driver = webdriver.Firefox()

# Leer el archivo HTML con los enlaces de búsqueda
with open('busqueda.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Analizar el HTML
soup = BeautifulSoup(content, 'html.parser')

# Abrir el archivo de salida
with open('aprobadas.txt', 'w', encoding='utf-8') as out_file:
    # Iterar sobre todos los enlaces de búsqueda
    for search_link in soup.find_all('a'):
        # Navegar a la página de resultados de la búsqueda
        driver.get(search_link.get('href'))

        # Esperar a que se carguen los enlaces de los videos
        video_links = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.ID, 'video-title'))
        )

        # Variable para controlar si se ha encontrado un video válido
        valid_video_found = True

        # Filtrar los enlaces de los videos
        for video_link in video_links[:3]:  # Limitar la búsqueda a los primeros 3 videos
            title = video_link.get_attribute('title')
            if any(keyword in title for keyword in keywords):
                valid_video_found = False
                break  # Salir del bucle una vez que se encuentra un video inválido

        if valid_video_found:
            approved_search = search_link.text
            print(approved_search)
            # Escribir el nombre de la búsqueda aprobada en el archivo de salida
            out_file.write(approved_search + '\n')

# Cerrar el navegador
driver.quit()