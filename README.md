<div align="center">
  <h1 align="center">Algoritmos de automatizacion</a></h1>
</div>

<!-- Installation -->
### :gear: Instalacion

En un solo comando: 
```sh
pip beautifulsoup4 requests bs4 selenium
``` 
  
Oh uno por uno (Si es que tuvo problemas en instalarlo de un solo):
```sh
pip beautifulsoup4 
```
```sh
pip requests
```
```sh
pip bs4
```
```sh
pip selenium
```

<!-- TENGO QUE DEJAR PASO A PASO QUE TIENE QUE HACER! -->
## Explicacion de que hace cada script: 

#### 00_script:

Este script no sirve de nada, ya que la pagina original donde se hace el escaneo tiene un detector de boots, entonces la pagina se queda trabada, pero lo dejo ya que es interesante ver como hace scroll de manera automatica. 

#### 01_script_prueba:

Al tener en cuenta que el script 0 solo es de prueba, ahora nos vamos el script 1, para que el script funcione bien: tenemos que descargar la pagina completa, descargar el codigo fuente de la pagina, para que resulte mas facil, es irse a la seccion de generos y descargar todo el catalago de la pagina, guardarlo en una carpeta para tener el codigo HTML. El script 01 al momento de ser ejecutado va a escanear el codigo fuente de la pagina que previamente hemos descargado, va a examinar o escanear el codigo hasta encontrar la etiqueta **<a>** va a seguir escaneando y va a encontrar la etiqueta **title** que es la encargada de guardar los titulos de las bandas en la pagina web y al momento de encontrar esa palabra clave va a extraer el titulo y lo va almacenar en un nuevo archivo txt llamado bandas.txt.

#### 02_script_duplicados:
Como es logico, mas de alguna banda va a tener mas de un genero musical, por ende el titulo se va a repetir mas de una vez, lo que hace el script es compara los titulos y si son iguales se elimina y asi evitamos titulos duplicados.

#### 03_script_busqueda_youtube:
En este script no hay mucho que explicar, solo va agarrar los titulos del archivo bandas.txt y va a generar un html con la etiqueta **<a>** para que se pueda dar click y de forma instantanea tener el resultado de busqueda en youtube.

#### 04_script_filtro_busqueda:
Este script es el que cosidero es el mas interesante y completo de todos, lo que hace es abrir un navegador web, va hacer click uno por uno en el archivo html, al momento de tener la pagina abierta y el resultado de la busqueda va a buscar en los resultados de busqueda si alguno contiene alguna coincidecia en el titulo, si se cumple, se elimina la banda y si no se cumple se guarda la banda.

#### 05_script_filtro_single_and_demo:
Ya teniendo el archivo filtrado toca aplicar otro filtro que seria separar los demos y los singles, ya que es contenido que no me interesan en mi canal de youtube.

#### 06_script_descargas:

#### 07_script_links_duplicados:

#### 08_script_links_descargas:

#### crear_videos:

#### 03_script_busqueda_youtube: