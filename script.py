from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
import time

website = "https://deathgrind.club/"

# Configurar Selenium para usar Firefox en modo headless
options = Options()
options.headless = True
driver = webdriver.Firefox(options=options)

# Navegar a la página web
driver.get(website)

# Hacer scroll varias veces para cargar más contenido
for _ in range(5):  # Cambia este número según cuántas veces quieras hacer scroll
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)  # Esperar a que se cargue más contenido

# Obtener el contenido de la página
page_content = driver.page_source

# Crear un objeto BeautifulSoup con el contenido de la página
soup = BeautifulSoup(page_content, 'html.parser')

# Encontrar todos los elementos `a` con el atributo `title`
elements = soup.find_all('a', title=True)

# Iterar sobre estos elementos y extraer el valor del atributo `title`
for element in elements:
    title = element['title']
    print(title)

# Cerrar el navegador
driver.quit()