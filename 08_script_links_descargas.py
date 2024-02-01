from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Abre el archivo con los enlaces
with open('links_bandas_corregidos.txt', 'r', encoding='utf-8') as file:
    links = file.readlines()

# Inicia un navegador Chrome con Selenium
driver = webdriver.Chrome()

# Abre el archivo donde se guardarán los enlaces encontrados
with open('links_para_descargar.txt', 'w', encoding='utf-8') as output:
    # Para cada enlace
    for link in links:
        # Navega al enlace con Selenium
        driver.get(link.strip())
        # Espera a que se cargue el botón con el nombre de la clase
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'dgc-1x1y7r3.emyorhn0')))
        # Encuentra todos los enlaces dentro de este botón
        buttons = driver.find_elements_by_css_selector('dgc-1x1y7r3.emyorhn0 a')
        for button in buttons:
            # Extrae el atributo 'href' de cada enlace
            href = button.get_attribute('href')
            # Guarda estos enlaces en el archivo
            output.write(href + '\n')

# Cierra el navegador Chrome
driver.quit()