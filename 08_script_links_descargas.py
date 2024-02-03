from selenium import webdriver
from bs4 import BeautifulSoup

# Crea una nueva instancia del navegador
driver = webdriver.Firefox()

# Abre el archivo con los enlaces y lee todas las líneas
with open('links_bandas_corregidos2.txt', 'r') as f:
    links = f.read().splitlines()

# Abre el archivo donde se guardarán los enlaces de descarga
with open('links_para_descargar.txt', 'w') as f:
    # Para cada enlace en el archivo de entrada
    for link in links:
        print(f'Procesando {link}...')
        # Abre el enlace en el navegador
        driver.get(link)
        # Obtiene el código fuente de la página
        html = driver.page_source
        # Analiza el contenido con BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        # Busca el div con la clase específica
        div = soup.find('div', {'class': 'dgc-1v5q7bt e6btpoe22'})
        # Si el div existe
        if div:
            print('Div encontrado.')
            # Busca la etiqueta a con la clase específica dentro del div
            a_tags = div.find_all('a', {'class': 'MuiButtonBase-root MuiButton-root MuiButton-outlined MuiButton-outlinedPrimary MuiButton-sizeMedium MuiButton-outlinedSizeMedium MuiButton-fullWidth MuiButton-root MuiButton-outlined MuiButton-outlinedPrimary MuiButton-sizeMedium MuiButton-outlinedSizeMedium MuiButton-fullWidth ek7zlxg1 dgc-1sonpuj'})
            # Si se encontraron etiquetas a
            if a_tags:
                print(f'Encontradas {len(a_tags)} etiquetas a.')
                # Para cada etiqueta a
                for a in a_tags:
                    # Si la etiqueta a tiene un atributo href
                    if 'href' in a.attrs:
                        # Escribe el enlace de descarga en el archivo de salida
                        f.write(a['href'] + '\n')
            else:
                print('No se encontraron etiquetas a.')
        else:
            print('Div no encontrado.')

# Cierra el navegador al finalizar
driver.quit()