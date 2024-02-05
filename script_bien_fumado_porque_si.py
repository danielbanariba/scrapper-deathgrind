from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# Configurar opciones de Chrome
options = Options()
options.add_argument("--start-maximized")  # Iniciar Chrome maximizado

# Iniciar el navegador
driver = webdriver.Chrome(options=options)

# Leer el archivo con los enlaces
with open('link_descargar.txt', 'r', encoding='utf-8') as file:
    for link in file:
        # Abrir cada enlace en una nueva pestaña
        driver.execute_script(f"window.open('{link.strip()}');")

input("Presiona Enter para cerrar el script...")  # Agregar una pausa al final