import webbrowser
from bs4 import BeautifulSoup
import re

# Leer el archivo HTML
with open('links_bandas.html', 'r', encoding='utf-8') as f:
    contenido = f.read()

# Pasar el contenido a BeautifulSoup
soup = BeautifulSoup(contenido, 'html.parser')

# Encontrar todos los enlaces
enlaces = soup.find_all('a')

# Encontrar todas las etiquetas <br/>
brs = soup.find_all('br')

# Iterar sobre los enlaces y abrir cada uno en una nueva pestaña
for i in range(24):
    if enlaces:
        enlace = enlaces.pop(0)
        webbrowser.open_new_tab(enlace.get('href'))
        enlace.decompose()  # Eliminar el enlace del objeto soup

    if brs:
        br = brs.pop(0)
        br.decompose()  # Eliminar la etiqueta <br/> del objeto soup

# Convertir la sopa de nuevo a HTML
nuevo_contenido = str(soup)

# Eliminar los espacios en blanco que quedan después de los enlaces y las etiquetas <br/>
nuevo_contenido = re.sub(r'\n\s*\n', '\n', nuevo_contenido)

# Sobrescribir el archivo HTML con el nuevo contenido
with open('links_bandas.html', 'w', encoding='utf-8') as f:
    f.write(nuevo_contenido)