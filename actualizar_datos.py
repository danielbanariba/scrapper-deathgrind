#En este script lo que quiero hacer es que cuando vuelva a descargar nuevamente los archivos de la pagina DeathGrind.club va a comparar los ods archivos
# El nuevo y el viejo, entonces va a crear un tercer archivo que va a rescatar solo los que no tienen datos duplicados, es decir, que no se repiten, es decir
# El archivo nuevo solo va a tener datos nuevos

import webbrowser

# Iterate over the numbers 1 to 200
for i in range(101, 201):
    # Format the URL with the current number
    url = f"https://deathgrind.club/posts/genres/{i}"
    
    # Open the URL in the default web browser
    webbrowser.open(url)