from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# Definir las palabras clave
keywords = ["Full Album", "Full EP", "OFFICIAL EP STREAM", "OFFICIAL ALBUM STREAM"]

# Iniciar el navegador
driver = webdriver.Firefox()

# Leer el archivo HTML con los enlaces de búsqueda
with open('busqueda.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Analizar el HTML
soup = BeautifulSoup(content, 'html.parser')

# Iterar sobre todos los enlaces de búsqueda
for search_link in soup.find_all('a'):
    # Navegar a la página de resultados de la búsqueda
    driver.get(search_link.get('href'))

    # Esperar a que se carguen los enlaces de los videos
    video_links = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.ID, 'video-title'))
    )

    # Filtrar los enlaces de los videos
    for video_link in video_links:
        title = video_link.get_attribute('title')
        if any(keyword in title for keyword in keywords):
            print(video_link.get_attribute('href'))

# Cerrar el navegador
driver.quit()