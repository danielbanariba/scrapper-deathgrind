# El arhcivo html descargado, lastimosamente no se descargo la informacion de la descarga, pero lo que se puede hacer es un scraping de cada uno

# Descartar automáticamente las bandas si pertenecen a uno de los siquientes sellos discograficos:
# Unique Leader Records
# Century Media Records
# Nuclear Blast Records
# Metal Blade Records

# Instrucciones o pasos a seguir:
# 1) va abrir cada link generado por el algoritmo anterior osea el 06_script_descargas.py
# 2) va a empezar analizar el codigo html hasta encontrar la etiqueta "dgc-mxso69 e6btpoe18" ya que hay es donde contiene la informacion de la banda:
# Tipo (Album o EP), Año, Genero, Pais y Sello discografico
# 3) Va a comparar el nombre del sello discografico, si el sello discografico es uno de los mencionados anteriormente, se va a descartar la banda (usar el metodo lower() para comparar los nombres de los sellos discograficos ya que puede que esten en mayusculas o minusculas)
# 4) Si no es uno de los sellos discograficos mencionados anteriorente, se va a guardar el link que previamente se guardo de la banda en un archivo html, como se hizo en el paso anterior 06_script_descargas.py, por ende tendra que ser capaz de generar un nuevo html con las bandas aprobadas
# 5) A continuacion, si la banda paso el filtro, generar un nuevo archivo .txt que se va a llama "[nombre-de-la-banda] (descripcion).txt" dentro del archivo .txt va a tener la siguiente informacion:
# [nombre] - [nombre_album] (FULL [tipo] (osea si es un Album o EP)) ([Annio de lanzamiento] - [Genero]) 

# 6) se va a buscar tambien las redes sociales que involucran a la banda, ya sea facebook, youtube o cualquiera otra, esta informacion se va a encontrar en la etiqueta 'dgc-0 e1rub3pj0' dentonces al encontrar los nombres, ya sea discogs, bandcamps, facebook, instalgram o cualquier otro nombre que este dentro de la etiqueta, vas a poner el nombre y a la par vas a poner el link del nombre de la red social, el link va ser tal cual textual como este en el archivo html, no se va a modificar nada, solo se va a copiar y pegar. 
# Ejemplo de como se veria el archivo .txt al finalizar el script:


# Metallica - Master Of Puppets (FULL ALBUM) (1986 - HEAVY METAL) 

# Facebook: link
# Instagram: link
# Youtube: link

# Género/Genre: Heavy Metal
# País/Country: EE.UU
# Año/Year: 1986

# 7) Se va a repetir el proceso hasta que se haya analizado todos los links

import requests
from bs4 import BeautifulSoup
import re
import os

# Lista de sellos discográficos a filtrar
sellos_discograficos = ["Unique Leader Records", "Century Media Records", "Nuclear Blast Records", "Metal Blade Records"]

# Verificar si el archivo 'links_bandas.html' existe
if not os.path.exists('links_bandas.html'):
    print("El archivo 'links_bandas.html' no existe.")
    exit()

# Leer los enlaces del archivo
with open('links_bandas.html', 'r') as f:
    band_links = f.readlines()

# Lista para almacenar los enlaces aprobados
bandas_aprobadas = []

for link in band_links:
    response = requests.get(link)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Encuentra la etiqueta que contiene la información de la banda
    info_banda = soup.find('div', class_='dgc-mxso69 e6btpoe18')
    
    try:
        # Extrae el nombre del sello discográfico
        sello_discografico = info_banda.find('a', href=re.compile("\/label\/")).text.strip()
    except AttributeError:
        print(f"No se pudo encontrar el sello discográfico para el enlace {link}")
        continue
    
    # Filtra las bandas por sello discográfico
    if sello_discografico.lower() not in [sello.lower() for sello in sellos_discograficos]:
        # Guarda el enlace de la banda si pasa el filtro
        bandas_aprobadas.append(link)
        
        try:
            # Crea el archivo .txt para la banda
            info_banda_divs = info_banda.find_all('div')
            tipo = info_banda_divs[0].text.split(": ")[1].strip()
            año = info_banda_divs[1].text.split(": ")[1].strip()
            genero = info_banda_divs[2].text.split(": ")[1].strip()
            pais = info_banda_divs[3].text.split(": ")[1].strip()
        except (AttributeError, IndexError):
            print(f"No se pudo encontrar toda la información de la banda para el enlace {link}")
            continue
    
        # Verificar si el archivo .txt para la banda ya existe
        if os.path.exists(f"{nombre_banda} (descripcion).txt"):
            print(f"El archivo '{nombre_banda} (descripcion).txt' ya existe.")
            continue
        
        with open(f"{nombre_banda} (descripcion).txt", "w") as archivo_txt:
            archivo_txt.write(f"{nombre_banda} - {nombre_album} (FULL {tipo.upper()}) ({año} - {genero.upper()})\n\n")
            
            # Busca y guarda las redes sociales de la banda
            redes_sociales = soup.find_all('a', class_='dgc-0 e1rub3pj0')
            for red_social in redes_sociales:
                archivo_txt.write(f"{red_social.text.strip()}: {red_social['href']}\n")
                
            archivo_txt.write("\nGénero/Genre: {}\n".format(genero))
            archivo_txt.write("País/Country: {}\n".format(pais))
            archivo_txt.write("Año/Year: {}\n".format(año))

# Guarda los enlaces aprobados en un archivo HTML
with open("bandas_aprobadas.html", "w") as archivo_html:
    archivo_html.write("<html><head><title>Bandas Aprobadas</title></head><body>")
    for banda in bandas_aprobadas:
        archivo_html.write(f'<a href="{banda}">{banda}</a><br>')
    archivo_html.write("</body></html>")