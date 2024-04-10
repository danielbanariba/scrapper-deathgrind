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

#### 03_script_filtro_single_and_demo:
Teniendo la lista de las bandas completas osea el 'bandas_corregidos.txt' lo que toca es separarlo en dos archivos que seria un archivo donde solo contengan los titulos sinlge, demo, split, ect, y el otro donde tengan lo que realmente me interesa que es el album y el ep, esto se hace para reducir las posibles busquedas que se van hacer a continuacion.

#### 04_script_busqueda_youtube:
El archivo bandas.txt y va a generar un html con la etiqueta **<a>** para que se pueda dar click y de forma instantanea tener el resultado de busqueda en youtube.

#### 05_script_filtro_busqueda:
Abre un navegador web, para poder hacer click en cada uno de los enlances del archivo html, al momento de tener la pagina abierta y en el resultado de la busqueda va a buscar en los primeros dos videos alguna coincidecia en el titulo (album o ep), si se cumple, se elimina la banda de la lista bandas.txt y si no se cumple se guarda la banda y lo almacena en un nuevo archivo .txt llamado bandas_filtradas.txt. 
>
> [!WARNING] 
> Lastimosamente el script no es perfecto y tiene un límite, y de repente falla, asi que hay que entrar al archivo de bandas.txt y eliminar desde la última búsqueda y volver a ejecutar el script.
>

#### 06_script_descargas:
Ya teniendo la lista de bandas aprobadas lo que sigue es generar los links para poder acceder a ellos de manera simple y empezar a decargar, por ende solo se va a encargar de generar el codigo html con los nombres de la bandas.

#### 07_script_descartar_por_sello:
Va hacer otro filtro pero esta vez de la casa disquera para poder evitarnos problemas legales, al mismo tiempo, va a generar un nuevo archivo .txt que sera la descripcion osea toda la informacion importante, como annio, pais, redes sociales.

#### 03_script_busqueda_youtube:
