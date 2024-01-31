from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from bs4 import BeautifulSoup
import time

# Leer el archivo de bandas aprobadas
with open('aprobadas.txt', 'r') as f:
    bandas_aprobadas = f.read().splitlines()

# Configurar el navegador
options = Options()
options.headless = False
driver = webdriver.Firefox(options=options)

# Lista para almacenar los links de descarga
links_descarga = []

# Recorrer los archivos HTML
for banda in bandas_aprobadas:
    driver.get('C:/Users/banar/Downloads/deathgrind_geners/*.html')
    time.sleep(2)  # Esperar a que la página cargue

    # Buscar los elementos 'a' con el atributo 'title'
    elementos = driver.find_elements_by_xpath('//a[@title]')

    # Recorrer los elementos y hacer click si el título coincide con el nombre de la banda
    for elemento in elementos:
        if elemento.get_attribute('title') == banda:
            elemento.click()
            print(f'{banda}')  # Imprimir el nombre de la banda
            time.sleep(2)  # Esperar a que la página cargue

            # Buscar el botón y hacer click
            boton = driver.find_element_by_class_name('MuiButtonBase-root')
            boton.click()
            time.sleep(2)  # Esperar a que la página cargue

            # Extraer el HTML de la página y analizarlo con BeautifulSoup
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')

            # Buscar los elementos 'span' y extraer los links de descarga
            spans = soup.find_all('span', {'aria-label': True, 'class': 'dgc-1x1y7r3 emyorhn0'})
            for span in spans:
                link = span.find('a')['href']
                links_descarga.append(link)

# Cerrar el navegador
driver.quit()

# Guardar los links de descarga en un archivo
with open('links_descarga.txt', 'w') as f:
    for link in links_descarga:
        f.write(link + '\n')