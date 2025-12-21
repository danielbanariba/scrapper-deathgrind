from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Crear un objeto WebDriver con el navegador de tu elección
driver = webdriver.Firefox()

# Navegar a la página web
driver.get("file:///C:/Users/banar/Downloads/DeathGrindClub.htm")

# Hacer scroll varias veces para cargar más contenido
for _ in range(10):  # Cambia este número según tus necesidades
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)  # Esperar un poco para que se cargue el contenido

# Crear un objeto BeautifulSoup con el contenido de la página
soup = BeautifulSoup(driver.page_source, 'html.parser')

# Encontrar todos los elementos `a` con el atributo `title`
elements = soup.find_all('a', title=True)

# Iterar sobre estos elementos y extraer el valor del atributo `title`
for element in elements:
    title = element['title']
    print(title)

# Cerrar el navegador
driver.quit()



# Cuando el programa funcione correctamente y extraiga la mayor cantidad de titulos posible, lo que sigue hacer es:
# 1. automatizar la busqueda, va agarrar el titulo, lo va a ingresar en el buscador de youtube y va a guardar el link de los resultados, pero, no va abrir ningun link
# con el link se va a generar un html con el titlo y la url del video quedaria mas o menos asi: <a href="https://www.youtube.com/results?search_query=Carcass+-+Heartwork+(Full+Album)">Carcass - Heartwork (Full Album)</a>
# 2. para que con el html generado pueda venir yo facilmente y abrir link por link para ver que descargar y que no
# 3. Tener alguna opcion o algo donde los que ya busque, no me vuelva aparecer, hacer una comparacion de titulos, y decir "Caracass - Heartwork (Full Album) ya lo busque" entonces ignorarlo en la nueva lista que haga, para de esa forma evitar duplicados
# 4. hacer que el programa se ejecute cada cierto tiempo, para que se actualice la lista de titulos, y asi no tener que estar yo ejecutando el programa cada vez que quiera actualizar la lista de titulos
# 5. Crear 3 listas de titulos, la primera es cuando se guardan todos los titulos de los albumes
        # la segunda es cuando se guardan los titulos de los albumes que ya se buscaron en youtube
        # La tercera es cuando se verifica si ya se busco ese titulo en youtube, si ya se busco, se ignora, si no se busca y se guarda en la segunda lista