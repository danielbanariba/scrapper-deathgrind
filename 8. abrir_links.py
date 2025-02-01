import webbrowser
from bs4 import BeautifulSoup
import re
import random
import time

# Leer el archivo HTML
with open('links_bandas.html', 'r', encoding='utf-8') as f:
    contenido = f.read()

# Pasar el contenido a BeautifulSoup
soup = BeautifulSoup(contenido, 'html.parser')

# Encontrar todos los enlaces
enlaces = soup.find_all('a')

# Abrir enlaces uno por uno con intervalo de 2 segundos
for i in range(100):
    if enlaces:
        enlace = random.choice(enlaces)
        webbrowser.open_new_tab(enlace.get('href'))
        enlaces.remove(enlace)
        enlace.decompose()
        time.sleep(5)

# Convertir la sopa de nuevo a HTML
nuevo_contenido = str(soup)

# Eliminar los espacios en blanco que quedan después de los enlaces y las etiquetas <br/>
nuevo_contenido = re.sub(r'\n\s*\n', '\n', nuevo_contenido)

# Sobrescribir el archivo HTML con el nuevo contenido
with open('links_bandas.html', 'w', encoding='utf-8') as f:
    f.write(nuevo_contenido)