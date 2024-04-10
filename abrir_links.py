import webbrowser
from bs4 import BeautifulSoup

# Leer el archivo HTML
with open('tu_archivo.html', 'r') as f:
    contenido = f.read()

# Pasar el contenido a BeautifulSoup
soup = BeautifulSoup(contenido, 'html.parser')

# Encontrar todos los enlaces
enlaces = soup.find_all('a')

# Iterar sobre los enlaces y abrir cada uno en una nueva pestaña
for enlace in enlaces:
    webbrowser.open_new_tab(enlace.get('href'))