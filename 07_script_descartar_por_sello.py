# # El arhcivo html descargado, lastimosamente no se descargo la informacion de la descarga, pero lo que se puede hacer es un scraping de cada uno

# # Descartar automáticamente las bandas si pertenecen a uno de los siquientes sellos discograficos:
# # Unique Leader Records
# # Century Media Records
# # Nuclear Blast Records
# # Metal Blade Records

# Instrucciones o pasos a seguir:
# 1) tengo el archivo links_bandas.html que contiene un monton de links, se tendra que usar selenium para poder abrir cada link y examinar el codigo html de cada link
# 2) va a empezar analizar el codigo html hasta encontrar la etiqueta "dgc-mxso69 e6btpoe18" ya que hay es donde contiene la informacion de la banda: Tipo (Album o EP), Año, Genero, Pais y Sello discografico
# 3) Va a comparar el nombre del sello discografico que son lo siguientes: Unique Leader Records, Century Media Records, Nuclear Blast Records, Metal Blade Records, si el sello discografico es uno de los mencionados anteriormente, se va a descartar la banda (usar el metodo lower() para comparar los nombres de los sellos discograficos ya que puede que esten en mayusculas o minusculas)
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

with open("links_bandas.html", "r", encoding='utf-8') as f:
    links = f.readlines()

def analizar_banda(link):
    # Parse the HTML anchor tag and extract the URL
    soup_link = BeautifulSoup(link, "html.parser")
    url = soup_link.a['href']

    # Obtain the HTML page
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")

    # Continue with the rest of the function...

    # Buscar información de la banda
    info_banda = soup.find("div", class_="dgc-mxso69 e6btpoe18")
    tipo = info_banda.find("span", class_="dgc-mxso69 j83ag55e").text.strip()
    año = info_banda.find("span", class_="dgc-mxso69 e143979t").text.strip()
    genero = info_banda.find("span", class_="dgc-mxso69 d154197o").text.strip()
    pais = info_banda.find("span", class_="dgc-mxso69 e184788j").text.strip()
    sello = info_banda.find("span", class_="dgc-mxso69 e124547t").text.strip().lower()

    # Filtrar por sello discográfico
    if sello not in ["unique leader records", "century media records", 
                    "nuclear blast records", "metal blade records"]:

        # Guardar link en archivo HTML
        with open("bandas_aprobadas.html", "a") as f:
            f.write(link + "\n")

        # Generar archivo TXT
        nombre_banda = info_banda.find("h1", class_="dgc-mxso69 j83ag55e").text.strip()
        descripcion = f"{nombre_banda} - {tipo} ({año} - {genero})"
        with open(f"{nombre_banda} ({descripcion}).txt", "w") as f:
            f.write(f"{descripcion}\n\n")

            # Buscar redes sociales
            redes_sociales = soup.find("div", class_="dgc-0 e1rub3pj0")
            for enlace in redes_sociales.find_all("a"):
                nombre_red = enlace.text.strip()
                link_red = enlace["href"]
                f.write(f"{nombre_red}: {link_red}\n")

            # Información adicional
            f.write("\nGénero/Genre: {}\n".format(genero))
            f.write("País/Country: {}\n".format(pais))
            f.write("Año/Year: {}\n".format(año))

for link in links:
    analizar_banda(link.strip())